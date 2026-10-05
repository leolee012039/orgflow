"""Tests never call Gemini: an agent call that a test forgot to fake fails loudly instead of costing money."""

import pytest

from agents import runtime


class _NoGemini:
    def __init__(self, *args, **kwargs):
        raise RuntimeError("a test tried to call Gemini; fake the agent call instead")


@pytest.fixture(autouse=True)
def no_live_gemini(monkeypatch):
    monkeypatch.setattr(runtime, "InMemoryRunner", _NoGemini)
