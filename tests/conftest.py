"""Tests never call Gemini: an agent call that a test forgot to fake fails the test instead of costing money.

The runtime turns a failed model call into an ordinary error and the stage falls back, so
a blocked call alone would not fail anything. The guard records each attempt and the
test fails at the end if there was one.
"""

import pytest

import pipeline
from agents import runtime


@pytest.fixture(autouse=True)
def no_live_gemini(monkeypatch):
    attempts: list[str] = []

    class NoGemini:
        def __init__(self, *args, **kwargs):
            attempts.append(getattr(kwargs.get("agent"), "name", "agent"))
            raise RuntimeError("a test tried to call Gemini; fake the agent call instead")

    monkeypatch.setattr(runtime, "InMemoryRunner", NoGemini)
    yield
    assert not attempts, f"these agents tried to call Gemini: {attempts}; fake them in the test"


@pytest.fixture(autouse=True)
def sign_in_off_by_default(monkeypatch):
    """Sign-in is on unless turned off; tests that check it turn it back on."""
    monkeypatch.setenv("ORGFLOW_REQUIRE_AUTH", "0")


@pytest.fixture(autouse=True)
def sample_read_live(monkeypatch):
    """Most tests check the live path with the sample documents and faked agents."""
    monkeypatch.setattr(pipeline, "SAMPLE_LIVE", True)
