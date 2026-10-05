"""Opportunity Analyst: finds 3 workflows worth automating, without being told which."""

from google.adk import Agent
from google.genai import types

from agents.runtime import LOW_THINKING, MODEL, AgentResult, json_part, pdf_part, problems_part, run_agent
from schemas import Opportunities

INSTRUCTION = """You are the Opportunity Analyst for OrgFlow.

You receive a company's documents (each introduced by "Document id: <id>") and the
organization JSON extracted from them. Nobody has told you what to automate: find
it yourself.

Return exactly 3 opportunities: repetitive or rule-based workflows that pass work
between several roles or departments. Rank them, most valuable first. Prefer:
1. clear handoffs between departments,
2. explicit approval rules or thresholds,
3. repetitive checks people do by hand,
4. workflows that can be demonstrated safely without real payments or emails.

For each opportunity:
- id: short snake_case; name: a short title.
- departments: department names exactly as they appear in the organization JSON.
- manual_handoffs: how many times the work changes hands today, counted from the documents.
- impact: HIGH, MEDIUM or LOW.
- why: two sentences on what is slow or repetitive today and what can be automated.
- evidence: one or more passages copied word for word from the documents, with the
  document id they came from.
- executable: true only for the top-ranked opportunity, and only if its steps can be
  expressed as approvals, automated checks, tasks and notifications using rules
  stated in the documents. Every other opportunity is false.

Never assume software, integrations, departments or rules that the documents do not
mention. Return JSON only."""


def build_agent(name: str = "opportunity_analyst") -> Agent:
    return Agent(name=name, model=MODEL, instruction=INSTRUCTION,
                 output_schema=Opportunities, generate_content_config=LOW_THINKING)


def _inputs(org_pdf: bytes, policy_pdf: bytes, organization: dict) -> list[types.Part]:
    return [*pdf_part("org_chart", org_pdf), *pdf_part("policy", policy_pdf),
            json_part("Organization JSON", organization)]


async def discover(org_pdf: bytes, policy_pdf: bytes, organization: dict) -> AgentResult:
    parts = [*_inputs(org_pdf, policy_pdf, organization),
             types.Part.from_text(text="Find the 3 best automation opportunities.")]
    return await run_agent(build_agent(), parts)


async def repair(org_pdf: bytes, policy_pdf: bytes, organization: dict,
                 previous: dict | None, problems: list[str]) -> AgentResult:
    parts = [*_inputs(org_pdf, policy_pdf, organization), problems_part(previous, problems)]
    return await run_agent(build_agent("opportunity_analyst_repair"), parts)
