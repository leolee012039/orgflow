"""A person settles what the documents leave open, once, and every case after that follows it.

No test here calls Gemini: runs use the plain-code check, the endpoint a fake reviewer.
"""

from fastapi.testclient import TestClient

import main
from agents import request_reviewer
from runner import run_chain, run_workflow, with_decisions
from sample_docs import DISCOUNT, OPERATIONS, all_workflows, fixture, org, workflow
from schemas import AIReviewResponse, AmountDecision, ApproverDecision, Workflow

PURCHASE = {"requester": "Emma Chen", "department": "Operations", "requested_item": "MacBook Pro",
            "estimated_cost": 7500, "business_justification": "Laptop for a new product designer on the team."}
DISCOUNT_CASE = {"requester": "Ken Ito", "department": "Sales", "customer": "Acme", "product": "Headset",
                 "list_price": 300, "discount_percentage": 10, "reason": "Annual renewal for a key account."}
CEO_FOR_DIRECTOR = ApproverDecision(workflow_id=OPERATIONS, actor="Director", role_id="chief_executive_officer")


def step(trace, step_id):
    return next(s for s in trace.steps if s.step_id == step_id)


def results(trace):
    return {s.step_id: s.result for s in trace.steps}


# --- Who approves in place of an approver the org chart doesn't have --------------------

def test_without_a_decision_a_missing_director_stops_the_case():
    trace = run_workflow(workflow(OPERATIONS), org(), PURCHASE)
    assert trace.status == "NEEDS_HUMAN_REVIEW"
    assert step(trace, "step_director_approval").result == "HUMAN_REVIEW"


def test_the_role_a_person_names_approves_in_place_of_the_missing_director():
    trace = run_workflow(workflow(OPERATIONS), org(), PURCHASE, decisions=[CEO_FOR_DIRECTOR])
    assert trace.status == "COMPLETED"
    director = step(trace, "step_director_approval")
    assert director.result == "PASSED"
    assert director.actor == "chief_executive_officer" and director.stands_in_for == "Director"
    assert director.reason == "Approved by simulated Chief Executive Officer (CEO), in place of Director"
    # Only the step that named the Director changes
    assert step(trace, "step_finance_validation").stands_in_for is None


def test_a_decision_still_follows_the_policy_amounts():
    trace = run_workflow(workflow(OPERATIONS), org(), {**PURCHASE, "estimated_cost": 2400}, decisions=[CEO_FOR_DIRECTOR])
    assert trace.status == "COMPLETED"
    assert step(trace, "step_director_approval").result == "SKIPPED"


def test_the_requesters_own_department_head_can_stand_in():
    decision = ApproverDecision(workflow_id=OPERATIONS, actor="Director", role_id="requester.manager")
    trace = run_workflow(workflow(OPERATIONS), org(), PURCHASE, decisions=[decision])
    assert trace.status == "COMPLETED"
    director = step(trace, "step_director_approval")
    assert director.actor == "requester.manager" and director.stands_in_for == "Director"
    assert director.reason == "Approved by simulated Operations Manager, in place of Director"

def test_a_decision_changes_nothing_when_it_doesnt_fit():
    for decision in (
        ApproverDecision(workflow_id=DISCOUNT, actor="Director", role_id="chief_executive_officer"),  # other workflow
        ApproverDecision(workflow_id=OPERATIONS, actor="Director", role_id="vice_president"),  # no such role
        ApproverDecision(workflow_id=OPERATIONS, actor="Finance Manager", role_id="accountant"),  # not missing
    ):
        trace = run_workflow(workflow(OPERATIONS), org(), PURCHASE, decisions=[decision])
        assert trace.status == "NEEDS_HUMAN_REVIEW", decision
        assert step(trace, "step_finance_validation").stands_in_for is None


def test_settling_leaves_the_built_workflow_as_it_was():
    wf = workflow(OPERATIONS)
    settled, stand_ins, _ = with_decisions(wf, org(), [CEO_FOR_DIRECTOR])
    assert wf.unresolved_actors == ["Director"] and settled.unresolved_actors == []
    assert stand_ins == {"step_director_approval": "Director"}
    assert next(s for s in wf.steps if s.id == "step_director_approval").actor == "Director"


def test_with_the_decision_a_7500_purchase_runs_through_three_departments():
    stopped = run_chain(all_workflows(), org(), OPERATIONS, PURCHASE)
    assert [leg.department for leg in stopped.legs] == ["Operations"]
    trace = run_chain(all_workflows(), org(), OPERATIONS, PURCHASE, decisions=[CEO_FOR_DIRECTOR])
    assert trace.status == "COMPLETED"
    assert [leg.department for leg in trace.legs] == ["Operations", "Procurement", "Finance"]


# --- Which level owns the exact amount the policy leaves open -----------------------------

def test_without_a_decision_exactly_ten_percent_stops():
    trace = run_workflow(workflow(DISCOUNT), org(), DISCOUNT_CASE)
    assert trace.status == "NEEDS_HUMAN_REVIEW" and trace.steps[-1].step_id == "amount_check"


def test_exactly_ten_percent_goes_to_the_level_the_person_chose():
    above = run_workflow(workflow(DISCOUNT), org(), DISCOUNT_CASE,
                         decisions=[AmountDecision(workflow_id=DISCOUNT, field="discount_percentage", amount=10, level="above")])
    assert above.status == "COMPLETED"
    assert results(above)["step_sales_manager_approval"] == "PASSED"
    assert results(above)["step_sales_representative_approval"] == "SKIPPED"
    assert above.steps[0].step_id == "amount_decision_discount_percentage"
    assert above.steps[0].source == "Above 10% up to 20% Sales Manager approval"

    below = run_workflow(workflow(DISCOUNT), org(), DISCOUNT_CASE,
                         decisions=[AmountDecision(workflow_id=DISCOUNT, field="discount_percentage", amount=10, level="below")])
    assert below.status == "COMPLETED"
    assert results(below)["step_sales_representative_approval"] == "PASSED"
    assert results(below)["step_sales_manager_approval"] == "SKIPPED"
    assert below.steps[0].source == "Below 10% Sales Representative approval"


def test_an_amount_decision_moves_only_that_exact_amount():
    decision = AmountDecision(workflow_id=DISCOUNT, field="discount_percentage", amount=10, level="above")
    for pct, approver in ((9, "step_sales_representative_approval"), (11, "step_sales_manager_approval")):
        before = run_workflow(workflow(DISCOUNT), org(), {**DISCOUNT_CASE, "discount_percentage": pct})
        after = run_workflow(workflow(DISCOUNT), org(), {**DISCOUNT_CASE, "discount_percentage": pct}, decisions=[decision])
        assert results(before) == results(after)
        assert results(after)[approver] == "PASSED"
        assert not any(s.step_id.startswith("amount_decision") for s in after.steps)


def test_an_amount_decision_for_another_amount_does_not_settle_this_one():
    decision = AmountDecision(workflow_id=DISCOUNT, field="discount_percentage", amount=20, level="above")
    trace = run_workflow(workflow(DISCOUNT), org(), DISCOUNT_CASE, decisions=[decision])
    assert trace.status == "NEEDS_HUMAN_REVIEW" and trace.steps[-1].step_id == "amount_check"


# --- Endpoint -----------------------------------------------------------------------------

client = TestClient(main.app)


def chain_body(**extra):
    return {"workflows": [w.model_dump() for w in all_workflows()], "organization": fixture("organization.json"),
            "start_id": OPERATIONS, "request": PURCHASE, **extra}


def test_run_chain_endpoint_follows_decisions(monkeypatch):
    monkeypatch.setattr(request_reviewer, "make_reviewer", lambda check, fields: (
        lambda f: AIReviewResponse(decision="PASS", reasons=[])))
    decision = {**CEO_FOR_DIRECTOR.model_dump(), "decided_at": "2026-10-06T09:00:00Z"}  # extra fields are fine
    resp = client.post("/api/run_chain", json=chain_body(decisions=[decision]))
    assert resp.status_code == 200
    trace = resp.json()
    assert trace["status"] == "COMPLETED" and len(trace["legs"]) == 3
    director = next(s for s in trace["legs"][0]["trace"]["steps"] if s["step_id"] == "step_director_approval")
    assert director["stands_in_for"] == "Director"


def test_run_chain_endpoint_rejects_malformed_decisions():
    bad = [{"kind": "approver", "workflow_id": OPERATIONS, "actor": "Director"},  # no role
           {"kind": "amount", "workflow_id": DISCOUNT, "field": "discount_percentage", "amount": 10, "level": "middle"},
           {"kind": "vote", "workflow_id": OPERATIONS}]
    for decision in bad:
        assert client.post("/api/run_chain", json=chain_body(decisions=[decision])).status_code == 422, decision
    too_many = [CEO_FOR_DIRECTOR.model_dump()] * 51
    assert client.post("/api/run_chain", json=chain_body(decisions=too_many)).status_code == 422


# --- Found in review: an amount decision touches only the two levels' own rules ---------------

def quotes_workflow(tiers=True, director_value=5000, director_op=">"):
    """Approvals by amount, plus a quotes rule from another table at the same number."""
    return Workflow.model_validate({
        "workflow_name": "Purchase approval", "opportunity_id": "purchase_approval", "department": "Operations",
        "fields": [{"name": "estimated_cost", "label": "Estimated Cost", "type": "number", "options": []}],
        "required_fields": ["estimated_cost"],
        "rules": [
            {"id": "r_low", "when": {"field": "estimated_cost", "op": "<", "value": 5000}, "source": "Under $5,000: Manager"},
            {"id": "r_high", "when": {"field": "estimated_cost", "op": director_op, "value": director_value},
             "source": "Over $5,000: Director"},
            {"id": "r_quotes", "when": {"field": "estimated_cost", "op": ">=", "value": 5000},
             "source": "$5,000 or more: three quotes"},
        ],
        "steps": [
            {"id": "manager", "type": "approval", "actor": "operations_manager", "only_if": "r_low"},
            {"id": "director", "type": "approval", "actor": "finance_manager", "only_if": "r_high"},
            {"id": "quotes", "type": "approval", "actor": "procurement_manager", "only_if": "r_quotes"},
        ],
        "unresolved_actors": [],
        "amount_tiers": [
            {"field": "estimated_cost", "min": None, "max": 5000, "source": "Under $5,000: Manager"},
            {"field": "estimated_cost", "min": 5000, "max": None, "source": "Over $5,000: Director"},
        ] if tiers else [],
        "starts_from": None, "hands_to": None, "output": "Approved purchase", "explanation": "Test workflow.",
    })


def at_5000(wf, decision):
    return run_workflow(wf, org(), {"requester": "Emma Chen", "department": "Operations", "estimated_cost": 5000},
                        decisions=[decision])


def amount(level):
    return AmountDecision(workflow_id="purchase_approval", field="estimated_cost", amount=5000, level=level)


def test_an_amount_decision_leaves_rules_from_another_table_alone():
    below = at_5000(quotes_workflow(), amount("below"))
    assert below.status == "COMPLETED"
    assert results(below) == {"amount_decision_estimated_cost": "DONE", "manager": "PASSED",
                              "director": "SKIPPED", "quotes": "PASSED"}
    above = at_5000(quotes_workflow(), amount("above"))
    assert results(above) == {"amount_decision_estimated_cost": "DONE", "manager": "SKIPPED",
                              "director": "PASSED", "quotes": "PASSED"}


def test_an_amount_decision_does_nothing_once_the_policy_leaves_no_gap():
    # The workflow was rebuilt and the levels no longer leave 5,000 open: the old decision is ignored
    trace = at_5000(quotes_workflow(tiers=False), amount("below"))
    assert results(trace) == {"manager": "SKIPPED", "director": "SKIPPED", "quotes": "PASSED"}


def test_an_amount_decision_whose_rules_dont_meet_the_amount_still_stops_the_case():
    # The Director rule was written for 5,001: no rule of the chosen level can take 5,000
    trace = at_5000(quotes_workflow(director_value=5001), amount("above"))
    assert trace.status == "NEEDS_HUMAN_REVIEW" and trace.steps[-1].step_id == "amount_check"


def test_an_amount_decision_the_rules_already_agree_with_takes_effect():
    # Gemini wrote the Director rule as >= 5,000 although the words leave 5,000 open
    trace = at_5000(quotes_workflow(director_op=">="), amount("above"))
    assert results(trace) == {"amount_decision_estimated_cost": "DONE", "manager": "SKIPPED",
                              "director": "PASSED", "quotes": "PASSED"}
    # The other choice takes 5,000 away from the Director's level, not from the quotes rule
    trace = at_5000(quotes_workflow(director_op=">="), amount("below"))
    assert results(trace) == {"amount_decision_estimated_cost": "DONE", "manager": "PASSED",
                              "director": "SKIPPED", "quotes": "PASSED"}
