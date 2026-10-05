"""Phase 3: opportunity and workflow guards, guarded stages, the runner's live review, endpoints.

No test here calls Gemini: agent calls are replaced with fakes.
"""

import asyncio
import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
import pipeline
from agents import opportunity_analyst, request_reviewer, workflow_architect
from agents.runtime import AgentResult
from guard import extract_pdf_text, load_fixture, validate_opportunities_output, validate_workflow_output
from schemas import AIReviewResponse, Opportunity, Organization, PurchaseRequestForm, Workflow

ROOT = Path(__file__).resolve().parent.parent
EN = ROOT / "demo_assets" / "en"
ORG_PDF = (EN / "NovaGear_Organization_Chart.pdf").read_bytes()
POLICY_PDF = (EN / "NovaGear_Purchasing_Policy.pdf").read_bytes()
DOC_TEXT = extract_pdf_text(ORG_PDF) + "\n" + extract_pdf_text(POLICY_PDF)
ORG = Organization.model_validate(load_fixture("organization_fixture.json"))


def opps_data() -> dict:
    return copy.deepcopy(load_fixture("opportunities_fixture.json"))


def wf_data() -> dict:
    return copy.deepcopy(load_fixture("workflow_fixture.json"))


# --- Opportunity guard ------------------------------------------------------------

def test_fixture_opportunities_pass_full_guard():
    opps, problems = validate_opportunities_output(opps_data(), ORG, DOC_TEXT)
    assert problems == [] and opps is not None


def test_only_top_opportunity_may_be_executable():
    data = opps_data()
    data["opportunities"][1]["executable"] = True
    _, problems = validate_opportunities_output(data, ORG, DOC_TEXT)
    assert any("top-ranked" in p for p in problems)

    data = opps_data()
    data["opportunities"][0]["executable"] = False
    _, problems = validate_opportunities_output(data, ORG, DOC_TEXT)
    assert any("top-ranked" in p for p in problems)


def test_opportunity_with_unknown_department_or_invented_quote_is_rejected():
    data = opps_data()
    data["opportunities"][2]["departments"].append("Human Resources")
    data["opportunities"][1]["evidence"] = [{"doc": "policy", "quote": "HR onboards every new hire within 3 days."}]
    opps, problems = validate_opportunities_output(data, ORG, DOC_TEXT)
    assert opps is None
    assert any("Human Resources" in p for p in problems)
    assert any("does not ground" in p for p in problems)


# --- Workflow guard -----------------------------------------------------------------

def test_fixture_workflow_passes_full_guard():
    wf, problems = validate_workflow_output(wf_data(), ORG, DOC_TEXT)
    assert problems == [] and wf is not None


@pytest.mark.parametrize("mutate,expected", [
    (lambda d: d["steps"][2].update(only_if="r_missing"), "is not a rule id"),
    (lambda d: d["rules"][0]["when"].update(field="budget_code"), "not a request form field"),
    (lambda d: d["required_fields"].append("cost_center"), "not a request form field"),
    (lambda d: d["steps"][4].update(actor="Chief Purchasing Officer"), "not in organization roles"),
    (lambda d: d["unresolved_actors"].append("Chief Purchasing Officer"), "does not appear in the uploaded documents"),
    (lambda d: d["steps"].append(dict(d["steps"][1])), "Step ids must be unique"),
    (lambda d: d["rules"][1]["when"].update(value=6000), "does not appear in its source quote"),
])
def test_workflow_guard_rejects(mutate, expected):
    data = wf_data()
    mutate(data)
    wf, problems = validate_workflow_output(data, ORG, DOC_TEXT)
    assert wf is None
    assert any(expected in p for p in problems), problems


# --- Guarded stages with fake agents ----------------------------------------------

def test_discover_opportunities_live(monkeypatch):
    async def fake(org_pdf, policy_pdf, organization):
        assert organization["company"] == "NovaGear Inc."
        return AgentResult(opps_data(), None, 7000)

    monkeypatch.setattr(opportunity_analyst, "discover", fake)
    result = asyncio.run(pipeline.discover_opportunities(ORG_PDF, POLICY_PDF, ORG))
    assert result.origin == "live"
    assert result.value.opportunities[0].executable


def test_design_workflow_repairs_wrong_opportunity_id(monkeypatch):
    wrong = wf_data()
    wrong["opportunity_id"] = "something_else"

    async def fake_design(*args):
        return AgentResult(wrong, None, 6000)

    async def fake_repair(org_pdf, policy_pdf, organization, opportunity, previous, problems):
        assert "opportunity_id must be 'purchase_request_approval'" in problems[0]
        return AgentResult(wf_data(), None, 5000)

    monkeypatch.setattr(workflow_architect, "design", fake_design)
    monkeypatch.setattr(workflow_architect, "repair", fake_repair)
    opportunity = Opportunity.model_validate(opps_data()["opportunities"][0])
    result = asyncio.run(pipeline.design_workflow(ORG_PDF, POLICY_PDF, ORG, opportunity))
    assert result.origin == "repaired" and result.latency_ms == 11000


# --- Runner with the live reviewer --------------------------------------------------

def form(**overrides) -> PurchaseRequestForm:
    base = dict(requester="Emma Chen", department="Operations", item="MacBook Pro", estimated_cost=2400,
                business_justification="Laptop required for a new Product Designer.")
    return PurchaseRequestForm(**{**base, **overrides})


def test_run_request_uses_reviewer_and_handoff_metric(monkeypatch):
    seen = {}

    def fake_make_reviewer(check, required_fields):
        seen["check"], seen["fields"] = check, required_fields
        return lambda f: AIReviewResponse(decision="PASS", reasons=[])

    monkeypatch.setattr(request_reviewer, "make_reviewer", fake_make_reviewer)
    trace = asyncio.run(pipeline.run_request(Workflow.model_validate(wf_data()), ORG, form(), 5))
    assert trace.status == "COMPLETED"
    assert trace.metrics.manual_handoffs_before == 5
    assert "section 2" in seen["check"] and "business_justification" in seen["fields"]
    assert trace.steps[0].reason == "Policy section 2 check passed by Gemini"


def test_run_request_falls_back_when_reviewer_fails(monkeypatch):
    def broken(form):
        raise RuntimeError("timed out after 25s")

    monkeypatch.setattr(request_reviewer, "make_reviewer", lambda check, fields: broken)
    trace = asyncio.run(pipeline.run_request(Workflow.model_validate(wf_data()), ORG, form()))
    assert trace.status == "COMPLETED"
    assert "fallback check" in trace.steps[0].reason


def test_reviewer_can_only_send_to_human_review(monkeypatch):
    monkeypatch.setattr(request_reviewer, "make_reviewer", lambda check, fields: (
        lambda f: AIReviewResponse(decision="NEEDS_HUMAN_REVIEW", reasons=["justification is vague"])))
    trace = asyncio.run(pipeline.run_request(Workflow.model_validate(wf_data()), ORG,
                                             form(business_justification="need it")))
    assert trace.status == "NEEDS_HUMAN_REVIEW"
    assert trace.steps[0].result == "HUMAN_REVIEW"
    assert "justification is vague" in trace.steps[0].reason


# --- Endpoints -------------------------------------------------------------------------

client = TestClient(main.app)
FILES = {"org_chart": ("org.pdf", ORG_PDF, "application/pdf"),
         "policy": ("policy.pdf", POLICY_PDF, "application/pdf")}
ORG_JSON = json.dumps(load_fixture("organization_fixture.json"))


def test_opportunities_endpoint(monkeypatch):
    async def fake(org_pdf, policy_pdf, organization):
        return AgentResult(opps_data(), None, 7000)

    monkeypatch.setattr(opportunity_analyst, "discover", fake)
    resp = client.post("/api/opportunities", files=FILES, data={"organization": ORG_JSON})
    assert resp.status_code == 200
    body = resp.json()
    assert body["origin"] == "live" and len(body["opportunities"]) == 3


def test_opportunities_endpoint_rejects_bad_organization():
    resp = client.post("/api/opportunities", files=FILES, data={"organization": '{"company": 1}'})
    assert resp.status_code == 422


def test_workflow_endpoint(monkeypatch):
    async def fake(*args):
        return AgentResult(wf_data(), None, 6000)

    monkeypatch.setattr(workflow_architect, "design", fake)
    opp = json.dumps(opps_data()["opportunities"][0])
    resp = client.post("/api/workflow", files=FILES, data={"organization": ORG_JSON, "opportunity": opp})
    assert resp.status_code == 200
    body = resp.json()
    assert body["origin"] == "live" and body["unresolved_actors"] == ["Director"]


def test_workflow_endpoint_refuses_blueprint_only_opportunity():
    opp = json.dumps(opps_data()["opportunities"][1])
    resp = client.post("/api/workflow", files=FILES, data={"organization": ORG_JSON, "opportunity": opp})
    assert resp.status_code == 400
    assert "blueprint only" in resp.json()["detail"]


def test_run_endpoint(monkeypatch):
    monkeypatch.setattr(request_reviewer, "make_reviewer", lambda check, fields: (
        lambda f: AIReviewResponse(decision="PASS", reasons=[])))
    body = {"workflow": wf_data(), "organization": load_fixture("organization_fixture.json"),
            "request": form(estimated_cost=8000).model_dump(), "manual_handoffs_before": 4}
    resp = client.post("/api/run", json=body)
    assert resp.status_code == 200
    trace = resp.json()
    assert trace["status"] == "NEEDS_HUMAN_REVIEW"
    assert trace["steps"][-1]["step_id"] == "director_approval"
    assert "not in the org chart" in trace["steps"][-1]["reason"]
