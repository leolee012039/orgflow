"""Workflow Architect: compiles one opportunity into workflow.json for the runner."""

from google.adk import Agent
from google.genai import types

from agents.runtime import LOW_THINKING, MODEL, AgentResult, json_part, pdf_part, problems_part, run_agent
from schemas import Workflow

REQUEST_FIELDS = {
    "requester": "name of the person asking",
    "department": "department of the requester",
    "item": "what is being requested",
    "estimated_cost": "number, in USD",
    "business_justification": "why it is needed",
}

INSTRUCTION = """You are the Workflow Architect for OrgFlow.

You receive the company's documents (each introduced by "Document id: <id>"), the
organization JSON, the chosen opportunity, and the fields of the request form.
Compile the opportunity into a workflow that a plain program can execute. You only
design it: the program runs it later, so every decision must be an explicit rule.

Fields:
- workflow_name: a short title. opportunity_id: the chosen opportunity's id.
- required_fields: the request form fields that the policy says every request must include.
- rules: one rule per condition stated in the policy. when.field is a request form
  field, when.op is one of < <= > >= ==, when.value is a number for amounts.
  Read "A - B" or "between A and B" as inclusive, "below A" as < A and "above B" as > B.
  An approval that applies to several tiers needs one rule covering all of them
  (for example, if Legal review were required in every tier from USD 10,000 upward,
  the rule would be estimated_cost >= 10000).
  source: the policy passage the rule comes from, copied word for word (the whole
  table row or sentence, including the amounts).
- steps, in execution order:
  1. an "ai_review" step with actor "orgflow_ai" that checks the policy's
     required-information rule; set check to a one-line description of that rule
     and on_fail to "human_review";
  2. one "approval" step per approval the policy requires, in the policy's order.
     Use actor "requester.manager" for the requester's own manager. When an
     approval applies only under a condition, set only_if to that rule's id;
  3. a "task" step for the role that carries out the work after approval;
  4. a "notification" step to actor "requester".
- actors: use role ids from the organization JSON, or the special actors
  "requester", "requester.manager" and "orgflow_ai". If the policy requires an
  approver that has no matching role in the organization, use the approver's name
  exactly as the policy writes it, and also list that name in unresolved_actors.
  Never map such an approver onto a different existing role.
- explanation: two sentences on why this workflow follows the policy.

Use only the four step types: approval, ai_review, task, notification. Never invent
roles, thresholds or rules. Return JSON only."""


def build_agent(name: str = "workflow_architect") -> Agent:
    return Agent(name=name, model=MODEL, instruction=INSTRUCTION,
                 output_schema=Workflow, generate_content_config=LOW_THINKING)


def _inputs(org_pdf: bytes, policy_pdf: bytes, organization: dict, opportunity: dict) -> list[types.Part]:
    return [*pdf_part("org_chart", org_pdf), *pdf_part("policy", policy_pdf),
            json_part("Organization JSON", organization),
            json_part("Chosen opportunity", opportunity),
            json_part("Request form fields", REQUEST_FIELDS)]


async def design(org_pdf: bytes, policy_pdf: bytes, organization: dict, opportunity: dict) -> AgentResult:
    parts = [*_inputs(org_pdf, policy_pdf, organization, opportunity),
             types.Part.from_text(text="Compile the chosen opportunity into a workflow.")]
    return await run_agent(build_agent(), parts)


async def repair(org_pdf: bytes, policy_pdf: bytes, organization: dict, opportunity: dict,
                 previous: dict | None, problems: list[str]) -> AgentResult:
    parts = [*_inputs(org_pdf, policy_pdf, organization, opportunity), problems_part(previous, problems)]
    return await run_agent(build_agent("workflow_architect_repair"), parts)
