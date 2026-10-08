"""The answer formats sent to Gemini.

Gemini answers 400 INVALID_ARGUMENT to a format with maxItems: from 6 Oct, when the step limit was written
as Field(max_length=...), every live workflow build failed, and no test noticed because tests never call
Gemini. Limits on an answer are checked in code after it arrives, never in the format.
"""

import json

import pytest

from agents import (department_analyst, document_reader, organization_analyst, request_reviewer,
                    workflow_architect, workflow_planner)
from schemas import MAX_STEPS, Workflow

AGENTS = [department_analyst, document_reader, organization_analyst, request_reviewer, workflow_architect,
          workflow_planner]
REJECTED_BY_GEMINI = ("maxItems",)


@pytest.mark.parametrize("module", AGENTS, ids=lambda m: m.__name__.rsplit(".", 1)[-1])
def test_no_answer_format_has_what_gemini_rejects(module):
    schema = json.dumps(module.build_agent().output_schema.model_json_schema())
    assert [k for k in REJECTED_BY_GEMINI if f'"{k}"' in schema] == []


def test_the_step_limit_still_holds():
    step = {"id": "s", "type": "task", "actor": "Clerk"}
    longest = {"workflow_name": "w", "opportunity_id": "w", "required_fields": [], "explanation": "",
               "steps": [step] * MAX_STEPS}
    Workflow.model_validate(longest)
    with pytest.raises(ValueError, match=f"at most {MAX_STEPS} steps"):
        Workflow.model_validate({**longest, "steps": [step] * (MAX_STEPS + 1)})
