"""run_agent: hedged requests and time limits, with a fake model call."""

import asyncio
import time
from types import SimpleNamespace

import pytest

from agents import runtime

AGENT = SimpleNamespace(name="test_agent", instruction="test")


@pytest.fixture(autouse=True)
def fast_timers(monkeypatch):
    monkeypatch.setattr(runtime, "HEDGE_AFTER_S", 0.05)
    monkeypatch.delenv("ORGFLOW_DEV_CACHE", raising=False)


def fake_calls(monkeypatch, behaviours):
    """behaviours[i] is (delay_s, result_or_exception) for the i-th model call."""
    calls = []

    async def fake_run(agent, parts):
        delay, outcome = behaviours[len(calls)]
        calls.append(time.perf_counter())
        await asyncio.sleep(delay)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(runtime, "_run", fake_run)
    return calls


def run(timeout_s=2.0):
    return asyncio.run(runtime.run_agent(AGENT, [], timeout_s=timeout_s))


def test_fast_answer_does_not_hedge(monkeypatch):
    calls = fake_calls(monkeypatch, [(0.0, '{"answer": 1}')])
    result = run()
    assert result.data == {"answer": 1} and len(calls) == 1


def test_slow_answer_is_beaten_by_the_backup_request(monkeypatch):
    calls = fake_calls(monkeypatch, [(1.0, '{"answer": "slow"}'), (0.0, '{"answer": "backup"}')])
    result = run()
    assert result.data == {"answer": "backup"}
    assert len(calls) == 2
    assert result.latency_ms < 500


def test_backup_failure_still_waits_for_the_first_request(monkeypatch):
    fake_calls(monkeypatch, [(0.2, '{"answer": "first"}'), (0.0, RuntimeError("quota"))])
    result = run()
    assert result.data == {"answer": "first"}


def test_both_too_slow_times_out(monkeypatch):
    fake_calls(monkeypatch, [(1.0, "{}"), (1.0, "{}")])
    result = run(timeout_s=0.3)
    assert result.data is None and result.error.startswith("timed out")


def test_immediate_error_is_reported_without_backup(monkeypatch):
    calls = fake_calls(monkeypatch, [(0.0, RuntimeError("403 PERMISSION_DENIED"))])
    result = run()
    assert result.data is None and "403" in result.error
    assert len(calls) == 1


def test_markdown_wrapped_json_is_accepted(monkeypatch):
    fake_calls(monkeypatch, [(0.0, '```json\n{"answer": 2}\n```')])
    assert run().data == {"answer": 2}


class FakeRunner:
    """Stands in for ADK's InMemoryRunner: yields the given events, then never finishes,
    the way ADK keeps a run open after reporting a failed model call."""

    events: list = []

    def __init__(self, agent, app_name):
        async def create_session(app_name, user_id):
            return SimpleNamespace(id="s1")

        self.session_service = SimpleNamespace(create_session=create_session)

    async def run_async(self, user_id, session_id, new_message):
        for event in self.events:
            yield event
        await asyncio.sleep(3600)


def test_a_reported_model_error_stops_the_call_at_once(monkeypatch):
    FakeRunner.events = [SimpleNamespace(content=None, error_code="RESOURCE_EXHAUSTED",
                                         error_message="429 Resource exhausted")]
    monkeypatch.setattr(runtime, "InMemoryRunner", FakeRunner)
    start = time.perf_counter()
    result = run(timeout_s=5.0)
    assert time.perf_counter() - start < 1.0
    assert result.data is None and "RESOURCE_EXHAUSTED" in result.error


def test_html_entities_in_an_answer_become_characters():
    # An Australian company's "People & Culture" came back from Gemini as "People &amp; Culture"
    data = runtime._parse_json('{"department": "People &amp; Culture", "roles": [{"title": "R&amp;D Lead"}], "n": 3}')
    assert data == {"department": "People & Culture", "roles": [{"title": "R&D Lead"}], "n": 3}


def test_every_agent_retries_a_busy_endpoint():
    # Four retries ride out a busy spell (ISSUES.md #27), and their waits leave most of the time budget for the calls
    retry = runtime.gemini().retry_options
    assert retry is not None and retry.attempts >= 5
    waits = sum(min(retry.initial_delay * 2 ** i, retry.max_delay) for i in range(retry.attempts - 1))
    assert waits <= runtime.CALL_TIMEOUT_S / 2
