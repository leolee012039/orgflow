"""Live acceptance check for Phase 3: opportunities → workflow → runs (uses Gemini).

Run: uv run python scripts/live_pipeline.py [rounds]
Each round: analyze the organization, find opportunities, compile the top one,
then run the policy's boundary cases through the runner. Only the 2,400 and
"N/A" requests call Gemini for the ai_review step; the other cases use the
runner's plain-code check, since they test thresholds, not the reviewer.
"""

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
os.environ.pop("ORGFLOW_DEV_CACHE", None)

import pipeline  # noqa: E402
from schemas import PurchaseRequestForm  # noqa: E402

EN = ROOT / "demo_assets" / "en"
BASE = dict(request_id="PR-2026-0142", requester="Emma Chen", department="Operations",
            item="MacBook Pro",
            business_justification="Laptop required for a new Product Designer supporting the Operations team.")

# (label, overrides, live review, expected status, finance step, director step)
CASES = [
    ("USD 750", {"estimated_cost": 750}, False, "COMPLETED", "SKIPPED", "SKIPPED"),
    ("USD 1,000", {"estimated_cost": 1000}, False, "COMPLETED", "PASSED", "SKIPPED"),
    ("USD 2,400", {"estimated_cost": 2400}, True, "COMPLETED", "PASSED", "SKIPPED"),
    ("USD 5,000", {"estimated_cost": 5000}, False, "COMPLETED", "PASSED", "SKIPPED"),
    ("USD 8,000", {"estimated_cost": 8000}, False, "NEEDS_HUMAN_REVIEW", "PASSED", "HUMAN_REVIEW"),
    ("no justification", {"estimated_cost": 2400, "business_justification": ""}, False, "RETURNED", None, None),
    ("justification N/A", {"estimated_cost": 2400, "business_justification": "N/A"}, True,
     "NEEDS_HUMAN_REVIEW", None, None),
]


def step_result(trace, workflow, kind):
    """Find the finance or director approval by its actor, whatever ids the model chose."""
    for step in workflow.steps:
        if step.type != "approval":
            continue
        actor = step.actor.lower()
        is_director = step.actor in workflow.unresolved_actors
        is_finance = not is_director and ("finance" in actor or "accountant" in actor)
        if (kind == "director" and is_director) or (kind == "finance" and is_finance):
            return next((s.result for s in trace.steps if s.step_id == step.id), None)
    return None


async def one_round(n: int) -> int:
    org_pdf = (EN / "NovaGear_Organization_Chart.pdf").read_bytes()
    policy_pdf = (EN / "NovaGear_Purchasing_Policy.pdf").read_bytes()
    failures = 0

    org = await pipeline.analyze_organization(org_pdf, policy_pdf)
    opps = await pipeline.discover_opportunities(org_pdf, policy_pdf, org.value)
    print(f"\n=== round {n} ===")
    print(f"organization: {org.origin} {org.latency_ms}ms")
    print(f"opportunities: {opps.origin} {opps.latency_ms}ms")
    for o in opps.value.opportunities:
        print(f"   - {o.name} [{o.impact}] executable={o.executable} departments={o.departments}")
    top = opps.value.opportunities[0]
    purchase_first = "purchase" in top.name.lower() and top.executable
    failures += not purchase_first or opps.origin == "fixture"

    wf = await pipeline.design_workflow(org_pdf, policy_pdf, org.value, top)
    print(f"workflow: {wf.origin} {wf.latency_ms}ms unresolved={wf.value.unresolved_actors}")
    for r in wf.value.rules:
        print(f"   rule {r.id}: {r.when.field} {r.when.op} {r.when.value}  <- {r.source!r}")
    for s in wf.value.steps:
        print(f"   step {s.id}: {s.type} by {s.actor}" + (f" only_if {s.only_if}" if s.only_if else ""))
    failures += wf.origin == "fixture"
    failures += max(org.latency_ms, opps.latency_ms, wf.latency_ms) > 25000

    for label, overrides, live, status, finance, director in CASES:
        form = PurchaseRequestForm(**{**BASE, **overrides})
        trace = await pipeline.run_request(wf.value, org.value, form, top.manual_handoffs, live_review=live)
        got = (trace.status, step_result(trace, wf.value, "finance"), step_result(trace, wf.value, "director"))
        want = (status, finance, director)
        ok = got[0] == want[0] and (finance is None or got[1:] == want[1:])
        failures += not ok
        print(f"   run {label:<18} {got} {'PASS' if ok else 'FAIL expected ' + str(want)}")
        if label == "USD 2,400" or not ok:
            for s in trace.steps:
                print(f"      {s.result:<12} {s.step_id}: {s.reason}")
    return failures


async def main(rounds: int) -> int:
    failures = 0
    for n in range(1, rounds + 1):
        failures += await one_round(n)
    print(f"\n{'ALL PASS' if failures == 0 else f'{failures} FAILURE(S)'}")
    return failures


if __name__ == "__main__":
    sys.exit(asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 1)))
