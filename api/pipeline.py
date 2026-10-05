"""Guarded AI stages: live answer → one repair → prevalidated fixture or an honest failure.

Each stage asks an agent once, checks the answer with plain code, and asks the
agent once more with the list of problems if the check fails. A timeout skips
the repair, because a second slow call would break the time budget.

If both answers fail, the NovaGear sample falls back to its prevalidated
fixture so the demo never stops. Anyone else's documents get no fixture: the
stage returns "unverified" and the API says so, instead of showing NovaGear.
"""

import asyncio
import hashlib
import io
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Generic, Optional, TypeVar

from pypdf import PdfReader

from agents import (
    document_reader,
    opportunity_analyst,
    organization_analyst,
    request_reviewer,
    workflow_architect,
)
from agents.runtime import AgentResult, log_event
from coverage import find_amount_gaps
from guard import (
    extract_pdf_text,
    load_fixture,
    validate_opportunities_output,
    validate_organization_output,
    validate_workflow_output,
    verify_quote_in_text,
)
from runner import run_workflow
from schemas import ExecutionTrace, Opportunities, Opportunity, Organization, PurchaseRequestForm, Workflow

T = TypeVar("T")


@dataclass
class StageResult(Generic[T]):
    value: Optional[T]
    origin: str  # "live" | "repaired" | "fixture" | "unverified"
    latency_ms: int
    problems: list[str] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)


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


def is_sample(org_pdf: bytes, policy_pdf: bytes) -> bool:
    """True only for the bundled NovaGear documents, the one case where a fixture is honest."""
    sample = load_fixture("sample_documents.json")
    return _sha256(org_pdf) == sample["org_chart"] and _sha256(policy_pdf) == sample["policy"]


def _fixture(org_pdf: bytes, policy_pdf: bytes, name: str, model):
    if not is_sample(org_pdf, policy_pdf):
        return None
    return lambda: model.model_validate(load_fixture(name))


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


async def documents_text(org_pdf: bytes, policy_pdf: bytes) -> str:
    org_text, policy_text = await asyncio.gather(document_text(org_pdf), document_text(policy_pdf))
    return org_text + "\n" + policy_text


async def analyze_organization(org_pdf: bytes, policy_pdf: bytes) -> StageResult[Organization]:
    doc_text = await documents_text(org_pdf, policy_pdf)
    return await run_guarded_stage(
        stage="organization",
        first_call=lambda: organization_analyst.analyze(org_pdf, policy_pdf),
        repair_call=lambda previous, problems: organization_analyst.repair(org_pdf, policy_pdf, previous, problems),
        validate=lambda data: validate_organization_output(data, doc_text),
        fixture=_fixture(org_pdf, policy_pdf, "organization_fixture.json", Organization),
    )


async def discover_opportunities(org_pdf: bytes, policy_pdf: bytes, org: Organization) -> StageResult[Opportunities]:
    doc_text = await documents_text(org_pdf, policy_pdf)
    org_json = org.model_dump(by_alias=True)
    return await run_guarded_stage(
        stage="opportunities",
        first_call=lambda: opportunity_analyst.discover(org_pdf, policy_pdf, org_json),
        repair_call=lambda previous, problems: opportunity_analyst.repair(
            org_pdf, policy_pdf, org_json, previous, problems),
        validate=lambda data: validate_opportunities_output(data, org, doc_text),
        fixture=_fixture(org_pdf, policy_pdf, "opportunities_fixture.json", Opportunities),
    )


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


async def design_workflow(org_pdf: bytes, policy_pdf: bytes, org: Organization,
                          opportunity: Opportunity) -> StageResult[Workflow]:
    doc_text = await documents_text(org_pdf, policy_pdf)
    org_json = org.model_dump(by_alias=True)
    opp_json = opportunity.model_dump()

    def validate(data):
        wf, problems = validate_workflow_output(data, org, doc_text)
        if wf is not None and wf.opportunity_id != opportunity.id:
            return None, [f"opportunity_id must be '{opportunity.id}', got '{wf.opportunity_id}'"]
        return wf, problems

    result = await run_guarded_stage(
        stage="workflow",
        first_call=lambda: workflow_architect.design(org_pdf, policy_pdf, org_json, opp_json),
        repair_call=lambda previous, problems: workflow_architect.repair(
            org_pdf, policy_pdf, org_json, opp_json, previous, problems),
        validate=validate,
        fixture=_fixture(org_pdf, policy_pdf, "workflow_fixture.json", Workflow),
    )
    if result.value is not None:
        result.extras["gaps"] = find_gaps(result.value, await document_text(org_pdf))
        result.extras["amount_gaps"] = find_amount_gaps(result.value.amount_tiers)
    return result


async def run_request(workflow: Workflow, org: Organization, form: PurchaseRequestForm,
                      manual_handoffs_before: int = 4, live_review: bool = True) -> ExecutionTrace:
    """Execute a request. The runner is plain code; only the ai_review step may call Gemini."""
    reviewer = None
    review_step = next((s for s in workflow.steps if s.type == "ai_review"), None)
    if live_review and review_step is not None:
        reviewer = request_reviewer.make_reviewer(review_step.check or "", workflow.required_fields)
    trace = await asyncio.to_thread(run_workflow, workflow, org, form, reviewer, manual_handoffs_before)
    log_event("run", request_id=trace.request_id, status=trace.status,
              steps=[f"{s.step_id}:{s.result}" for s in trace.steps])
    return trace
