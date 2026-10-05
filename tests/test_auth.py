"""Sign-in: the sample is open, anything else needs a Firebase user, and each user has a daily limit."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import auth
import main
import pipeline
from guard import load_fixture
from schemas import Organization

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = {
    "org_chart": (ROOT / "demo_assets" / "en" / "NovaGear_Organization_Chart.pdf").read_bytes(),
    "policy": (ROOT / "demo_assets" / "en" / "NovaGear_Purchasing_Policy.pdf").read_bytes(),
}
OTHER = {
    "org_chart": (ROOT / "demo_assets" / "zh" / "Xiangying_Fitness_Org_Chart.pdf").read_bytes(),
    "policy": (ROOT / "demo_assets" / "zh" / "Xiangying_Fitness_Purchasing_Policy.pdf").read_bytes(),
}
client = TestClient(main.app)


@pytest.fixture(autouse=True)
def signed_in_mode(monkeypatch):
    monkeypatch.setenv("ORGFLOW_REQUIRE_AUTH", "1")
    monkeypatch.setattr(auth, "_checks_today", {})

    async def fake_analyze(org_pdf, policy_pdf):
        org = Organization.model_validate(load_fixture("organization_fixture.json"))
        return pipeline.StageResult(org, "live", 5)

    monkeypatch.setattr(pipeline, "analyze_organization", fake_analyze)
    monkeypatch.setattr(auth, "verify_token", lambda token: "user-1" if token == "good" else None)


def analyze(docs, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post("/api/analyze", headers=headers, files={
        "org_chart": ("org.pdf", docs["org_chart"], "application/pdf"),
        "policy": ("policy.pdf", docs["policy"], "application/pdf"),
    })


def test_the_sample_needs_no_account():
    assert analyze(SAMPLE).status_code == 200


def test_other_documents_need_a_signed_in_user():
    res = analyze(OTHER)
    assert res.status_code == 401
    assert res.json()["detail"] == auth.SIGN_IN_MESSAGE
    assert analyze(OTHER, token="forged").status_code == 401
    assert analyze(OTHER, token="good").status_code == 200


def test_each_user_has_a_daily_limit(monkeypatch):
    monkeypatch.setattr(auth, "DAILY_LIMIT", 2)
    assert [analyze(OTHER, token="good").status_code for _ in range(3)] == [200, 200, 429]
    assert analyze(SAMPLE).status_code == 200  # the sample doesn't count against anyone


def test_sign_in_is_off_unless_turned_on(monkeypatch):
    monkeypatch.delenv("ORGFLOW_REQUIRE_AUTH")
    assert analyze(OTHER).status_code == 200
