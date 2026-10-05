"""Phase 2: clean demo PDFs, quote grounding, organization guard, guarded stage, /api/analyze.

No test here calls Gemini: agent calls are replaced with fakes.
"""

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
import pipeline
from agents import organization_analyst
from agents.runtime import AgentResult
from guard import extract_pdf_text, load_fixture, validate_organization_output, verify_quote_in_text

ROOT = Path(__file__).resolve().parent.parent
EN = ROOT / "demo_assets" / "en"
ORG_PDF = (EN / "NovaGear_Organization_Chart.pdf").read_bytes()
POLICY_PDF = (EN / "NovaGear_Purchasing_Policy.pdf").read_bytes()
ORG_TEXT = extract_pdf_text(ORG_PDF)
POLICY_TEXT = extract_pdf_text(POLICY_PDF)
DOC_TEXT = ORG_TEXT + "\n" + POLICY_TEXT


# --- Clean demo PDFs -----------------------------------------------------------

def test_org_chart_does_not_give_away_the_flow():
    lowered = ORG_TEXT.lower()
    assert "director" not in lowered  # the policy's Director must stay unresolved
    assert "primary demo flow" not in lowered
    assert "cross-functional" not in lowered
    assert "1,000" not in ORG_TEXT and "5,000" not in ORG_TEXT


def test_policy_keeps_rules_but_not_the_answer():
    assert "Decision Examples" not in POLICY_TEXT
    assert "OrgFlow" not in POLICY_TEXT
    assert "2,400" not in POLICY_TEXT
    for quote in [
        "Below USD 1,000 Manager approval",
        "USD 1,000 - USD 5,000 Manager approval + Finance validation",
        "Above USD 5,000 Manager approval + Finance validation + Director approval",
    ]:
        assert verify_quote_in_text(quote, POLICY_TEXT), quote


def test_web_copies_match_demo_assets():
    web = ROOT / "web" / "public" / "demo"
    assert (web / "NovaGear_Organization_Chart.pdf").read_bytes() == ORG_PDF
    assert (web / "NovaGear_Purchasing_Policy.pdf").read_bytes() == POLICY_PDF


# --- Check 3: quotes must come from the documents ------------------------------

def test_quote_exact_english_passes():
    assert verify_quote_in_text(
        "Requests missing required information must not proceed to approval.", POLICY_TEXT)


def test_quote_scrambled_chinese_passes():
    # pypdf extracts the zh-TW policy line in this scrambled order
    extracted = "金額介於 至 USD 1,000 USD 5,000\n需要：\n直屬經理核准（Manager Approval）"
    assert verify_quote_in_text("金額介於 USD 1,000 至 USD 5,000", extracted)


def test_quote_invented_fails():
    assert not verify_quote_in_text("Purchases above USD 20,000 require Board approval.", DOC_TEXT)
    assert not verify_quote_in_text("All laptops must be ordered from approved vendors.", DOC_TEXT)


@pytest.mark.parametrize("name,quotes", [
    ("organization_fixture.json", lambda d: [r["evidence"]["quote"] for r in d["relationships"]]),
    ("opportunities_fixture.json", lambda d: [e["quote"] for o in d["opportunities"] for e in o["evidence"]]),
    ("workflow_fixture.json", lambda d: [r["source"] for r in d["rules"]]),
])
def test_fixture_quotes_ground_in_clean_pdfs(name, quotes):
    for quote in quotes(load_fixture(name)):
        assert verify_quote_in_text(quote, DOC_TEXT), quote


# --- Organization guard ----------------------------------------------------------

def _org() -> dict:
    return json.loads(json.dumps(load_fixture("organization_fixture.json")))


def test_fixture_organization_passes_full_guard():
    org, problems = validate_organization_output(_org(), DOC_TEXT)
    assert problems == []
    assert org is not None


def test_guard_rejects_broken_reporting_lines():
    data = _org()
    data["departments"][0]["head_role_id"] = "chief_revenue_officer"
    data["roles"][1]["reports_to"] = "vp_sales"
    org, problems = validate_organization_output(data, DOC_TEXT)
    assert org is None
    assert any("head_role_id" in p for p in problems)
    assert any("reports_to" in p for p in problems)


def test_guard_rejects_invented_role():
    data = _org()
    data["roles"].append({"id": "director", "title": "Purchasing Director", "department": "Procurement",
                          "reports_to": "ceo", "responsibilities": []})
    org, problems = validate_organization_output(data, DOC_TEXT)
    assert org is None
    assert any("Purchasing Director" in p for p in problems)


# --- Guarded stage: live → repair → fixture -------------------------------------

def _fake(results: list[AgentResult]):
    calls = []

    async def first():
        calls.append("first")
        return results[0]

    async def repair(previous, problems):
        calls.append(("repair", tuple(problems)))
        return results[1]

    return first, repair, calls


def _stage(results):
    first, repair, calls = _fake(results)
    result = asyncio.run(pipeline.run_guarded_stage(
        stage="organization", first_call=first, repair_call=repair,
        validate=lambda d: validate_organization_output(d, DOC_TEXT),
        fixture=lambda: "FIXTURE",
    ))
    return result, calls


def test_stage_live():
    result, calls = _stage([AgentResult(_org(), None, 10)])
    assert result.origin == "live" and calls == ["first"]


def test_stage_repaired_after_bad_answer():
    bad = _org()
    bad["roles"].append({"id": "x", "title": "Chief Happiness Officer", "department": None,
                         "reports_to": None, "responsibilities": []})
    result, calls = _stage([AgentResult(bad, None, 10), AgentResult(_org(), None, 12)])
    assert result.origin == "repaired"
    assert result.latency_ms == 22
    assert "Chief Happiness Officer" in calls[1][1][0]


def test_stage_fixture_when_repair_also_fails():
    result, _ = _stage([AgentResult(None, "model returned invalid JSON", 10),
                        AgentResult({"company": "x"}, None, 10)])
    assert result.origin == "fixture" and result.value == "FIXTURE"


def test_stage_timeout_skips_repair():
    result, calls = _stage([AgentResult(None, "timed out after 25s", 25000),
                            AgentResult(_org(), None, 10)])
    assert result.origin == "fixture"
    assert calls == ["first"]


# --- /api/analyze -----------------------------------------------------------------

client = TestClient(main.app)


def _upload(org=ORG_PDF, policy=POLICY_PDF):
    return client.post("/api/analyze", files={
        "org_chart": ("org.pdf", org, "application/pdf"),
        "policy": ("policy.pdf", policy, "application/pdf"),
    })


def test_analyze_endpoint_returns_live_organization(monkeypatch):
    async def fake_analyze(org_pdf, policy_pdf):
        assert org_pdf == ORG_PDF and policy_pdf == POLICY_PDF
        return AgentResult(_org(), None, 8000)

    monkeypatch.setattr(organization_analyst, "analyze", fake_analyze)
    resp = _upload()
    assert resp.status_code == 200
    body = resp.json()
    assert body["origin"] == "live"
    assert body["latency_ms"] == 8000
    assert len(body["departments"]) == 4
    assert body["relationships"][0]["from"] == "Operations"


def test_analyze_endpoint_rejects_non_pdf():
    resp = _upload(org=b"hello, not a pdf")
    assert resp.status_code == 415
    assert "not a PDF" in resp.json()["detail"]


def test_analyze_endpoint_rejects_large_pdf():
    resp = _upload(policy=b"%PDF-" + b"0" * (5 * 1024 * 1024))
    assert resp.status_code == 413
