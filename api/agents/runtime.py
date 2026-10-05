"""Run one ADK agent call with a time limit and return its JSON output.

Every call writes one structured log line (Cloud Run sends JSON on stdout to
Cloud Logging). With ORGFLOW_DEV_CACHE=1, identical calls are answered from a
local cache so development does not spend the Gemini free-tier quota.
"""

import asyncio
import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from google.adk import Agent
from google.adk.models.google_llm import Gemini
from google.adk.runners import InMemoryRunner
from google.genai import types

# Local development reads api/.env; Cloud Run sets the same variables on the service.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
# Most calls answer in 3-10 s; long real documents take 30-60 s and a few calls stall. After HEDGE_AFTER_S a second,
# identical request starts and the first answer wins; CALL_TIMEOUT_S caps the pair. 60 s cut off real university
# documents (organization regulations of 14-18 pages) about half the time, so the cap is 90 s.
CALL_TIMEOUT_S = float(os.getenv("GEMINI_TIMEOUT_S", "90"))
HEDGE_AFTER_S = float(os.getenv("GEMINI_HEDGE_AFTER_S", "20"))

# Low thinking keeps a call near 10 s; the default level often runs past the time budget.
LOW_THINKING = types.GenerateContentConfig(
    temperature=0,
    thinking_config=types.ThinkingConfig(thinking_level="low"),
)
# Vertex answers 429 when its shared capacity is busy. Two retries, about 2 s and 4 s later,
# clear most of them well inside the time budget. Without retry options the client never retries.
RETRY = types.HttpRetryOptions(attempts=3, initial_delay=2, max_delay=8)


def gemini() -> Gemini:
    """The model every agent uses."""
    return Gemini(model=MODEL, retry_options=RETRY)
CACHE_DIR = Path(__file__).resolve().parent.parent.parent / ".cache" / "llm"


class GeminiCallError(RuntimeError):
    """The model call failed, for example 429 RESOURCE_EXHAUSTED after the retries."""


@dataclass
class AgentResult:
    data: Optional[dict[str, Any]]
    error: Optional[str]
    latency_ms: int
    cached: bool = False


def log_event(event: str, **fields: Any) -> None:
    print(json.dumps({"severity": "INFO", "event": event, **fields}), flush=True)


def pdf_part(label: str, pdf_bytes: bytes) -> list[types.Part]:
    """A labelled PDF, so the model can cite which document a quote came from."""
    return [
        types.Part.from_text(text=f"Document id: {label}"),
        types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
    ]


def document_parts(docs: list[tuple[str, bytes]]) -> list[types.Part]:
    """Every uploaded document, each labelled with its id ("org_chart", "policy_1", ...)."""
    return [part for label, pdf in docs for part in pdf_part(label, pdf)]


def json_part(label: str, value: Any) -> types.Part:
    return types.Part.from_text(text=f"{label}:\n{json.dumps(value, ensure_ascii=False, indent=1)}")


def problems_part(previous: Optional[dict], problems: list[str]) -> types.Part:
    """What a repair call is told: its previous answer and why the guard rejected it."""
    return types.Part.from_text(
        text="Your previous output:\n" + json.dumps(previous, ensure_ascii=False)
        + "\n\nAn automatic check rejected it for these problems:\n- " + "\n- ".join(problems)
        + "\n\nReturn a corrected version that fixes every problem. Keep everything that was correct: "
        + "never delete departments, roles, rules or steps that appear in the documents just to pass the checks."
    )


def _cache_key(agent: Agent, parts: list[types.Part]) -> str:
    h = hashlib.sha256()
    h.update(f"{MODEL}|{agent.name}|{agent.instruction}".encode())
    for part in parts:
        if part.text is not None:
            h.update(part.text.encode())
        elif part.inline_data is not None and part.inline_data.data:
            h.update(part.inline_data.data)
    return h.hexdigest()[:32]


async def _run(agent: Agent, parts: list[types.Part]) -> str:
    runner = InMemoryRunner(agent=agent, app_name="orgflow")
    session = await runner.session_service.create_session(app_name="orgflow", user_id="orgflow")
    message = types.Content(role="user", parts=parts)
    final_text = ""
    events = runner.run_async(user_id="orgflow", session_id=session.id, new_message=message)
    try:
        async for event in events:
            text = ""
            if event.content and event.content.parts:
                text = "".join(p.text or "" for p in event.content.parts if not getattr(p, "thought", False))
                if text.strip():
                    final_text = text
            if event.error_code and not text.strip():
                # ADK reports a failed model call (429, 403) as an event and may then keep the run
                # open, so stop here instead of waiting for the time limit
                raise GeminiCallError(f"{event.error_code}: {event.error_message}")
    finally:
        await events.aclose()  # lets ADK cancel its run now rather than when garbage collected
    return final_text


async def _run_hedged(agent: Agent, parts: list[types.Part], timeout_s: float) -> tuple[str, bool]:
    """Return the first successful answer; start a backup request if the first is slow."""
    deadline = time.perf_counter() + timeout_s
    pending = {asyncio.create_task(_run(agent, parts))}
    hedged = False
    last_error: Optional[BaseException] = None
    try:
        while pending:
            wait_s = deadline - time.perf_counter()
            if not hedged:
                wait_s = min(wait_s, HEDGE_AFTER_S)
            done, pending = await asyncio.wait(pending, timeout=max(wait_s, 0),
                                               return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if task.exception() is None:
                    return task.result(), hedged
                last_error = task.exception()
            if not done and not hedged and time.perf_counter() < deadline:
                hedged = True
                pending.add(asyncio.create_task(_run(agent, parts)))
            elif not done:
                raise asyncio.TimeoutError
        raise last_error or RuntimeError("no answer")
    finally:
        for task in pending:
            task.cancel()


def _parse_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned[cleaned.find("{"):]
    return json.loads(cleaned)


async def run_agent(agent: Agent, parts: list[types.Part], timeout_s: float = CALL_TIMEOUT_S) -> AgentResult:
    use_cache = os.getenv("ORGFLOW_DEV_CACHE") == "1"
    key = _cache_key(agent, parts)
    cache_file = CACHE_DIR / f"{key}.json"
    if use_cache and cache_file.exists():
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        log_event("gemini_call", agent=agent.name, model=MODEL, cached=True, latency_ms=0, ok=True)
        return AgentResult(data=data, error=None, latency_ms=0, cached=True)

    call_id = uuid.uuid4().hex[:8]
    start = time.perf_counter()
    hedged = False
    try:
        text, hedged = await _run_hedged(agent, parts, timeout_s)
        data = _parse_json(text)
        error = None
    except asyncio.TimeoutError:
        data, error = None, f"timed out after {timeout_s:.0f}s"
    except json.JSONDecodeError as exc:
        data, error = None, f"model returned invalid JSON: {exc}"
    except Exception as exc:  # network, quota, auth: the guard falls back to a fixture
        data, error = None, f"{type(exc).__name__}: {exc}"
    latency_ms = int((time.perf_counter() - start) * 1000)

    log_event("gemini_call", call_id=call_id, agent=agent.name, model=MODEL, cached=False,
              latency_ms=latency_ms, hedged=hedged, ok=error is None, error=error)
    if use_cache and data is not None:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return AgentResult(data=data, error=error, latency_ms=latency_ms)
