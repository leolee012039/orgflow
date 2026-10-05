"""Measure OrgFlow on companies it was not tuned on, and write docs/EVAL.md.

Run: uv run --group dev --with pymupdf python scripts/eval_documents.py [name ...]
With names, only those companies run and docs/EVAL.md is left alone. Uses the live
Gemini model (about 8-12 calls per company). Real documents are downloaded once into
.cache/eval/ and used unchanged.
"""

import asyncio
import io
import os
import sys
import time
import hashlib
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
os.environ.pop("ORGFLOW_DEV_CACHE", None)

import pipeline  # noqa: E402
import runner  # noqa: E402
from schemas import RequestForm  # noqa: E402

CACHE = ROOT / ".cache" / "eval"
EN = ROOT / "demo_assets" / "en"
ZH = ROOT / "demo_assets" / "zh"
NOVAGEAR_POLICIES = ["Purchasing_Policy", "Procurement_Payment_Procedures", "Sales_Discount_Policy"]


@dataclass
class Pair:
    name: str
    kind: str  # what kind of input this is
    org: str  # local path or URL
    policies: list[str]
    note: str


PAIRS = [
    Pair("NovaGear", "sample, English, 3 policies", str(EN / "NovaGear_Organization_Chart.pdf"),
         [str(EN / f"NovaGear_{n}.pdf") for n in NOVAGEAR_POLICIES], "The demo company (fictional)."),
    Pair("NovaGear, scanned", "image-only PDFs", "scanned:NovaGear_Organization_Chart",
         [f"scanned:NovaGear_{n}" for n in NOVAGEAR_POLICIES],
         "Same documents rendered as JPEG pages with no text layer."),
    Pair("Xiangying Fitness", "fictional, Traditional Chinese", str(ZH / "Xiangying_Fitness_Org_Chart.pdf"),
         [str(ZH / "Xiangying_Fitness_Purchasing_Policy.pdf")],
         "A made-up gym chain with three planted flaws: an approver missing from the org chart, amounts "
         "written in Chinese numerals, and no approval level for exactly NT$100,000."),
    Pair("National Taiwan University", "real, Traditional Chinese",
         "https://ntuinfo.ntu.edu.tw/pdf/p1_2_0_strusys.pdf",
         ["https://ga.ntu.edu.tw/main_ch/fileRename/fileRename/123/938/1/7/請購作業規範112.1.7修正.pdf"],
         "Organization table (vertical text) and purchase request rules."),
    Pair("National Taitung University", "real, Traditional Chinese",
         "https://law.nttu.edu.tw/var/file/70/1070/img/1828/327627930.pdf",
         ["https://dga.nttu.edu.tw/var/file/8/1008/img/715/738540495.pdf"],
         "Organization regulations (18 pages) and procurement rules with amounts in Chinese numerals."),
]


def scanned(name: str) -> bytes:
    import pymupdf  # dev-only: uv run --with pymupdf

    src = pymupdf.open(EN / f"{name}.pdf")
    out = pymupdf.open()
    for page in src:
        pix = page.get_pixmap(dpi=150)
        new = out.new_page(width=page.rect.width, height=page.rect.height)
        new.insert_image(new.rect, stream=pix.tobytes("jpeg", jpg_quality=80))
    buf = io.BytesIO()
    out.save(buf, deflate=True)
    return buf.getvalue()


def load(source: str) -> bytes:
    if source.startswith("scanned:"):
        return scanned(source.split(":", 1)[1])
    if not source.startswith("http"):
        return Path(source).read_bytes()
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / (hashlib.sha1(source.encode()).hexdigest()[:16] + ".pdf")
    if not target.exists():
        req = urllib.request.Request(urllib.parse.quote(source, safe=":/?=&%"), headers={"User-Agent": "Mozilla/5.0"})
        target.write_bytes(urllib.request.urlopen(req, timeout=60).read())
    return target.read_bytes()


def build_order(plan: list) -> list:
    """What "Build all" builds in the web app: each department's first workflow, the workflows they start
    from and the workflows that pick up their results, upstream first (web/src/lib/chain.ts)."""
    def upstream(c):
        return next((w for w in plan if c.starts_from and w.department == c.starts_from and w.hands_to == c.department), None)

    def downstream(c):
        return next((w for w in plan if c.hands_to and w.department == c.hands_to and w.starts_from == c.department), None)

    wanted: dict = {}

    def add(c, seen):
        if c.id in wanted or c.id in seen:
            return
        seen.add(c.id)
        up = upstream(c)
        if up:
            add(up, seen)
        wanted[c.id] = c
        down = downstream(c)
        if down:
            add(down, seen)

    first: dict = {}
    for w in plan:
        first.setdefault(w.department, w)
    for w in first.values():
        add(w, set())
    return list(wanted.values())


EXAMPLES = {"business_justification": "Replacement equipment needed for daily operations of the team.",
            "reason": "Annual renewal for a key account that orders every quarter."}


def case_values(wf, number: float) -> dict:
    values = {}
    for f in pipeline.fields_of(wf):
        if f.type == "number":
            values[f.name] = number
        elif f.type == "choice":
            values[f.name] = f.options[0] if f.options else ""
        else:
            values[f.name] = EXAMPLES.get(f.name, f"Sample {f.label}")
    return values


async def evaluate(pair: Pair) -> dict:
    docs = pipeline.Docs(load(pair.org), [load(p) for p in pair.policies])
    row: dict = {"pair": pair, "built": {}}
    t = time.perf_counter()
    org = await pipeline.analyze_organization(docs)
    row["org"] = org
    if org.value is not None:
        dmap = await pipeline.map_departments(docs, org.value)
        row["map"] = dmap
        if dmap.value is not None:
            plan = await pipeline.plan_workflows(docs, org.value, dmap.value)
            row["plan"] = plan
            if plan.value is not None:
                for c in build_order(plan.value.workflows):
                    up_c = next((w for w in plan.value.workflows if c.starts_from and w.department == c.starts_from
                                 and w.hands_to == c.department), None)
                    upstream = row["built"].get(up_c.id).value if up_c and up_c.id in row["built"] else None
                    if up_c is not None and upstream is None:
                        continue  # its upstream failed to build
                    row["built"][c.id] = await pipeline.build_workflow(docs, org.value, c, upstream)
    row["total_s"] = time.perf_counter() - t

    # Cases: every start point, at amounts just below, at and above each threshold and gap (plain code only)
    built = {k: r.value for k, r in row["built"].items() if r.value is not None}
    workflows = list(built.values())
    row["chains"], row["runs"] = [], []
    for wf in workflows:
        if wf.starts_from and any(w.department == wf.starts_from and w.hands_to == wf.department for w in workflows):
            continue
        path = [wf.department]
        current = wf
        while (nxt := runner.next_workflow(current, workflows)) is not None and nxt.department not in path:
            path.append(nxt.department)
            current = nxt
        row["chains"].append(" → ".join(path))
        numbers = sorted({float(r.when.value) for r in wf.rules if isinstance(r.when.value, (int, float))}
                         | {float(g["amount"]) for g in row["built"][wf.opportunity_id].extras.get("amount_gaps", [])})
        probes = sorted({max(n + d, 0) for n in numbers for d in (-1, 0, 1)}) or [1000.0]
        for n in probes:
            form = RequestForm(request_id="EVAL", requester="Test Requester", department=wf.department,
                               **case_values(wf, n))
            trace = await pipeline.run_chain_request(workflows, org.value, wf.opportunity_id, form, live_review=False)
            row["runs"].append(trace.status)
            if trace.status != "COMPLETED" and "first_stop" not in row:
                leg = trace.legs[-1]
                row["first_stop"] = f"{wf.workflow_name} at {n:,.0f}: {leg.department}, {leg.trace.steps[-1].reason}"
    return row


def fmt_stage(stage) -> str:
    if stage is None:
        return "not reached"
    return f"{stage.origin}, {stage.latency_ms / 1000:.1f} s"


def findings_of(row: dict) -> list[str]:
    out = []
    for r in row["built"].values():
        if r.value is None:
            continue
        out += [f"{g['actor']} missing in {r.value.department}" if g["status"] == "missing"
                else f"{g['actor']} to confirm in {r.value.department}" for g in r.extras.get("gaps", [])]
        out += [f"{g['kind']} at {g['amount']:,.0f} ({g['field']}) in {r.value.department}"
                for g in r.extras.get("amount_gaps", [])]
    return out


def write_report(rows: list[dict]) -> str:
    lines = [
        "# OrgFlow evaluation on documents it was not tuned on",
        "",
        f"Run on {date.today().isoformat()} with Gemini 3.8 Flash (Vertex AI, location global), "
        "using `scripts/eval_documents.py`. Real documents were downloaded from the public web and used unchanged.",
        "",
        "Each company goes through every stage the web app runs: the organization, the department map (what each "
        "department does and hands to the others), the plan (1-3 workflows per department), then every workflow "
        "\"Build all linked workflows\" would build. Cases then run from every start point across departments, at "
        "amounts just below, at and above each threshold.",
        "",
        "Origin: **live** = Gemini's first answer passed every check; **repaired** = passed after one "
        "correction; **unverified** = still failing, so OrgFlow showed nothing instead of guessing; "
        "**fixture** = the NovaGear sample's saved answer.",
        "",
        "| Company | Input | Organization | Department map | Plan | Workflows built | Problems found | Chains | Cases run |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        p = row["pair"]
        org, dmap, plan = row.get("org"), row.get("map"), row.get("plan")
        org_txt = fmt_stage(org) + (f"; {len(org.value.departments)} units, {len(org.value.roles)} roles"
                                    if org and org.value else "")
        map_txt = fmt_stage(dmap) + (f"; {len(dmap.value.departments)} departments, {len(dmap.value.handoffs)} handoffs"
                                     if dmap and dmap.value else "")
        plan_txt = fmt_stage(plan) + (f"; {len(plan.value.workflows)} workflows" if plan and plan.value else "")
        builds = list(row["built"].values())
        origins = [b.origin for b in builds]
        built_txt = (f"{sum(b.value is not None for b in builds)} of {len(builds)} ("
                     + ", ".join(f"{o} ×{origins.count(o)}" for o in sorted(set(origins))) + ")") if builds else "-"
        runs = row["runs"]
        runs_txt = (f"{len(runs)} (" + ", ".join(f"{s.lower().replace('_', ' ')} ×{runs.count(s)}"
                                                 for s in sorted(set(runs))) + ")") if runs else "-"
        lines.append(f"| {p.name} | {p.kind} | {org_txt} | {map_txt} | {plan_txt} | {built_txt} | "
                     f"{'; '.join(findings_of(row)) or 'none'} | {'; '.join(row['chains']) or '-'} | {runs_txt} |")

    lines += ["", "## Details", ""]
    for row in rows:
        p = row["pair"]
        lines += [f"### {p.name}", "", p.note, ""]
        if p.org.startswith("http"):
            lines += [f"- Organization: {p.org}", *(f"- Policy: {x}" for x in p.policies)]
        elif not p.org.startswith("scanned"):
            files = [Path(p.org), *map(Path, p.policies)]
            lines.append("Sources: " + ", ".join(f"`{f.relative_to(ROOT).as_posix()}`" for f in files) + ".")
        lines.append(f"- Total time for every AI stage and build: {row['total_s']:.1f} s")
        dmap = row.get("map")
        if dmap and dmap.value:
            for d in dmap.value.departments:
                lines.append(f"- **{d.name}**: {d.summary}")
            for h in dmap.value.handoffs:
                lines.append(f"  - Handoff {h.from_dept} → {h.to}: {h.what}. 「{h.evidence.quote.strip()}」")
        plan = row.get("plan")
        if plan and plan.value:
            for w in plan.value.workflows:
                link = (f", starts from {w.starts_from}" if w.starts_from else "") + (f", hands to {w.hands_to}" if w.hands_to else "")
                result = row["built"].get(w.id)
                status = f"built ({result.origin})" if result and result.value else (f"not built ({result.origin})" if result else "not built")
                lines.append(f"- Planned in {w.department}: {w.name} ({w.basis}{link}): {status}")
        for f in findings_of(row):
            lines.append(f"- Found by code: {f}")
        if row.get("first_stop"):
            lines.append(f"- First case that stopped: {row['first_stop']}")
        for name in ("org", "map", "plan"):
            stage = row.get(name)
            if stage and stage.problems:
                lines.append(f"- Checks that failed before the final answer ({name}): "
                             + "; ".join(x[:140] for x in stage.problems[:3]))
        for key, r in row["built"].items():
            if r.problems:
                lines.append(f"- Checks that failed before the final answer (build {key}): "
                             + "; ".join(x[:140] for x in r.problems[:2]))
        lines.append("")
    return "\n".join(lines) + "\n"


async def main() -> None:
    rows = []
    only = [a.lower() for a in sys.argv[1:]]
    for pair in PAIRS:
        if only and not any(o in pair.name.lower() for o in only):
            continue
        print(f"evaluating {pair.name} ...", flush=True)
        rows.append(await evaluate(pair))
    report = write_report(rows)
    if not only:
        (ROOT / "docs" / "EVAL.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    asyncio.run(main())
