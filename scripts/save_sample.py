"""Add a sample company: read its documents live once, check the reading, and save it as the sample's answers.

Run: uv run python scripts/save_sample.py ID "Company" "Market" "Industry" "Language" ORG.pdf POLICY.pdf ...

Reads the PDFs with live Gemini through every stage the web app runs
(organization, department map, plan, every planned workflow, each after the one it starts from; a failed build
is tried again), prints what was found, and writes:
  web/public/demo/ID/                  the PDFs, which the web app sends for the sample
  api/fixtures/ID/organization.json, department_map.json, workflow_plan.json, workflows/<workflow id>.json
  api/fixtures/sample_documents.json   the documents' fingerprints, so the API knows them
  web/src/lib/samples.json             the sample list the web app shows
Nothing is written unless every stage was answered live and every planned workflow was built.
"""

import asyncio
import hashlib
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
os.environ.pop("ORGFLOW_DEV_CACHE", None)
os.environ["ORGFLOW_SAMPLE_LIVE"] = "1"  # read live even if these documents are already a sample

import pipeline  # noqa: E402

FIXTURES = ROOT / "api" / "fixtures"
DEMO = ROOT / "web" / "public" / "demo"
SAMPLES_JSON = ROOT / "web" / "src" / "lib" / "samples.json"


def build_order(plan: list) -> list:
    """What "Build all" builds: every planned workflow, each after the workflow it starts from."""
    def upstream(c):
        return next((w for w in plan if c.starts_from and w.department == c.starts_from and w.hands_to == c.department), None)

    wanted: dict = {}

    def add(c, seen):
        if c.id in wanted or c.id in seen:
            return
        seen.add(c.id)
        up = upstream(c)
        if up:
            add(up, seen)
        wanted[c.id] = c

    for w in plan:
        add(w, set())
    return list(wanted.values())


async def read(docs: pipeline.Docs):
    org = await pipeline.analyze_organization(docs)
    if org.value is None or org.origin not in ("live", "repaired"):
        sys.exit(f"organization: {org.origin} {org.problems[:3]}")
    dmap = await pipeline.map_departments(docs, org.value)
    if dmap.value is None or dmap.origin not in ("live", "repaired"):
        sys.exit(f"department map: {dmap.origin} {dmap.problems[:3]}")
    plan = await pipeline.plan_workflows(docs, org.value, dmap.value)
    if plan.value is None or plan.origin not in ("live", "repaired"):
        sys.exit(f"plan: {plan.origin} {plan.problems[:3]}")
    candidates = plan.value.workflows
    built: dict = {}
    for attempt in range(3):
        for c in build_order(candidates):
            if c.id in built:
                continue
            up_c = next((w for w in candidates if c.starts_from and w.department == c.starts_from
                         and w.hands_to == c.department), None)
            upstream = built[up_c.id].value if up_c is not None and up_c.id in built else None
            if up_c is not None and upstream is None:
                continue  # its upstream isn't built yet
            result = await pipeline.build_workflow(docs, org.value, c, upstream)
            if result.value is not None and result.origin in ("live", "repaired"):
                built[c.id] = result
            else:
                print(f"  build {c.id}: {result.origin} {result.problems[:2]}", flush=True)
        if len(built) == len(candidates) or attempt == 2:
            break
        print(f"  {len(built)} of {len(candidates)} built; trying the rest again in 10 s", flush=True)
        time.sleep(10)
    if len(built) != len(candidates):
        sys.exit(f"built {len(built)} of {len(candidates)}; nothing saved")
    return org.value, dmap.value, plan.value, built


def main():
    sample_id, company, market, industry, language, org_path, *policy_paths = sys.argv[1:]
    if not re.fullmatch(r"[a-z0-9_]+", sample_id):  # it names folders, and the API reads only ids like this
        sys.exit(f"the id must be lower-case letters, digits or _, got {sample_id!r}")
    sources = [Path(org_path), *map(Path, policy_paths)]
    docs = pipeline.Docs(sources[0].read_bytes(), [p.read_bytes() for p in sources[1:]])

    t = time.perf_counter()
    org, dmap, plan, built = asyncio.run(read(docs))
    print(f"\n{company}: read and built in {time.perf_counter() - t:.0f} s")
    print(f"  departments: {[d.name for d in dmap.departments]}")
    print(f"  handoffs: {[(h.from_dept, h.to, h.what) for h in dmap.handoffs]}")
    for wid, r in built.items():
        gaps = [f"{g['actor']} ({g['status']})" for g in r.extras.get("gaps", [])]
        amounts = [f"{g['kind']} at {g['amount']:,.0f}" for g in r.extras.get("amount_gaps", [])]
        unchecked = " AMOUNT LEVELS UNCHECKED" if r.extras.get("amount_levels_unchecked") else ""
        print(f"  {r.value.department} / {r.value.workflow_name} [{wid}]: missing {gaps or '-'}; amounts {amounts or '-'}{unchecked}")

    # Everything is written beside its place first and swapped in at the end, so a failed run leaves the
    # sample as it was
    def dump(model, path):
        path.write_text(json.dumps(model.model_dump(by_alias=True), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    staged = FIXTURES / f".{sample_id}.new"
    shutil.rmtree(staged, ignore_errors=True)
    (staged / "workflows").mkdir(parents=True)
    dump(org, staged / "organization.json")
    dump(dmap, staged / "department_map.json")
    dump(plan, staged / "workflow_plan.json")
    for wid, r in built.items():
        dump(r.value, staged / "workflows" / f"{wid}.json")
    staged_demo = DEMO / f".{sample_id}.new"
    shutil.rmtree(staged_demo, ignore_errors=True)
    staged_demo.mkdir(parents=True)
    for src in sources:
        shutil.copyfile(src, staged_demo / src.name)
    for new, place in ((staged, FIXTURES / sample_id), (staged_demo, DEMO / sample_id)):
        shutil.rmtree(place, ignore_errors=True)
        new.rename(place)

    fingerprints = json.loads((FIXTURES / "sample_documents.json").read_text(encoding="utf-8"))
    fingerprints[sample_id] = {"org_chart": hashlib.sha256(docs.org_chart).hexdigest(),
                               "policies": [hashlib.sha256(p).hexdigest() for p in docs.policies]}
    (FIXTURES / "sample_documents.json").write_text(json.dumps(fingerprints, indent=2) + "\n", encoding="utf-8")

    samples = json.loads(SAMPLES_JSON.read_text(encoding="utf-8")) if SAMPLES_JSON.exists() else []
    entry = {"id": sample_id, "company": company, "market": market, "industry": industry, "language": language,
             "orgChart": f"{sample_id}/{sources[0].name}", "policies": [f"{sample_id}/{p.name}" for p in sources[1:]]}
    before = next((s for s in samples if s["id"] == sample_id), {})
    if "examples" in before:  # example answers for its forms are written by hand; a new reading keeps them
        entry["examples"] = before["examples"]
    samples = [entry if s["id"] == sample_id else s for s in samples] if before else samples + [entry]
    SAMPLES_JSON.write_text(json.dumps(samples, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nsaved api/fixtures/{sample_id}/, sample_documents.json, web/src/lib/samples.json")


if __name__ == "__main__":
    main()
