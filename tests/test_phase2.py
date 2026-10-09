"""Phase 2: clean demo PDFs, quote grounding, organization guard, guarded stage, /api/analyze.

No test here calls Gemini: agent calls are replaced with fakes.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

import main
import pipeline
from agents import organization_analyst
from agents.runtime import AgentResult
from guard import extract_pdf_text, load_fixture, validate_organization_output, verify_quote_in_text
from sample_docs import (
    DOC_TEXT,
    DOCS,
    ORG_PDF,
    ORG_TEXT,
    POLICY_NAMES,
    POLICY_PDFS,
    PURCHASING_PDF,
    ROOT,
    fixture,
    upload_files,
)

POLICY_TEXT = extract_pdf_text(PURCHASING_PDF)


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
    for name, pdf in zip(POLICY_NAMES, POLICY_PDFS):
        assert (web / name).read_bytes() == pdf


def test_the_sample_is_recognized_only_with_all_its_policies_in_order():
    assert pipeline.sample_name(DOCS) == "novagear"
    assert pipeline.sample_name(pipeline.Docs(ORG_PDF, POLICY_PDFS[:1])) is None
    assert pipeline.sample_name(pipeline.Docs(ORG_PDF, POLICY_PDFS[::-1])) is None


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
    ("novagear/organization.json", lambda d: [r["evidence"]["quote"] for r in d["relationships"]]),
    ("novagear/department_map.json", lambda d: [w["evidence"]["quote"] for p in d["departments"] for w in p["work"]]
     + [h["evidence"]["quote"] for h in d["handoffs"]]),
    ("novagear/workflow_plan.json", lambda d: [e["quote"] for w in d["workflows"] for e in w["evidence"]]),
    ("workflow_fixture.json", lambda d: [r["source"] for r in d["rules"]]),
])
def test_fixture_quotes_ground_in_clean_pdfs(name, quotes):
    for quote in quotes(load_fixture(name)):
        assert verify_quote_in_text(quote, DOC_TEXT), quote


# --- Organization guard ----------------------------------------------------------

def _org() -> dict:
    return fixture("organization.json")


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
                          "reports_to": data["roles"][0]["id"], "responsibilities": []})
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
    result, calls = _stage([AgentResult(None, "timed out after 25s", 25000, unavailable=True),
                            AgentResult(_org(), None, 10)])
    assert result.origin == "fixture"
    assert calls == ["first"]


def test_a_gemini_error_skips_repair_and_says_gemini_is_unavailable():
    # 6-8 Oct: Gemini answered 400 to every build, the repair failed the same way, and the page blamed the PDFs
    error = AgentResult(None, "ClientError: 400 INVALID_ARGUMENT", 300, unavailable=True)
    first, repair, calls = _fake([error, AgentResult(_org(), None, 10)])
    result = asyncio.run(pipeline.run_guarded_stage(
        stage="organization", first_call=first, repair_call=repair,
        validate=lambda d: validate_organization_output(d, DOC_TEXT), fixture=None))
    assert calls == ["first"]
    assert result.value is None and result.unavailable


def test_an_answer_that_fails_the_checks_is_not_called_unavailable():
    result, _ = _stage([AgentResult(None, "model returned invalid JSON", 10), AgentResult({"company": "x"}, None, 10)])
    assert not result.unavailable


# --- /api/analyze -----------------------------------------------------------------

client = TestClient(main.app)


def test_analyze_endpoint_reads_every_policy(monkeypatch):
    async def fake_analyze(docs):
        assert [label for label, _ in docs] == ["org_chart", "policy_1", "policy_2", "policy_3"]
        assert docs[0][1] == ORG_PDF and [pdf for _, pdf in docs[1:]] == POLICY_PDFS
        return AgentResult(_org(), None, 8000)

    monkeypatch.setattr(organization_analyst, "analyze", fake_analyze)
    resp = client.post("/api/analyze", files=upload_files())
    assert resp.status_code == 200
    body = resp.json()
    assert body["origin"] == "live"
    assert body["latency_ms"] == 8000
    assert len(body["departments"]) == 4


def test_an_org_chart_alone_is_enough(monkeypatch):
    async def fake_analyze(docs):
        assert [label for label, _ in docs] == ["org_chart"]
        data = _org()
        data["relationships"] = []  # their quotes come from the policies, which aren't uploaded here
        return AgentResult(data, None, 10)

    monkeypatch.setattr(organization_analyst, "analyze", fake_analyze)
    resp = client.post("/api/analyze", files=upload_files(policies=[]))
    assert resp.status_code == 200 and resp.json()["origin"] == "live"


def test_analyze_endpoint_rejects_non_pdf():
    resp = client.post("/api/analyze", files=upload_files(org_pdf=b"hello, not a pdf"))
    assert resp.status_code == 415
    assert "not a PDF" in resp.json()["detail"]


def test_analyze_endpoint_rejects_large_pdf():
    resp = client.post("/api/analyze", files=upload_files(policies=[b"%PDF-" + b"0" * (5 * 1024 * 1024)]))
    assert resp.status_code == 413


def test_analyze_endpoint_limits_the_number_of_policies():
    resp = client.post("/api/analyze", files=upload_files(policies=[PURCHASING_PDF] * 6))
    assert resp.status_code == 413
    assert "at most 5" in resp.json()["detail"]
