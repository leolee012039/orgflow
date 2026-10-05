"""Measure OrgFlow on document pairs it was not tuned on, and write docs/EVAL.md.

Run: uv run --group dev python scripts/eval_documents.py
Uses the live Gemini model (about 3-5 calls per pair). Real documents are
downloaded once into .cache/eval/ and used unchanged.
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
from schemas import PurchaseRequestForm  # noqa: E402

CACHE = ROOT / ".cache" / "eval"
EN = ROOT / "demo_assets" / "en"
ZH = ROOT / "demo_assets" / "zh"


@dataclass
class Pair:
    name: str
    kind: str  # what kind of input this is
    org: str  # local path or URL
    policy: str
    note: str


PAIRS = [
    Pair("NovaGear", "sample, English", str(EN / "NovaGear_Organization_Chart.pdf"),
         str(EN / "NovaGear_Purchasing_Policy.pdf"), "The demo company (fictional)."),
    Pair("NovaGear, scanned", "image-only PDFs", "scanned:NovaGear_Organization_Chart",
         "scanned:NovaGear_Purchasing_Policy", "Same documents rendered as JPEG pages with no text layer."),
    Pair("Xiangying Fitness", "fictional, Traditional Chinese", str(ZH / "Xiangying_Fitness_Org_Chart.pdf"),
         str(ZH / "Xiangying_Fitness_Purchasing_Policy.pdf"),
         "A made-up gym chain with three planted flaws: an approver missing from the org chart, amounts "
         "written in Chinese numerals, and no approval level for exactly NT$100,000."),
    Pair("National Taiwan University", "real, Traditional Chinese",
         "https://ntuinfo.ntu.edu.tw/pdf/p1_2_0_strusys.pdf",
         "https://ga.ntu.edu.tw/main_ch/fileRename/fileRename/123/938/1/7/請購作業規範112.1.7修正.pdf",
         "Organization table (vertical text) and purchase request rules."),
    Pair("National Taitung University", "real, Traditional Chinese",
         "https://law.nttu.edu.tw/var/file/70/1070/img/1828/327627930.pdf",
         "https://dga.nttu.edu.tw/var/file/8/1008/img/715/738540495.pdf",
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


async def evaluate(pair: Pair) -> dict:
    org_pdf, policy_pdf = load(pair.org), load(pair.policy)
    row: dict = {"pair": pair}
    t = time.perf_counter()
    org = await pipeline.analyze_organization(org_pdf, policy_pdf)
    row["org"] = org
    if org.value is None:
        row["total_s"] = time.perf_counter() - t
        return row
    opps = await pipeline.discover_opportunities(org_pdf, policy_pdf, org.value)
    row["opps"] = opps
    if opps.value is None:
        row["total_s"] = time.perf_counter() - t
        return row
    top = opps.value.opportunities[0]
    wf = await pipeline.design_workflow(org_pdf, policy_pdf, org.value, top)
    row["wf"] = wf
    row["total_s"] = time.perf_counter() - t
    if wf.value is not None:
        # Run requests just below, at and above every amount threshold (plain code only)
        amounts = sorted({float(r.when.value) for r in wf.value.rules if isinstance(r.when.value, (int, float))}
                         | {float(f["amount"]) for f in wf.extras.get("amount_gaps", [])})
        probes = sorted({max(a + d, 0) for a in amounts for d in (-1, 0, 1)}) or [1000.0]
        # Requests come from a department whose head is named, if the documents name any
        headed = [d for d in org.value.departments if d.head_role_id]
        dept = (headed or org.value.departments)[0].name if org.value.departments else "Operations"
        outcomes = []
        for amount in probes:
            form = PurchaseRequestForm(requester="Test Requester", department=dept, item="Laptop",
                                       estimated_cost=amount, business_justification="Laptop for a new staff member.")
            trace = await pipeline.run_request(wf.value, org.value, form, top.manual_handoffs, live_review=False)
            outcomes.append(trace.status)
            if trace.status != "COMPLETED" and "first_stop" not in row:
                row["first_stop"] = f"{amount:,.0f}: {trace.steps[-1].reason}"
        row["runs"] = outcomes
        row["requester_department"] = dept
    return row


def fmt_stage(stage) -> str:
    if stage is None:
        return "not reached"
    return f"{stage.origin}, {stage.latency_ms / 1000:.1f} s"


def write_report(rows: list[dict]) -> str:
    lines = [
        "# OrgFlow evaluation on documents it was not tuned on",
        "",
        f"Run on {date.today().isoformat()} with Gemini 3.8 Flash (Vertex AI, location global), "
        "using `scripts/eval_documents.py`. Real documents were downloaded from the public web and used unchanged.",
        "",
        "Origin: **live** = Gemini's first answer passed every check; **repaired** = passed after one "
        "correction; **unverified** = still failing, so OrgFlow showed nothing instead of guessing; "
        "**fixture** = the NovaGear sample's saved answer.",
        "",
        "| Pair | Input | Organization | Opportunities | Workflow | Rules | Gaps found | Requests run |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        p = row["pair"]
        wf = row.get("wf")
        org = row.get("org")
        rules = len(wf.value.rules) if wf and wf.value else "-"
        gaps = "; ".join([f"{g['actor']} ({g['status'].replace('_', ' ')})"
                          for g in (wf.extras.get("gaps", []) if wf else [])]
                         + [f"amount {f['kind']} at {f['amount']:,.0f}"
                            for f in (wf.extras.get("amount_gaps", []) if wf else [])]) or "none"
        runs = row.get("runs")
        runs_txt = f"{len(runs)} (" + ", ".join(f"{s.lower().replace('_', ' ')} ×{runs.count(s)}"
                                               for s in sorted(set(runs))) + ")" if runs else "-"
        org_txt = fmt_stage(org)
        if org and org.value:
            org_txt += f"; {len(org.value.departments)} units, {len(org.value.roles)} roles"
        lines.append(f"| {p.name} | {p.kind} | {org_txt} | {fmt_stage(row.get('opps'))} | "
                     f"{fmt_stage(wf)} | {rules} | {gaps} | {runs_txt} |")

    lines += ["", "## Details", ""]
    for row in rows:
        p = row["pair"]
        lines += [f"### {p.name}", "", p.note, ""]
        if not p.org.startswith(("http", "scanned")):
            lines.append(f"Sources: `{Path(p.org).relative_to(ROOT).as_posix()}` and "
                         f"`{Path(p.policy).relative_to(ROOT).as_posix()}`.")
        elif p.org.startswith("http"):
            lines += [f"- Organization: {p.org}", f"- Policy: {p.policy}"]
        lines.append(f"- Total time for the three AI stages: {row['total_s']:.1f} s")
        if row.get("requester_department"):
            lines.append(f"- Test requests came from: {row['requester_department']}")
        if row.get("first_stop"):
            lines.append(f"- First request that stopped (amount: reason): {row['first_stop']}")
        opps = row.get("opps")
        if opps and opps.value:
            lines.append("- Opportunities found: " + "; ".join(
                f"{o.name}{' (built)' if o.executable else ''}" for o in opps.value.opportunities))
        wf = row.get("wf")
        if wf and wf.value:
            for r in wf.value.rules:
                lines.append(f"- Rule `{r.when.field} {r.when.op} {r.when.value:,}`" if isinstance(r.when.value, (int, float))
                             else f"- Rule `{r.when.field} {r.when.op} {r.when.value}`")
                lines.append(f"  - Policy text: 「{r.source.strip()}」")
            for t in wf.value.amount_tiers:
                ends = (f"up to {t.max:,.0f}" if t.min is None else f"from {t.min:,.0f}" if t.max is None
                        else f"{t.min:,.0f} to {t.max:,.0f}")
                lines.append(f"- Amount level {ends}: 「{t.source.strip()}」")
            for f in wf.extras.get("amount_gaps", []):
                lines.append(f"- Amount {f['kind']} at {f['amount']:,.0f} (found by code): "
                             f"「{f['below'].strip()}」 then 「{f['above'].strip()}」")
        for stage_name in ("org", "opps", "wf"):
            stage = row.get(stage_name)
            if stage and stage.problems:
                lines.append(f"- Checks that failed before the final answer ({stage_name}): "
                             + "; ".join(x[:140] for x in stage.problems[:3]))
        lines.append("")
    return "\n".join(lines) + "\n"


async def main() -> None:
    rows = []
    for pair in PAIRS:
        print(f"evaluating {pair.name} ...", flush=True)
        rows.append(await evaluate(pair))
    report = write_report(rows)
    (ROOT / "docs" / "EVAL.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    asyncio.run(main())
