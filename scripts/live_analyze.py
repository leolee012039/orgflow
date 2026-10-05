"""Live acceptance check for the Organization Analyst (uses the Gemini API).

Run: uv run python scripts/live_analyze.py [runs]
Passes when every run returns origin "live" or "repaired" with the CEO,
4 departments and 8 department roles.
"""

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
os.environ.pop("ORGFLOW_DEV_CACHE", None)  # acceptance runs must hit the live model

import pipeline  # noqa: E402

EN = ROOT / "demo_assets" / "en"


async def main(runs: int) -> int:
    org_pdf = (EN / "NovaGear_Organization_Chart.pdf").read_bytes()
    policy_pdf = (EN / "NovaGear_Purchasing_Policy.pdf").read_bytes()
    failures = 0
    for i in range(1, runs + 1):
        result = await pipeline.analyze_organization(org_pdf, policy_pdf)
        org = result.value
        dept_roles = [r for r in org.roles if r.department]
        top = [r for r in org.roles if r.reports_to is None]
        ok = (result.origin != "fixture" and len(org.departments) == 4
              and len(dept_roles) == 8 and len(top) == 1)
        failures += not ok
        print(f"run {i}: origin={result.origin} latency={result.latency_ms}ms "
              f"departments={len(org.departments)} department_roles={len(dept_roles)} "
              f"top_role={[r.title for r in top]} relationships={len(org.relationships)} "
              f"-> {'PASS' if ok else 'FAIL'}")
        if result.problems:
            print("   problems:", result.problems[:5])
    return failures


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    sys.exit(asyncio.run(main(n)))
