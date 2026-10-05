"""Workflow Planner: for each department, the workflows worth automating, linked across departments."""

from google.adk import Agent
from google.genai import types

from agents.runtime import LOW_THINKING, AgentResult, document_parts, gemini, json_part, problems_part, run_agent
from schemas import WorkflowPlan

MAX_PER_DEPARTMENT = 3

INSTRUCTION = f"""You are the Workflow Planner for OrgFlow.

You receive a company's documents (each introduced by "Document id: <id>"), the
organization JSON, and the department map: what each department does and the
handoffs between departments. For every department in the department map, propose 1
to {MAX_PER_DEPARTMENT} workflows it could automate, most valuable first.

A workflow is repeated, rule-based work that either a person starts with a form, or
that starts when another department hands work over. For each workflow:
- id: short snake_case, unique across all departments.
- department: the department that owns it, exactly as in the department map.
- name: a short title. trigger: one sentence on what starts it.
- starts_from: the department whose handoff starts it, or null when a person starts
  it with a form. hands_to: the department that receives its result, or null. Use
  only handoffs listed in the department map: starts_from -> department and
  department -> hands_to must each be a handoff there.
- output: what it produces, in a few words.
- basis: "policy" when a policy document states rules for it (approvals, amounts,
  required information); "org_chart" when only responsibilities describe it.
- why: two sentences on what is slow or manual today and what automation changes.
- manual_handoffs: how many times the work changes hands today, counted from the
  documents.
- evidence: passages copied word for word, with their document ids. A "policy"
  workflow cites the policy passage that states its rules.

Connect departments: for every handoff in the department map, plan one workflow in
the sending department with hands_to set to the receiver, and one in the receiving
department with starts_from set to the sender, so that the first hands its result to
the second. Rank these first in their departments.

Approval levels: a policy that sets who approves by amount (one approver up to an
amount, another above it) needs exactly one workflow that takes a request through
those levels, citing the passages that state them. When one department sends such
requests, that is its workflow. When any unit may send them, plan it in the
department that handles them under the policy, ranked first there, ahead of the
handoff workflows. Never plan the same approval levels in two departments. When a
department reaches {MAX_PER_DEPARTMENT} workflows, keep both sides of every handoff and the
approval-levels workflow, and drop the others.

Write name, trigger, output and why in the language of the documents. Never
assume software, integrations or rules that the documents do not mention. Return
JSON only."""


def build_agent(name: str = "workflow_planner") -> Agent:
    return Agent(name=name, model=gemini(), instruction=INSTRUCTION,
                 output_schema=WorkflowPlan, generate_content_config=LOW_THINKING)


def _inputs(docs: list[tuple[str, bytes]], organization: dict, department_map: dict) -> list[types.Part]:
    return [*document_parts(docs), json_part("Organization JSON", organization),
            json_part("Department map", department_map)]


async def plan(docs: list[tuple[str, bytes]], organization: dict, department_map: dict) -> AgentResult:
    parts = [*_inputs(docs, organization, department_map),
             types.Part.from_text(text="Plan the workflows for every department.")]
    return await run_agent(build_agent(), parts)


async def repair(docs: list[tuple[str, bytes]], organization: dict, department_map: dict,
                 previous: dict | None, problems: list[str]) -> AgentResult:
    parts = [*_inputs(docs, organization, department_map), problems_part(previous, problems)]
    return await run_agent(build_agent("workflow_planner_repair"), parts)
