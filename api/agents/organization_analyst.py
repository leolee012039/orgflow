"""Organization Analyst: reads the org chart and policy PDFs into organization.json."""

import json

from google.adk import Agent
from google.genai import types

from agents.runtime import MODEL, AgentResult, pdf_part, run_agent
from schemas import Organization

INSTRUCTION = """You are the Organization Analyst for OrgFlow.

Read only the supplied company documents. Each document is introduced by a line
"Document id: <id>". Build the company's organization as JSON:

- departments: every department named in the documents, with head_role_id set to
  the id of the role that leads it.
- roles: every role or job title, including the chief executive. Use short
  snake_case ids (for example "operations_manager", "ceo"). Set department to the
  department name, or null for company-wide executives. Set reports_to to the id
  of the role this role reports to, or null for the top role. Copy each role's
  responsibilities from the documents, keeping their wording.
- relationships: cross-department handoffs that the documents state explicitly.
  "from" and "to" are department names. evidence.doc is the document id and
  evidence.quote is a short passage copied word for word from that document.

Rules:
- Never invent departments, roles, people, approval levels or numbers.
- Use the titles exactly as written in the documents.
- If the policy names an approver that the org chart does not list, do not add
  it as a role.
- Return JSON only."""

REPAIR_INSTRUCTION = """You previously produced organization JSON for these documents,
but an automatic check rejected it. Produce a corrected version that fixes every
listed problem, following the same rules: use only the supplied documents, never
invent roles or departments, copy quotes word for word, and return JSON only."""

_config = types.GenerateContentConfig(
    temperature=0,
    # Low thinking keeps a call near 10 s; the default level often runs past the 25 s budget.
    thinking_config=types.ThinkingConfig(thinking_level="low"),
)


def build_agent() -> Agent:
    return Agent(name="organization_analyst", model=MODEL, instruction=INSTRUCTION,
                 output_schema=Organization, generate_content_config=_config)


def build_repair_agent() -> Agent:
    return Agent(name="organization_analyst_repair", model=MODEL, instruction=REPAIR_INSTRUCTION,
                 output_schema=Organization, generate_content_config=_config)


def _documents(org_pdf: bytes, policy_pdf: bytes) -> list[types.Part]:
    return [*pdf_part("org_chart", org_pdf), *pdf_part("policy", policy_pdf)]


async def analyze(org_pdf: bytes, policy_pdf: bytes) -> AgentResult:
    parts = _documents(org_pdf, policy_pdf)
    parts.append(types.Part.from_text(text="Extract the organization."))
    return await run_agent(build_agent(), parts)


async def repair(org_pdf: bytes, policy_pdf: bytes, previous: dict | None, errors: list[str]) -> AgentResult:
    parts = _documents(org_pdf, policy_pdf)
    parts.append(types.Part.from_text(
        text="Previous output:\n" + json.dumps(previous, ensure_ascii=False)
        + "\n\nProblems found:\n- " + "\n- ".join(errors)
    ))
    return await run_agent(build_repair_agent(), parts)
