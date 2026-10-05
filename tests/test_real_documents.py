"""Fixes from running real documents (NTU, NCUE, NTTU policies): see docs/ISSUES.md.

No test here calls Gemini.
"""

import asyncio
import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
import pipeline
from agents import organization_analyst, workflow_architect
from agents.runtime import AgentResult
from guard import (
    check_rule_numbers,
    extract_numbers,
    extract_pdf_text,
    load_fixture,
    validate_organization_output,
    validate_workflow_output,
    verify_quote_in_text,
)
from runner import run_workflow
from sample_docs import DOC_TEXT, DOCS, OPERATIONS, ORG_PDF, POLICY_PDFS, PURCHASING_PDF, planned, upload_files
from schemas import Organization, Workflow

OTHER_ORG_PDF = ORG_PDF + b"\n% another company's file\n"  # same text, different bytes: not the sample
OTHER_DOCS = pipeline.Docs(OTHER_ORG_PDF, POLICY_PDFS)


# --- Amounts in Chinese policies ---------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("採購金額超過新台幣50,000元者", ["50000"]),
    ("5萬元以下", ["50000"]),
    ("新臺幣五萬元以下", ["50000"]),
    ("逾新臺幣十五萬元", ["150000"]),
    ("新臺幣一百萬元", ["1000000"]),
    ("財物採購為 5 千萬元以上", ["50000000"]),
    ("未達 200 萬元由總務長決行", ["2000000"]),
    ("新臺幣三千元", ["3000"]),
    ("USD 1,000 - USD 5,000", ["1000", "5000"]),
    ("一級主管代為決行", []),
])
def test_amounts_are_read_in_any_format(text, expected):
    assert extract_numbers(text) == expected


def test_rule_value_matches_amount_written_in_wan():
    wf = Workflow.model_validate(load_fixture("workflow_fixture.json"))
    wf.rules[0].when.value = 300000
    wf.rules[0].source = "院系所未逾 30 萬元之請購：由請購單位主管核定"
    wf.rules[1].when.value = 2000000
    wf.rules[1].source = "200 萬元以上應經校長核定"
    assert check_rule_numbers(wf) == []


# --- Organizations that list units without heads ------------------------------------

def test_department_without_named_head_is_accepted():
    data = copy.deepcopy(load_fixture("novagear/organization.json"))
    data["departments"][0]["head_role_id"] = None  # Sales: unit listed, head not named
    org, problems = validate_organization_output(data, DOC_TEXT)
    assert problems == [] and org is not None


def test_requester_manager_without_head_goes_to_a_person():
    data = copy.deepcopy(load_fixture("novagear/organization.json"))
    data["departments"][1]["head_role_id"] = None  # Operations
    org = Organization.model_validate(data)
    wf = Workflow.model_validate(load_fixture("workflow_fixture.json"))
    trace = run_workflow(wf, org, {"requester": "Emma Chen", "department": "Operations", "item": "Laptop",
                                   "estimated_cost": 2400, "business_justification": "New designer needs a laptop."})
    assert trace.status == "NEEDS_HUMAN_REVIEW"
    assert "names no head" in trace.steps[-1].reason


def test_workflow_without_rules_is_rejected_when_policy_has_amounts():
    data = copy.deepcopy(load_fixture("workflow_fixture.json"))
    data["rules"] = []
    for step in data["steps"]:
        step["only_if"] = None
    org = Organization.model_validate(load_fixture("novagear/organization.json"))
    wf, problems = validate_workflow_output(data, org, DOC_TEXT)
    assert wf is None
    assert any("no rules" in p for p in problems)


# --- Someone else's documents never come back as NovaGear ---------------------------

def _always_invalid(monkeypatch):
    async def bad(*args):
        return AgentResult({"company": "x"}, None, 10)
    monkeypatch.setattr(organization_analyst, "analyze", bad)
    monkeypatch.setattr(organization_analyst, "repair", bad)


def test_sample_documents_fall_back_to_the_fixture(monkeypatch):
    _always_invalid(monkeypatch)
    result = asyncio.run(pipeline.analyze_organization(DOCS))
    assert result.origin == "fixture" and result.value.company == "NovaGear Inc."


def test_other_documents_are_unverified_not_novagear(monkeypatch):
    _always_invalid(monkeypatch)
    result = asyncio.run(pipeline.analyze_organization(OTHER_DOCS))
    assert result.origin == "unverified" and result.value is None
    assert result.problems


def test_api_says_plainly_when_it_could_not_verify(monkeypatch):
    _always_invalid(monkeypatch)
    resp = TestClient(main.app).post("/api/analyze", files=upload_files(org_pdf=OTHER_ORG_PDF))
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "shows nothing instead of guessing" in detail["message"]
    assert detail["problems"]


# --- Gaps: missing approver vs. possible match ---------------------------------------

def test_director_is_a_missing_approver_in_novagear():
    wf = Workflow.model_validate(load_fixture("workflow_fixture.json"))
    gaps = pipeline.find_gaps(wf, extract_pdf_text(ORG_PDF))
    assert gaps == [{
        "actor": "Director",
        "status": "missing",
        "step_id": "director_approval",
        "policy_quote": "Above USD 5,000  Manager approval + Finance validation + Director approval",
    }]


def test_approver_named_in_the_org_chart_is_only_a_possible_match():
    wf = Workflow.model_validate(load_fixture("workflow_fixture.json"))
    # NTU's org table is extracted one character per line
    org_chart_text = "表 1:國立臺灣大學組織架構表\n人\n事\n室\n主\n計\n室\n稽\n核\n室"
    wf.unresolved_actors = ["主計室"]
    wf.steps[3].actor = "主計室"
    gaps = pipeline.find_gaps(wf, org_chart_text)
    assert gaps[0]["status"] == "possible_match"


def test_build_endpoint_returns_gaps(monkeypatch):
    async def fake(*args):
        return AgentResult(load_fixture(f"novagear/workflows/{OPERATIONS}.json"), None, 6000)
    monkeypatch.setattr(workflow_architect, "design", fake)
    resp = TestClient(main.app).post("/api/build", files=upload_files(), data={
        "organization": json.dumps(load_fixture("novagear/organization.json")),
        "planned": json.dumps(planned(OPERATIONS).model_dump())})
    assert resp.status_code == 200
    assert resp.json()["gaps"][0]["actor"] == "Director"


# --- Vertical org charts and units as approvers ---------------------------------------

def test_vertical_text_still_grounds_unit_names():
    from guard import verify_quote_in_text
    vertical = "社\n會\n科\n學\n院(4\n系 3\n所)\n公\n共\n衛\n生\n學\n院"
    assert verify_quote_in_text("社會科學院", vertical)
    assert verify_quote_in_text("公共衛生學院", vertical)
    assert not verify_quote_in_text("藝術學院", vertical)


def test_a_department_can_approve_as_a_unit():
    org = Organization.model_validate(load_fixture("novagear/organization.json"))
    data = copy.deepcopy(load_fixture("workflow_fixture.json"))
    data["steps"][2]["actor"] = "Finance"  # "the finance department validates"
    wf, problems = validate_workflow_output(data, org, DOC_TEXT)
    assert problems == [] and wf is not None
    trace = run_workflow(wf, org, {"requester": "Emma Chen", "department": "Operations", "item": "Laptop",
                                   "estimated_cost": 2400, "business_justification": "New designer needs a laptop."})
    finance = next(s for s in trace.steps if s.step_id == "finance_validation")
    assert finance.result == "PASSED" and "Finance" in finance.reason


# --- Scanned PDFs: no text layer, so Gemini transcribes once for the guard ----------

def _image_only_pdf() -> bytes:
    import io
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.rect(72, 72, 300, 200)  # a drawing, no text layer
    c.showPage()
    c.save()
    return buf.getvalue()


def test_scanned_pdf_is_transcribed_once(monkeypatch):
    from agents import document_reader
    calls = []

    async def fake_transcribe(pdf):
        calls.append(pdf)
        return AgentResult({"text": "Purchasing Policy\nAbove USD 5,000 Director approval"}, None, 900)

    monkeypatch.setattr(document_reader, "transcribe", fake_transcribe)
    monkeypatch.setattr(pipeline, "_TRANSCRIPTS", {})
    scanned = _image_only_pdf()
    first = asyncio.run(pipeline.document_text(scanned))
    second = asyncio.run(pipeline.document_text(scanned))
    assert "Director approval" in first and first == second
    assert len(calls) == 1


def test_text_pdf_is_not_transcribed(monkeypatch):
    from agents import document_reader

    async def boom(pdf):
        raise AssertionError("must not transcribe a PDF that has text")

    monkeypatch.setattr(document_reader, "transcribe", boom)
    assert "Purchasing Policy" in asyncio.run(pipeline.document_text(PURCHASING_PDF))


def test_look_alike_characters_in_a_pdf_still_match_the_quote():
    # A real university PDF stores 行 and 立 as CJK compatibility ideographs (U+F914, U+F9F7)
    doc_text = "國\uf9f7彰化師範大學組織規程\n本大學設下列各\uf914政單位"
    assert verify_quote_in_text("本大學設下列各行政單位", doc_text)
    assert extract_numbers("預算金額新臺幣５０萬元以下") == ["500000"]
    # List markers stay apart from the amount after them
    assert extract_numbers("\u24605萬元以下") == ["50000"]
    assert extract_numbers("\u24885萬元以下") == ["50000"]
