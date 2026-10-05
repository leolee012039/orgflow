"""Department Analyst: what each department does, and how work moves between departments."""

from google.adk import Agent
from google.genai import types

from agents.runtime import LOW_THINKING, AgentResult, document_parts, gemini, json_part, problems_part, run_agent
from schemas import DepartmentMap

MAX_DEPARTMENTS = 10

INSTRUCTION = f"""You are the Department Analyst for OrgFlow.

You receive a company's documents (each introduced by "Document id: <id>") and the
organization JSON extracted from them. Describe what each department does and how
work moves between departments.

- departments: one profile for each department in the organization JSON that the
  documents give work to, at most {MAX_DEPARTMENTS}. With more departments, keep the
  ones the documents say most about. name: exactly as in the organization JSON.
  summary: one sentence on what the department is for. work: the recurring work the
  documents assign to the department or its roles. task: a few words; evidence: a
  passage copied word for word from the documents, with its document id.
- handoffs: every place where one department's result goes to another department,
  which then does its own work with it: carries out an approved request, pays an
  invoice, checks a customer's credit. Read every policy for passages where a
  request, order, invoice or result "is handed to", "is sent to", "goes to" or "is
  submitted to" another department, and list each one. When a passage names only the
  receiving department, the sender is the department whose roles submit that kind of
  request according to the documents: if a role in Maintenance "submits repair
  requests" and a policy says "approved repair requests are handed to Facilities",
  that is a handoff from Maintenance to Facilities. An approval that is only one step inside
  the sender's own process is not a handoff. from and to: department
  names exactly as in the organization JSON. what: the item that passes, in a few
  words (for example "approved purchase request"). evidence: a passage copied word
  for word that shows the handoff.

Write summary, task and what in the language of the documents. Never invent
departments, work or handoffs that no passage supports. Return JSON only."""


def build_agent(name: str = "department_analyst") -> Agent:
    return Agent(name=name, model=gemini(), instruction=INSTRUCTION,
                 output_schema=DepartmentMap, generate_content_config=LOW_THINKING)


def _inputs(docs: list[tuple[str, bytes]], organization: dict) -> list[types.Part]:
    return [*document_parts(docs), json_part("Organization JSON", organization)]


async def analyze(docs: list[tuple[str, bytes]], organization: dict) -> AgentResult:
    parts = [*_inputs(docs, organization), types.Part.from_text(text="Map the departments and their handoffs.")]
    return await run_agent(build_agent(), parts)


async def repair(docs: list[tuple[str, bytes]], organization: dict,
                 previous: dict | None, problems: list[str]) -> AgentResult:
    parts = [*_inputs(docs, organization), problems_part(previous, problems)]
    return await run_agent(build_agent("department_analyst_repair"), parts)
