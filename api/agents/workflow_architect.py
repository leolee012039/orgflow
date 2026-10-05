"""Workflow Architect: compiles one department's planned workflow into workflow.json for the runner."""

from typing import Optional

from google.adk import Agent
from google.genai import types

from agents.runtime import LOW_THINKING, AgentResult, document_parts, gemini, json_part, problems_part, run_agent
from schemas import Workflow

INSTRUCTION = """You are the Workflow Architect for OrgFlow.

You receive the company's documents (each introduced by "Document id: <id>"), the
organization JSON, one planned workflow of one department, and, when the workflow
starts from another department's workflow, the upstream workflow's form fields.
Compile the planned workflow into a workflow that a plain program can execute. You
only design it: the program runs it later, so every decision must be an explicit rule.

Fields:
- workflow_name: a short title in the language of the documents. opportunity_id: the
  planned workflow's id. department, starts_from, hands_to and output: copy them from
  the planned workflow.
- fields: the form that starts the workflow, besides "requester" and "department",
  which every form has. name: snake_case; label: what the documents call it; type:
  text, number, date or choice (with options). Include the information the documents
  require and every number a rule compares. When upstream form fields are given, the
  case arrives with exactly that information: use only upstream fields, with the same
  names, types and labels.
- required_fields: the fields the documents say must be filled in (field names, or
  "requester" and "department").
- rules: one rule per condition stated in the documents. Every amount that decides
  who must approve, or what work is done (for example how many vendor quotes are
  needed), becomes a rule, and the steps it changes use only_if with that rule's id.
  when.field is one of the form fields, when.op is
  one of < <= > >= ==, and when.value is the amount written out in full (for example
  12萬元 is 120000 and 三千元 is 3000). Read "A - B" or "between A and B" as inclusive,
  "below A" / 未達 A as < A, "above B" / 逾 B as > B, and 以上 / 以下 as inclusive. An
  approval that applies to several tiers needs one rule covering all of them. A step
  that applies only between two amounts (for example two quotes from USD 1,000 to
  USD 5,000) sets only_if to the rule for the lower end and also_if to the rule for
  the upper end. source:
  the passage the rule comes from, copied word for word (the whole table row or
  sentence, including the amounts).
- steps, in execution order:
  1. an "ai_review" step with actor "orgflow_ai" that checks the required
     information; set check to a one-line description of that rule and on_fail to
     "human_review";
  2. one "approval" step per approval the documents require, in their order (none
     when the documents require no approval). Use
     "requester.manager" only for the manager of the person who submitted the form,
     and only in a workflow that a person starts with a form. When an approval
     applies only under a condition, set only_if to that rule's id;
  3. one "task" step for each piece of work the department carries out;
  4. a "notification" step to actor "requester".
- actors: role ids from the organization JSON, department names from the
  organization JSON when the documents say a unit (not a person) does the step, or
  the special actors "requester", "requester.manager" and "orgflow_ai". If the
  documents require an approver that has no matching role in the organization, use
  the approver's name exactly as written, and also list that name in
  unresolved_actors. Never map such an approver onto a different existing role.
- amount_tiers: when the documents decide approvals by amount, list each amount
  tier once, in their order. field: the form field the amounts apply to. min and max
  are the amounts written at the tier's lower and upper end, in full like rule
  values, and null when the tier's passage writes no amount for that end. Copy the
  numbers as written, never adding or subtracting 1: for 逾二萬元，未達十萬元 min is
  20000 and max is 100000; for Above USD 5,000 min is 5000 and max is null. source:
  the tier's passage word for word. Leave amount_tiers empty when no approval depends
  on an amount.
- explanation: two sentences on why this workflow follows the documents.

When the planned workflow's basis is "org_chart", no policy states its rules: add
rules only for conditions a passage states, and route approvals to the department's
head. Use only the four step types: approval, ai_review, task, notification. Never
invent roles, thresholds or rules. Return JSON only."""


def build_agent(name: str = "workflow_architect") -> Agent:
    return Agent(name=name, model=gemini(), instruction=INSTRUCTION,
                 output_schema=Workflow, generate_content_config=LOW_THINKING)


def _inputs(docs: list[tuple[str, bytes]], organization: dict, planned: dict,
            upstream_fields: Optional[list[dict]]) -> list[types.Part]:
    parts = [*document_parts(docs), json_part("Organization JSON", organization),
             json_part("Planned workflow", planned)]
    if upstream_fields is not None:
        parts.append(json_part("Upstream form fields", upstream_fields))
    return parts


async def design(docs: list[tuple[str, bytes]], organization: dict, planned: dict,
                 upstream_fields: Optional[list[dict]] = None) -> AgentResult:
    parts = [*_inputs(docs, organization, planned, upstream_fields),
             types.Part.from_text(text="Compile the planned workflow.")]
    return await run_agent(build_agent(), parts)


async def repair(docs: list[tuple[str, bytes]], organization: dict, planned: dict,
                 upstream_fields: Optional[list[dict]], previous: dict | None, problems: list[str]) -> AgentResult:
    parts = [*_inputs(docs, organization, planned, upstream_fields), problems_part(previous, problems)]
    return await run_agent(build_agent("workflow_architect_repair"), parts)
