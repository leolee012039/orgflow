"""Guarded AI stages: live answer → one repair → prevalidated fixture.

Each stage asks an agent once, checks the answer with plain code, asks the
agent once more with the list of problems if the check fails, and otherwise
returns the fixture so the demo never stops. A timeout skips the repair,
because a second slow call would break the time budget.
"""

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Generic, Optional, TypeVar

import asyncio

from agents import opportunity_analyst, organization_analyst, request_reviewer, workflow_architect
from agents.runtime import AgentResult, log_event
from guard import (
    extract_pdf_text,
    load_fixture,
    validate_opportunities_output,
    validate_organization_output,
    validate_workflow_output,
)
from runner import run_workflow
from schemas import ExecutionTrace, Opportunities, Opportunity, Organization, OriginType, PurchaseRequestForm, Workflow

T = TypeVar("T")


@dataclass
class StageResult(Generic[T]):
    value: T
    origin: OriginType
    latency_ms: int
    problems: list[str] = field(default_factory=list)


async def run_guarded_stage(
    stage: str,
    first_call: Callable[[], Awaitable[AgentResult]],
    repair_call: Callable[[Optional[dict], list[str]], Awaitable[AgentResult]],
    validate: Callable[[Any], tuple[Optional[T], list[str]]],
    fixture: Callable[[], T],
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

    log_event("guard", stage=stage, origin="fixture", latency_ms=latency, problems=problems[:10])
    return StageResult(fixture(), "fixture", latency, problems)


def documents_text(org_pdf: bytes, policy_pdf: bytes) -> str:
    return extract_pdf_text(org_pdf) + "\n" + extract_pdf_text(policy_pdf)


async def analyze_organization(org_pdf: bytes, policy_pdf: bytes) -> StageResult[Organization]:
    doc_text = documents_text(org_pdf, policy_pdf)
    return await run_guarded_stage(
        stage="organization",
        first_call=lambda: organization_analyst.analyze(org_pdf, policy_pdf),
        repair_call=lambda previous, problems: organization_analyst.repair(org_pdf, policy_pdf, previous, problems),
        validate=lambda data: validate_organization_output(data, doc_text),
        fixture=lambda: Organization.model_validate(load_fixture("organization_fixture.json")),
    )


async def discover_opportunities(org_pdf: bytes, policy_pdf: bytes, org: Organization) -> StageResult[Opportunities]:
    doc_text = documents_text(org_pdf, policy_pdf)
    org_json = org.model_dump(by_alias=True)
    return await run_guarded_stage(
        stage="opportunities",
        first_call=lambda: opportunity_analyst.discover(org_pdf, policy_pdf, org_json),
        repair_call=lambda previous, problems: opportunity_analyst.repair(
            org_pdf, policy_pdf, org_json, previous, problems),
        validate=lambda data: validate_opportunities_output(data, org, doc_text),
        fixture=lambda: Opportunities.model_validate(load_fixture("opportunities_fixture.json")),
    )


async def design_workflow(org_pdf: bytes, policy_pdf: bytes, org: Organization,
                          opportunity: Opportunity) -> StageResult[Workflow]:
    doc_text = documents_text(org_pdf, policy_pdf)
    org_json = org.model_dump(by_alias=True)
    opp_json = opportunity.model_dump()

    def validate(data):
        wf, problems = validate_workflow_output(data, org, doc_text)
        if wf is not None and wf.opportunity_id != opportunity.id:
            return None, [f"opportunity_id must be '{opportunity.id}', got '{wf.opportunity_id}'"]
        return wf, problems

    return await run_guarded_stage(
        stage="workflow",
        first_call=lambda: workflow_architect.design(org_pdf, policy_pdf, org_json, opp_json),
        repair_call=lambda previous, problems: workflow_architect.repair(
            org_pdf, policy_pdf, org_json, opp_json, previous, problems),
        validate=validate,
        fixture=lambda: Workflow.model_validate(load_fixture("workflow_fixture.json")),
    )


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
