"""Fixes from the 9 Oct review (docs/ISSUES.md #19): amounts that aren't numbers, Gemini failures answered as
Gemini's and not the documents', and a sign-in check that doesn't ask Google every time."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import auth
import main
from agents import organization_analyst
from agents.runtime import AgentResult
from guard import load_fixture
from runner import run_workflow
from sample_docs import upload_files
from schemas import Organization, Workflow

client = TestClient(main.app)
ZH = Path(__file__).resolve().parent.parent / "demo_assets" / "zh"
# Not a sample: a sample falls back to its saved answers, other documents get an error. The gym chain is a
# sample, so a byte added after its end gives other documents with the same text
OTHER = upload_files((ZH / "Xiangying_Fitness_Org_Chart.pdf").read_bytes() + b"\n% not a sample\n",
                     [(ZH / "Xiangying_Fitness_Purchasing_Policy.pdf").read_bytes()])
PURCHASE = {"request_id": "PR-1", "requester": "Emma Chen", "department": "Operations", "item": "Laptop",
            "business_justification": "Laptop required for a new designer on the Operations team."}


@pytest.fixture
def org():
    return Organization.model_validate(load_fixture("novagear/organization.json"))


@pytest.fixture
def workflow():
    return Workflow.model_validate(load_fixture("workflow_fixture.json"))


# --- Amounts ----------------------------------------------------------------------------------

@pytest.mark.parametrize("amount", ["abc", "nan", "", "  "])
def test_an_amount_that_isnt_a_number_returns_the_case(org, workflow, amount):
    # Before: every rule on the amount was "not met", its approvals were skipped, and the case completed
    trace = run_workflow(workflow, org, {**PURCHASE, "estimated_cost": amount})
    assert trace.status == "RETURNED"
    assert not any(s.result == "PASSED" for s in trace.steps)


def test_a_missing_amount_a_step_depends_on_returns_the_case(org, workflow):
    workflow.required_fields = [f for f in workflow.required_fields if f != "estimated_cost"]
    trace = run_workflow(workflow, org, PURCHASE)
    assert trace.status == "RETURNED"
    assert trace.steps[0].reason == "Missing or not a number: estimated cost"


def test_an_amount_written_as_text_still_runs(org, workflow):
    trace = run_workflow(workflow, org, {**PURCHASE, "estimated_cost": "2400"})
    assert trace.status == "COMPLETED"


# --- Gemini failures --------------------------------------------------------------------------

def test_gemini_not_answering_is_a_503_that_doesnt_blame_the_documents(monkeypatch):
    calls = []

    async def failing(*args):
        calls.append(args)
        return AgentResult(None, "ClientError: 403 PERMISSION_DENIED projects/123456/locations/global", 200,
                           unavailable=True)

    monkeypatch.setattr(organization_analyst, "analyze", failing)
    monkeypatch.setattr(organization_analyst, "repair", failing)
    monkeypatch.setenv("ORGFLOW_REQUIRE_AUTH", "0")
    resp = client.post("/api/analyze", files=OTHER)
    assert resp.status_code == 503
    detail = resp.json()["detail"]
    assert detail["message"] == main.GEMINI_UNAVAILABLE_MESSAGE and detail["problems"] == []
    assert "PERMISSION_DENIED" not in resp.text and "123456" not in resp.text
    assert len(calls) == 1  # no repair: it would fail the same way


# --- Sign-in check ----------------------------------------------------------------------------

def test_a_token_that_isnt_a_jwt_never_reaches_google(monkeypatch):
    def must_not_run(*args, **kwargs):
        raise AssertionError("verified a token that can't be one")

    monkeypatch.setattr(auth.id_token, "verify_firebase_token", must_not_run)
    assert auth.verify_token("garbage") is None
    assert auth.verify_token("a.b.c" + "x" * auth.MAX_TOKEN_CHARS) is None


def test_googles_certificates_are_fetched_once_an_hour(monkeypatch):
    fetched = []

    class Response:
        status = 200
        data = b"{}"
        headers = {}

    def fake_call(self, url, method="GET", body=None, headers=None, timeout=None, **kwargs):
        fetched.append((url, timeout))
        return Response()

    monkeypatch.setattr(auth.google_requests.Request, "__call__", fake_call)
    transport = auth._CachedCertsRequest()
    first = transport("https://certs.example/x")
    assert transport("https://certs.example/x") is first
    assert fetched == [("https://certs.example/x", 10)]
