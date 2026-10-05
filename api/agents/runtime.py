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
from google.adk.runners import InMemoryRunner
from google.genai import types

# Local development reads api/.env; Cloud Run sets the same variables on the service.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
# Most calls answer in 3-9 s, but a few take 15-30 s. After HEDGE_AFTER_S a second,
# identical request starts and the first answer wins; CALL_TIMEOUT_S caps the pair.
CALL_TIMEOUT_S = float(os.getenv("GEMINI_TIMEOUT_S", "40"))
HEDGE_AFTER_S = float(os.getenv("GEMINI_HEDGE_AFTER_S", "12"))

# Low thinking keeps a call near 10 s; the default level often runs past the time budget.
LOW_THINKING = types.GenerateContentConfig(
    temperature=0,
    thinking_config=types.ThinkingConfig(thinking_level="low"),
)
CACHE_DIR = Path(__file__).resolve().parent.parent.parent / ".cache" / "llm"


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


def json_part(label: str, value: Any) -> types.Part:
    return types.Part.from_text(text=f"{label}:\n{json.dumps(value, ensure_ascii=False, indent=1)}")


def problems_part(previous: Optional[dict], problems: list[str]) -> types.Part:
    """What a repair call is told: its previous answer and why the guard rejected it."""
    return types.Part.from_text(
        text="Your previous output:\n" + json.dumps(previous, ensure_ascii=False)
        + "\n\nAn automatic check rejected it for these problems:\n- " + "\n- ".join(problems)
        + "\n\nReturn a corrected version that fixes every problem."
    )


def _cache_key(agent: Agent, parts: list[types.Part]) -> str:
    h = hashlib.sha256()
    h.update(f"{MODEL}|{agent.name}|{agent.instruction}".encode())
    for part in parts:
        if part.text is not None:
            h.update(part.text.encode())
        elif part.inline_data is not None:
            h.update(part.inline_data.data)
    return h.hexdigest()[:32]


async def _run(agent: Agent, parts: list[types.Part]) -> str:
    runner = InMemoryRunner(agent=agent, app_name="orgflow")
    session = await runner.session_service.create_session(app_name="orgflow", user_id="orgflow")
    message = types.Content(role="user", parts=parts)
    final_text = ""
    async for event in runner.run_async(user_id="orgflow", session_id=session.id, new_message=message):
        if event.content and event.content.parts:
            text = "".join(p.text or "" for p in event.content.parts if not getattr(p, "thought", False))
            if text.strip():
                final_text = text
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
