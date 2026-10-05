"""Document Reader: transcribes a scanned (image-only) PDF so the guard has text to check.

The analysts read the PDF directly; this transcript is only what the guard compares
their quotes against when pypdf finds no text layer.
"""

from google.adk import Agent
from google.genai import types
from pydantic import BaseModel

from agents.runtime import LOW_THINKING, MODEL, AgentResult, pdf_part, run_agent

INSTRUCTION = """You transcribe documents for OrgFlow.

Copy every piece of text in the document exactly as written, in its original
language. Put each heading, paragraph and table row on its own line. Do not
translate, summarize, correct or add anything. Return JSON with one field, "text"."""


class Transcript(BaseModel):
    text: str


def build_agent() -> Agent:
    return Agent(name="document_reader", model=MODEL, instruction=INSTRUCTION,
                 output_schema=Transcript, generate_content_config=LOW_THINKING)


async def transcribe(pdf_bytes: bytes) -> AgentResult:
    parts = [*pdf_part("document", pdf_bytes), types.Part.from_text(text="Transcribe this document.")]
    return await run_agent(build_agent(), parts)
