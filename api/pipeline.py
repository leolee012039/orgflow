"""Guarded AI stages: live answer → one repair → prevalidated fixture or an honest failure.

Each stage asks an agent once, checks the answer with plain code, and asks the
agent once more with the list of problems if the check fails. A timeout skips
the repair, because a second slow call would break the time budget.

If both answers fail, a bundled sample falls back to its prevalidated fixture so
the demo never stops. Anyone else's documents get no fixture: the stage returns
"unverified" and the API says so, instead of showing the sample.

The stages follow the company from the top down: the organization, then what each
department does and hands to the others, then the workflows each department could
automate, then one department's workflow built so a program can run it.
"""

import asyncio
import hashlib
import io
import os
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Generic, Optional, Sequence, TypeVar

from pypdf import PdfReader

from agents import (
    department_analyst,
    document_reader,
    organization_analyst,
    request_reviewer,
    workflow_architect,
    workflow_planner,
)
from agents.runtime import AgentResult, log_event
from amount_coverage import find_amount_gaps
from guard import (
    FIXTURES_DIR,
    extract_pdf_text,
    form_fields,
    load_fixture,
    validate_department_map,
    validate_organization_output,
    validate_workflow_output,
    validate_workflow_plan,
    verified_amount_tiers,
    verify_quote_in_text,
)
from runner import run_chain, run_workflow
from schemas import (
    ChainTrace,
    Decision,
    DepartmentMap,
    ExecutionTrace,
    FormField,
    Organization,
    RequestForm,
    Workflow,
    WorkflowCandidate,
    WorkflowPlan,
)

T = TypeVar("T")


@dataclass
class StageResult(Generic[T]):
    value: Optional[T]
    origin: str  # "live" | "repaired" | "fixture" | "unverified"
    latency_ms: int
    problems: list[str] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class Docs:
    """The uploaded documents: one org chart and any number of policies."""
    org_chart: bytes
    policies: list[bytes]

    def labelled(self) -> list[tuple[str, bytes]]:
        """Each document with the id agents cite it by: org_chart, policy_1, policy_2, ..."""
        return [("org_chart", self.org_chart), *((f"policy_{i}", p) for i, p in enumerate(self.policies, 1))]


async def run_guarded_stage(
    stage: str,
    first_call: Callable[[], Awaitable[AgentResult]],
    repair_call: Callable[[Optional[dict], list[str]], Awaitable[AgentResult]],
    validate: Callable[[Any], tuple[Optional[T], list[str]]],
    fixture: Optional[Callable[[], T]],
) -> StageResult[T]:
    first = await first_call()
    latency = first.latency_ms
    if first.data is not None:
        value, problems = validate(first.data)
        if value is not None:
            log_event("guard", stage=stage, origin="live", latency_ms=latency)
            return StageResult(value, "live", latency)
    else:
        problems = [first.error or "no answer"]

    if first.error is None or not first.error.startswith("timed out"):
        second = await repair_call(first.data, problems)
        latency += second.latency_ms
        if second.data is not None:
            value, repair_problems = validate(second.data)
            if value is not None:
                log_event("guard", stage=stage, origin="repaired", latency_ms=latency, problems=problems)
                return StageResult(value, "repaired", latency, problems)
            problems = problems + repair_problems
        else:
            problems = problems + [second.error or "no answer"]

    origin = "fixture" if fixture is not None else "unverified"
    log_event("guard", stage=stage, origin=origin, latency_ms=latency, problems=problems[:10])
    return StageResult(fixture() if fixture is not None else None, origin, latency, problems)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sample_name(docs: Docs) -> Optional[str]:
    """Which bundled sample these exact documents are, if any: the one case where a fixture is honest."""
    org, policies = _sha256(docs.org_chart), [_sha256(p) for p in docs.policies]
    for name, sample in load_fixture("sample_documents.json").items():
        if sample["org_chart"] == org and sample["policies"] == policies:
            return name
    return None


def is_sample(docs: Docs) -> bool:
    return sample_name(docs) is not None


def _fixture(docs: Docs, filename: str, model):
    name = sample_name(docs)
    if name is None or not os.path.exists(os.path.join(FIXTURES_DIR, name, filename)):
        return None
    return lambda: model.model_validate(load_fixture(f"{name}/{filename}"))


_TRANSCRIPTS: dict[str, str] = {}


def _has_text_layer(text: str, pdf: bytes) -> bool:
    """A scanned PDF yields almost no text: fewer than 40 visible characters per page."""
    try:
        pages = len(PdfReader(io.BytesIO(pdf)).pages)
    except Exception:
        pages = 1
    return len(re.sub(r"\s", "", text)) >= 40 * max(pages, 1)


async def document_text(pdf: bytes) -> str:
    """The text the guard checks quotes against. Scanned PDFs are transcribed by Gemini once."""
    text = extract_pdf_text(pdf)
    if _has_text_layer(text, pdf):
        return text
    key = _sha256(pdf)
    if key not in _TRANSCRIPTS:
        result = await document_reader.transcribe(pdf)
        transcript = (result.data or {}).get("text", "") if result.data else ""
        log_event("transcribed", ok=bool(transcript), chars=len(transcript), latency_ms=result.latency_ms,
                  error=result.error)
        if not transcript:
            return text  # nothing better: the checks will fail and say so
        _TRANSCRIPTS[key] = transcript
    return _TRANSCRIPTS[key]


async def documents_text(docs: Docs) -> str:
    texts = await asyncio.gather(*(document_text(pdf) for _, pdf in docs.labelled()))
    return "\n".join(texts)


async def analyze_organization(docs: Docs) -> StageResult[Organization]:
    doc_text = await documents_text(docs)
    labelled = docs.labelled()
    return await run_guarded_stage(
        stage="organization",
        first_call=lambda: organization_analyst.analyze(labelled),
        repair_call=lambda previous, problems: organization_analyst.repair(labelled, previous, problems),
        validate=lambda data: validate_organization_output(data, doc_text),
        fixture=_fixture(docs, "organization.json", Organization),
    )


async def map_departments(docs: Docs, org: Organization) -> StageResult[DepartmentMap]:
    doc_text = await documents_text(docs)
    labelled, org_json = docs.labelled(), org.model_dump(by_alias=True)
    return await run_guarded_stage(
        stage="department_map",
        first_call=lambda: department_analyst.analyze(labelled, org_json),
        repair_call=lambda previous, problems: department_analyst.repair(labelled, org_json, previous, problems),
        validate=lambda data: validate_department_map(data, org, doc_text, department_analyst.MAX_DEPARTMENTS),
        fixture=_fixture(docs, "department_map.json", DepartmentMap),
    )


async def plan_workflows(docs: Docs, org: Organization, dmap: DepartmentMap) -> StageResult[WorkflowPlan]:
    doc_text = await documents_text(docs)
    labelled, org_json, map_json = docs.labelled(), org.model_dump(by_alias=True), dmap.model_dump(by_alias=True)
    return await run_guarded_stage(
        stage="workflow_plan",
        first_call=lambda: workflow_planner.plan(labelled, org_json, map_json),
        repair_call=lambda previous, problems: workflow_planner.repair(labelled, org_json, map_json, previous, problems),
        validate=lambda data: validate_workflow_plan(data, dmap, doc_text, workflow_planner.MAX_PER_DEPARTMENT),
        fixture=_fixture(docs, "workflow_plan.json", WorkflowPlan),
    )


LEGACY_FIELDS = [
    FormField(name="item", label="Requested Item"),
    FormField(name="estimated_cost", label="Estimated Cost", type="number"),
    FormField(name="business_justification", label="Business Justification"),
]


def fields_of(wf: Workflow) -> list[FormField]:
    """The fields a case carries out of this workflow."""
    return wf.fields or LEGACY_FIELDS


def find_gaps(workflow: Workflow, org_chart_text: str) -> list[dict[str, Any]]:
    """Approvers the policy requires that the organization does not provide.

    "missing": the uploaded org chart never mentions the approver.
    "possible_match": the org chart mentions it, but the extracted organization has no
    such role, so a person should confirm who it is before anyone calls it a gap.
    """
    rules = {r.id: r for r in workflow.rules}
    gaps = []
    for actor in workflow.unresolved_actors:
        step = next((s for s in workflow.steps if s.actor == actor), None)
        rule = rules.get(step.only_if) if step and step.only_if else None
        gaps.append({
            "actor": actor,
            "status": "possible_match" if verify_quote_in_text(actor, org_chart_text) else "missing",
            "step_id": step.id if step else None,
            "policy_quote": rule.source if rule else None,
        })
    return gaps


async def build_workflow(docs: Docs, org: Organization, planned: WorkflowCandidate,
                         upstream: Optional[Workflow] = None) -> StageResult[Workflow]:
    """Compile one department's planned workflow. When it starts from another department's
    built workflow, it may only use the data that arrives with the case."""
    doc_text = await documents_text(docs)
    labelled, org_json, planned_json = docs.labelled(), org.model_dump(by_alias=True), planned.model_dump()
    upstream_fields = fields_of(upstream) if upstream is not None else None
    upstream_json = [f.model_dump() for f in upstream_fields] if upstream_fields is not None else None

    def validate(data):
        wf, problems = validate_workflow_output(data, org, doc_text, planned, upstream_fields)
        if wf is not None and wf.opportunity_id != planned.id:
            return None, [f"opportunity_id must be '{planned.id}', got '{wf.opportunity_id}'"]
        return wf, problems

    # A saved answer was built against the sample's own upstream: use it only if it passes the same
    # checks against the upstream this build actually has
    fixture = None
    if re.fullmatch(r"[a-z0-9_]+", planned.id):
        saved = _fixture(docs, f"workflows/{planned.id}.json", Workflow)
        if saved is not None and validate(saved().model_dump())[0] is not None:
            fixture = saved
    result = await run_guarded_stage(
        stage="workflow",
        first_call=lambda: workflow_architect.design(labelled, org_json, planned_json, upstream_json),
        repair_call=lambda previous, problems: workflow_architect.repair(
            labelled, org_json, planned_json, upstream_json, previous, problems),
        validate=validate,
        fixture=fixture,
    )
    if result.value is not None:
        wf = result.value
        # The link the runner follows: this workflow receives cases from the one it was built against
        wf.upstream_id = upstream.opportunity_id if upstream is not None else None
        result.extras["gaps"] = find_gaps(wf, await document_text(docs.org_chart))
        tiers, tier_problems = verified_amount_tiers(wf.amount_tiers, doc_text, form_fields(wf))
        if tier_problems:
            log_event("amount_tiers_dropped", count=len(wf.amount_tiers), problems=tier_problems[:5])
        wf.amount_tiers = tiers  # the runner gets only tiers that passed the checks
        result.extras["amount_gaps"] = find_amount_gaps(tiers)
    return result


def _reviewer_for(workflow: Workflow):
    review_step = next((s for s in workflow.steps if s.type == "ai_review"), None)
    if review_step is None:
        return None
    return request_reviewer.make_reviewer(review_step.check or "", workflow.required_fields)


async def run_request(workflow: Workflow, org: Organization, form: RequestForm,
                      manual_handoffs_before: int = 4, live_review: bool = True,
                      decisions: Sequence[Decision] = ()) -> ExecutionTrace:
    """Execute a request. The runner is plain code; only the ai_review step may call Gemini."""
    reviewer = _reviewer_for(workflow) if live_review else None
    trace = await asyncio.to_thread(run_workflow, workflow, org, form, reviewer, manual_handoffs_before, decisions)
    log_event("run", request_id=trace.request_id, status=trace.status,
              steps=[f"{s.step_id}:{s.result}" for s in trace.steps])
    return trace


async def run_chain_request(workflows: list[Workflow], org: Organization, start_id: str, form: RequestForm,
                            handoffs_before: Optional[dict[str, int]] = None,
                            live_review: bool = True, decisions: Sequence[Decision] = ()) -> ChainTrace:
    """Run a case through the chain of built workflows that starts at start_id."""
    reviewer_for = _reviewer_for if live_review else None
    trace = await asyncio.to_thread(run_chain, workflows, org, start_id, form, reviewer_for, handoffs_before,
                                    decisions)
    log_event("run_chain", request_id=trace.request_id, status=trace.status,
              legs=[f"{leg.workflow_id}:{leg.trace.status}" for leg in trace.legs], waiting_for=trace.waiting_for)
    return trace
