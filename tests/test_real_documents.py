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
)
from runner import run_workflow
from schemas import Organization, Workflow

ROOT = Path(__file__).resolve().parent.parent
EN = ROOT / "demo_assets" / "en"
ORG_PDF = (EN / "NovaGear_Organization_Chart.pdf").read_bytes()
POLICY_PDF = (EN / "NovaGear_Purchasing_Policy.pdf").read_bytes()
OTHER_ORG_PDF = ORG_PDF + b"\n% another company's file\n"  # same text, different bytes: not the sample
DOC_TEXT = extract_pdf_text(ORG_PDF) + "\n" + extract_pdf_text(POLICY_PDF)


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
    data = copy.deepcopy(load_fixture("organization_fixture.json"))
    data["departments"][0]["head_role_id"] = None  # Sales: unit listed, head not named
    org, problems = validate_organization_output(data, DOC_TEXT)
    assert problems == [] and org is not None


def test_requester_manager_without_head_goes_to_a_person():
    data = copy.deepcopy(load_fixture("organization_fixture.json"))
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
    org = Organization.model_validate(load_fixture("organization_fixture.json"))
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
    result = asyncio.run(pipeline.analyze_organization(ORG_PDF, POLICY_PDF))
    assert result.origin == "fixture" and result.value.company == "NovaGear Inc."


def test_other_documents_are_unverified_not_novagear(monkeypatch):
    _always_invalid(monkeypatch)
    result = asyncio.run(pipeline.analyze_organization(OTHER_ORG_PDF, POLICY_PDF))
    assert result.origin == "unverified" and result.value is None
    assert result.problems


def test_api_says_plainly_when_it_could_not_verify(monkeypatch):
    _always_invalid(monkeypatch)
    resp = TestClient(main.app).post("/api/analyze", files={
        "org_chart": ("org.pdf", OTHER_ORG_PDF, "application/pdf"),
        "policy": ("policy.pdf", POLICY_PDF, "application/pdf"),
    })
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


def test_workflow_endpoint_returns_gaps(monkeypatch):
    async def fake(*args):
        return AgentResult(load_fixture("workflow_fixture.json"), None, 6000)
    monkeypatch.setattr(workflow_architect, "design", fake)
    opp = load_fixture("opportunities_fixture.json")["opportunities"][0]
    resp = TestClient(main.app).post("/api/workflow", files={
        "org_chart": ("org.pdf", ORG_PDF, "application/pdf"),
        "policy": ("policy.pdf", POLICY_PDF, "application/pdf"),
    }, data={"organization": json.dumps(load_fixture("organization_fixture.json")), "opportunity": json.dumps(opp)})
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
    org = Organization.model_validate(load_fixture("organization_fixture.json"))
    data = copy.deepcopy(load_fixture("workflow_fixture.json"))
    data["steps"][2]["actor"] = "Finance"  # "the finance department validates"
    wf, problems = validate_workflow_output(data, org, DOC_TEXT)
    assert problems == [] and wf is not None
    trace = run_workflow(wf, org, {"requester": "Emma Chen", "department": "Operations", "item": "Laptop",
                                   "estimated_cost": 2400, "business_justification": "New designer needs a laptop."})
    finance = next(s for s in trace.steps if s.step_id == "finance_validation")
    assert finance.result == "PASSED" and "Finance" in finance.reason
