"""decision_matches: did the reviewer reach the decision the case expects? Plain code, no judge."""

import json
import re


def _text(response) -> str:
    if isinstance(response, dict):
        return "".join(p.get("text", "") for p in response.get("parts", []) if isinstance(p, dict))
    return str(response or "")


def evaluate(instance):
    expected = instance.get("expected_decision")
    text = _text(instance.get("response"))
    match = re.search(r"\{.*\}", text, re.S)
    try:
        decision = json.loads(match.group(0)).get("decision") if match else None
    except json.JSONDecodeError:
        decision = None
    score = 1.0 if decision == expected else 0.0
    return {"score": score, "explanation": f"expected {expected}, got {decision}"}
