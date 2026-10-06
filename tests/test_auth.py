"""Sign-in: the sample is open, anything else needs a Firebase user, and each user has a daily limit."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import auth
import main
import pipeline
from guard import load_fixture
from sample_docs import upload_files
from schemas import Organization

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = upload_files()
OTHER = upload_files((ROOT / "demo_assets" / "zh" / "Xiangying_Fitness_Org_Chart.pdf").read_bytes(),
                     [(ROOT / "demo_assets" / "zh" / "Xiangying_Fitness_Purchasing_Policy.pdf").read_bytes()])
client = TestClient(main.app)


@pytest.fixture(autouse=True)
def signed_in_mode(monkeypatch):
    monkeypatch.setenv("ORGFLOW_REQUIRE_AUTH", "1")
    monkeypatch.setattr(auth, "_checks_today", {})

    async def fake_analyze(docs):
        org = Organization.model_validate(load_fixture("novagear/organization.json"))
        return pipeline.StageResult(org, "live", 5)

    monkeypatch.setattr(pipeline, "analyze_organization", fake_analyze)
    monkeypatch.setattr(auth, "verify_token", lambda token: "user-1" if token == "good" else None)


def analyze(files, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post("/api/analyze", headers=headers, files=files)


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


def test_sign_in_is_on_unless_turned_off(monkeypatch):
    monkeypatch.delenv("ORGFLOW_REQUIRE_AUTH")
    assert analyze(OTHER).status_code == 401
    monkeypatch.setenv("ORGFLOW_REQUIRE_AUTH", "0")  # local development
    assert analyze(OTHER).status_code == 200
