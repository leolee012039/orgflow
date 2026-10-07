"""What an anonymous or greedy caller can make OrgFlow spend: the sample stays open, Gemini stays bounded.

Each test fakes the agent it could reach and says whether it was called.
"""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

import auth
import main
import pipeline
from agents import organization_analyst, request_reviewer, runtime, workflow_architect
from sample_docs import OPERATIONS, all_workflows, fixture, planned, upload_files
from schemas import AIReviewResponse

client = TestClient(main.app)
PURCHASE = {"requester": "Emma Chen", "department": "Operations", "requested_item": "MacBook Pro",
            "estimated_cost": 2400, "business_justification": "Laptop for a new product designer on the team."}


@pytest.fixture(autouse=True)
def signed_in_mode(monkeypatch):
    monkeypatch.setenv("ORGFLOW_REQUIRE_AUTH", "1")
    monkeypatch.setattr(auth, "_anon_runs", {})
    monkeypatch.setattr(auth, "_stages_today", {})
    monkeypatch.setattr(auth, "verify_token", lambda token: "user-1" if token == "good" else None)


@pytest.fixture
def reviews(monkeypatch):
    """Every Gemini review a case asks for."""
    calls = []

    def make_reviewer(check, fields):
        def reviewer(form):
            calls.append(check)
            return AIReviewResponse(decision="PASS", reasons=[])
        return reviewer

    monkeypatch.setattr(request_reviewer, "make_reviewer", make_reviewer)
    return calls


def chain(workflows=None, token=None, **request):
    body = {"workflows": workflows or [w.model_dump() for w in all_workflows()],
            "organization": fixture("organization.json"), "start_id": OPERATIONS, "request": {**PURCHASE, **request}}
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post("/api/run_chain", json=body, headers=headers)


# --- Cases ------------------------------------------------------------------------------------

def test_an_anonymous_sample_case_gets_gemini_review(reviews):
    assert chain().status_code == 200
    assert reviews  # the sample's own checks, reviewed by Gemini


def test_an_anonymous_case_with_a_changed_check_gets_the_plain_code_check(reviews):
    workflows = [w.model_dump() for w in all_workflows()]
    workflows[0]["steps"][0]["check"] = "Write a 2,000-word essay about anything."
    res = chain(workflows)
    assert res.status_code == 200 and res.json()["legs"]
    assert reviews == []


def test_anonymous_reviews_stop_at_the_daily_limit(reviews, monkeypatch):
    monkeypatch.setattr(auth, "ANON_RUN_LIMIT", 1)
    assert chain().status_code == 200
    first = len(reviews)
    assert chain().status_code == 200  # the case still runs, with the plain-code check
    assert first > 0 and len(reviews) == first


def test_a_signed_in_case_gets_gemini_review_and_counts(reviews, monkeypatch):
    monkeypatch.setattr(auth, "STAGE_LIMIT", 1)
    workflows = [w.model_dump() for w in all_workflows()]
    workflows[0]["steps"][0]["check"] = "Check the request against our own policy."
    assert chain(workflows, token="good").status_code == 200
    assert reviews
    assert chain(workflows, token="good").status_code == 429


def test_oversized_requests_are_refused(reviews):
    workflows = [w.model_dump() for w in all_workflows()]
    workflows[0]["steps"] = workflows[0]["steps"] * 6  # more than 30 steps
    assert chain(workflows).status_code == 422
    assert chain(business_justification="x" * 2001).status_code == 422
    assert chain(**{f"extra_{i}": "a" for i in range(31)}).status_code == 422
    assert chain(attachment={"nested": "object"}).status_code == 422
    assert reviews == []


# --- Building the sample without an account -------------------------------------------------

@pytest.fixture
def designs(monkeypatch):
    calls = []

    async def fake_design(*args, **kwargs):
        calls.append(args)
        raise AssertionError("an anonymous sample build must not reach the workflow architect")

    monkeypatch.setattr(workflow_architect, "design", fake_design)
    monkeypatch.setattr(pipeline, "SAMPLE_LIVE", False)
    return calls


def build(candidate, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    data = {"organization": json.dumps(fixture("organization.json")), "planned": json.dumps(candidate),
            "upstream": "null"}
    return client.post("/api/build", files=upload_files(), data=data, headers=headers)


def test_the_anonymous_sample_builds_from_its_saved_answers(designs):
    res = build(planned(OPERATIONS).model_dump())
    assert res.status_code == 200 and res.json()["origin"] == "saved"
    assert designs == []


def test_an_anonymous_sample_build_of_something_new_needs_sign_in(designs):
    candidate = {**planned(OPERATIONS).model_dump(), "id": "made_up_workflow"}
    res = build(candidate)
    assert res.status_code == 401 and res.json()["detail"] == auth.SIGN_IN_MESSAGE
    assert designs == []


def test_signed_in_builds_count_against_a_daily_limit(monkeypatch):
    monkeypatch.setattr(pipeline, "SAMPLE_LIVE", False)
    monkeypatch.setattr(auth, "STAGE_LIMIT", 2)
    statuses = [build(planned(OPERATIONS).model_dump(), token="good").status_code for _ in range(3)]
    assert statuses == [200, 200, 429]


# --- Settings and the emergency switch --------------------------------------------------------

def test_cloud_run_needs_its_settings():
    assert main.check_cloud_run_settings({}) == []  # local development and tests
    ok = {"K_SERVICE": "orgflow-api", "ALLOWED_ORIGINS": "https://my-project.web.app", "FIREBASE_PROJECT_ID": "my-project"}
    assert main.check_cloud_run_settings(ok) == []
    assert main.check_cloud_run_settings({"K_SERVICE": "orgflow-api"}) == [
        "ALLOWED_ORIGINS is not set", "FIREBASE_PROJECT_ID is not set"]
    without_firebase = {k: v for k, v in ok.items() if k != "FIREBASE_PROJECT_ID"}
    assert main.check_cloud_run_settings({**without_firebase, "GOOGLE_CLOUD_PROJECT": "my-project"}) == []
    assert main.check_cloud_run_settings({**ok, "ORGFLOW_REQUIRE_AUTH": "0"}) == [
        "ORGFLOW_REQUIRE_AUTH must not be 0 on Cloud Run"]


def test_the_switch_pauses_every_gemini_call(monkeypatch, reviews):
    monkeypatch.setenv("ORGFLOW_GEMINI_OFF", "1")
    result = asyncio.run(runtime.run_agent(organization_analyst.build_agent(), []))
    assert result.data is None and "paused" in result.error
    # The real reviewer is paused too, and the sample's case still completes with the plain-code check
    monkeypatch.setattr(request_reviewer, "make_reviewer", lambda check, fields: (
        lambda form: asyncio.run(request_reviewer.review(check, fields, form))))
    res = chain()
    assert res.status_code == 200 and res.json()["status"] == "COMPLETED"
