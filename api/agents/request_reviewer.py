"""Request Reviewer: the runner's only Gemini call (the ai_review step).

It may only check what the workflow's check describes. It can pass a request or
send it to a human; it can never reject one.
"""

import asyncio

from google.adk import Agent
from google.genai import types

from agents.runtime import LOW_THINKING, MODEL, json_part, run_agent
from schemas import AIReviewResponse, PurchaseRequestForm

INSTRUCTION = """You are the Request Reviewer for OrgFlow.

You receive one check from the company's policy, the list of required fields, and a
request. Check only that: every required field is present and meaningful. A
meaningful value is a real description, not a placeholder such as "N/A", "TBD",
"-", "none" or "test", and not a single vague word.

Do not judge the price, the vendor, or whether the purchase is a good idea. You
never reject a request.

Return decision "PASS" when the check is satisfied, otherwise
"NEEDS_HUMAN_REVIEW". Give one short reason per finding. Return JSON only."""


def build_agent() -> Agent:
    return Agent(name="request_reviewer", model=MODEL, instruction=INSTRUCTION,
                 output_schema=AIReviewResponse, generate_content_config=LOW_THINKING)


async def review(check: str, required_fields: list[str], form: PurchaseRequestForm) -> AIReviewResponse:
    parts = [
        json_part("Check", check),
        json_part("Required fields", required_fields),
        json_part("Request", form.model_dump()),
        types.Part.from_text(text="Review the request."),
    ]
    result = await run_agent(build_agent(), parts)
    if result.data is None:
        raise RuntimeError(result.error or "no answer")  # the runner falls back to its plain-code check
    return AIReviewResponse.model_validate(result.data)


def make_reviewer(check: str, required_fields: list[str]):
    """A blocking reviewer for the runner, which is plain synchronous code.

    Call the runner in a worker thread (asyncio.to_thread): each review then runs
    in that thread's own event loop.
    """
    def reviewer(form: PurchaseRequestForm) -> AIReviewResponse:
        return asyncio.run(review(check, required_fields, form))
    return reviewer
