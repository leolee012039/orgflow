"""Guarded AI stages: live answer → one repair → prevalidated fixture.

Each stage asks an agent once, checks the answer with plain code, asks the
agent once more with the list of problems if the check fails, and otherwise
returns the fixture so the demo never stops. A timeout skips the repair,
because a second slow call would break the time budget.
"""

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Generic, Optional, TypeVar

from agents import organization_analyst
from agents.runtime import AgentResult, log_event
from guard import extract_pdf_text, load_fixture, validate_organization_output
from schemas import Organization, OriginType

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
