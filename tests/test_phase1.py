import os
import sys
import json
import pytest

# Ensure api directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "api")))

from schemas import (
    Organization,
    Workflow,
    PurchaseRequestForm,
    ExecutionTrace,
    AIReviewResponse,
)
from runner import run_workflow
from guard import (
    load_fixture,
    check_schema,
    check_step_actors,
    check_rule_numbers,
    validate_workflow_output,
)

@pytest.fixture
def org_data():
    return Organization.model_validate(load_fixture("novagear/organization.json"))

@pytest.fixture
def workflow_data():
    return Workflow.model_validate(load_fixture("workflow_fixture.json"))

# -----------------------------------------------------------------------------
# 1. Fixture Schema Validation Tests
# -----------------------------------------------------------------------------

def test_fixtures_validate_against_schemas(org_data, workflow_data):
    assert org_data.company == "NovaGear Inc."
    assert len(org_data.departments) == 4
    # CEO + 8 department roles = 9 roles
    assert len(org_data.roles) == 9

    assert workflow_data.workflow_name == "Purchase Request Approval"
    assert len(workflow_data.steps) == 6
    assert "Director" in workflow_data.unresolved_actors


# -----------------------------------------------------------------------------
# 2. Runner Threshold & Flow Tests (Section 13)
# -----------------------------------------------------------------------------

def test_runner_usd_750(org_data, workflow_data):
    """USD 750: Manager PASSED; Finance SKIPPED; Director SKIPPED; COMPLETED"""
    form = {
        "request_id": "PR-750",
        "requester": "Emma Chen",
        "department": "Operations",
        "item": "Office Chair",
        "estimated_cost": 750.0,
        "business_justification": "Ergonomic chair needed for Operations workstation.",
    }
    trace = run_workflow(workflow_data, org_data, form)
    assert trace.status == "COMPLETED"

    steps_by_id = {s.step_id: s for s in trace.steps}
    assert steps_by_id["completeness_review"].result == "PASSED"
    assert steps_by_id["manager_approval"].result == "PASSED"
    assert steps_by_id["finance_validation"].result == "SKIPPED"
    assert steps_by_id["director_approval"].result == "SKIPPED"
    assert steps_by_id["procurement"].result == "DONE"
    assert steps_by_id["notify_requester"].result == "DONE"

def test_runner_usd_1000_boundary(org_data, workflow_data):
    """USD 1,000: Manager + Finance PASSED (boundary); Director SKIPPED; COMPLETED"""
    form = {
        "request_id": "PR-1000",
        "requester": "Emma Chen",
        "department": "Operations",
        "item": "Monitor 4K",
        "estimated_cost": 1000.0,
        "business_justification": "High resolution monitor for digital design work.",
    }
    trace = run_workflow(workflow_data, org_data, form)
    assert trace.status == "COMPLETED"

    steps_by_id = {s.step_id: s for s in trace.steps}
    assert steps_by_id["manager_approval"].result == "PASSED"
    assert steps_by_id["finance_validation"].result == "PASSED"
    assert steps_by_id["director_approval"].result == "SKIPPED"
    assert steps_by_id["procurement"].result == "DONE"

def test_runner_usd_2400(org_data, workflow_data):
    """USD 2,400: Manager + Finance PASSED; Director SKIPPED; Procurement DONE; COMPLETED"""
    form = {
        "request_id": "PR-2026-0142",
        "requester": "Emma Chen",
        "department": "Operations",
        "item": "MacBook Pro",
        "estimated_cost": 2400.0,
        "business_justification": "Laptop required for a new Product Designer supporting the Operations team.",
    }
    trace = run_workflow(workflow_data, org_data, form)
    assert trace.status == "COMPLETED"

    steps_by_id = {s.step_id: s for s in trace.steps}
    assert steps_by_id["completeness_review"].result == "PASSED"
    assert steps_by_id["manager_approval"].result == "PASSED"
    assert "Operations Manager" in steps_by_id["manager_approval"].reason
    assert steps_by_id["finance_validation"].result == "PASSED"
    assert steps_by_id["director_approval"].result == "SKIPPED"
    assert steps_by_id["procurement"].result == "DONE"
    assert steps_by_id["notify_requester"].result == "DONE"
    assert trace.metrics.human_approvals == 2
    assert trace.metrics.ai_checks == 1

def test_runner_usd_5000_boundary(org_data, workflow_data):
    """USD 5,000: Manager + Finance PASSED (boundary); Director SKIPPED; COMPLETED"""
    form = {
        "request_id": "PR-5000",
        "requester": "Emma Chen",
        "department": "Operations",
        "item": "Specialized Lab Equipment",
        "estimated_cost": 5000.0,
        "business_justification": "Precision testing apparatus for operational quality assurance.",
    }
    trace = run_workflow(workflow_data, org_data, form)
    assert trace.status == "COMPLETED"

    steps_by_id = {s.step_id: s for s in trace.steps}
    assert steps_by_id["manager_approval"].result == "PASSED"
    assert steps_by_id["finance_validation"].result == "PASSED"
    assert steps_by_id["director_approval"].result == "SKIPPED"
    assert steps_by_id["procurement"].result == "DONE"

def test_runner_usd_8000_unresolved_actor(org_data, workflow_data):
    """USD 8,000: Director required but not in org chart → HUMAN_REVIEW; NEEDS_HUMAN_REVIEW"""
    form = {
        "request_id": "PR-8000",
        "requester": "Emma Chen",
        "department": "Operations",
        "item": "Industrial Server Rack",
        "estimated_cost": 8000.0,
        "business_justification": "High-capacity server hardware for warehouse operations infrastructure.",
    }
    trace = run_workflow(workflow_data, org_data, form)
    assert trace.status == "NEEDS_HUMAN_REVIEW"

    steps_by_id = {s.step_id: s for s in trace.steps}
    assert steps_by_id["manager_approval"].result == "PASSED"
    assert steps_by_id["finance_validation"].result == "PASSED"
    assert steps_by_id["director_approval"].result == "HUMAN_REVIEW"
    assert "Director" in steps_by_id["director_approval"].reason
    assert "procurement" not in steps_by_id  # Stopped before procurement

def test_runner_missing_justification(org_data, workflow_data):
    """Missing business justification → RETURNED before any approval"""
    form = {
        "request_id": "PR-MISSING",
        "requester": "Emma Chen",
        "department": "Operations",
        "item": "MacBook Pro",
        "estimated_cost": 2400.0,
        "business_justification": "",  # Blank / missing
    }
    trace = run_workflow(workflow_data, org_data, form)
    assert trace.status == "RETURNED"
    assert len(trace.steps) == 1
    assert trace.steps[0].result == "RETURNED"
    assert "business_justification" in trace.steps[0].reason

def test_runner_justification_na(org_data, workflow_data):
    """Justification 'N/A' → ai_review → HUMAN_REVIEW (never RETURNED by AI)"""
    form = {
        "request_id": "PR-NA",
        "requester": "Emma Chen",
        "department": "Operations",
        "item": "MacBook Pro",
        "estimated_cost": 2400.0,
        "business_justification": "N/A",  # Placeholder
    }
    trace = run_workflow(workflow_data, org_data, form)
    assert trace.status == "NEEDS_HUMAN_REVIEW"
    steps_by_id = {s.step_id: s for s in trace.steps}
    assert "completeness_review" in steps_by_id
    assert steps_by_id["completeness_review"].result == "HUMAN_REVIEW"
    assert "fallback check" in steps_by_id["completeness_review"].reason
    # Approval steps did not run
    assert "manager_approval" not in steps_by_id

def test_runner_ai_client_fallback_on_error(org_data, workflow_data):
    """Gemini raises an error or times out → fallback check used with 'fallback check' in reason"""
    form = {
        "request_id": "PR-FALLBACK",
        "requester": "Emma Chen",
        "department": "Operations",
        "item": "MacBook Pro",
        "estimated_cost": 2400.0,
        "business_justification": "Replacement laptop for design operations team member.",
    }
    def faulty_ai_client(f):
        raise TimeoutError("Gemini timed out after 25s")

    trace = run_workflow(workflow_data, org_data, form, ai_reviewer=faulty_ai_client)
    assert trace.status == "COMPLETED"
    steps_by_id = {s.step_id: s for s in trace.steps}
    assert steps_by_id["completeness_review"].result == "PASSED"
    assert "fallback check" in steps_by_id["completeness_review"].reason

# -----------------------------------------------------------------------------
# 3. Guard Checks 1, 2, 4 Tests (Section 7)
# -----------------------------------------------------------------------------

def test_guard_check_1_schema_parsing(org_data):
    """Check 1: It parses into the Pydantic schema"""
    invalid_data = {"workflow_name": 123}  # missing required fields, wrong type
    wf, errors = validate_workflow_output(invalid_data, org_data)
    assert wf is None
    assert len(errors) > 0

def test_guard_check_2_actors(org_data, workflow_data):
    """Check 2: Every step actor exists in organization.json, or is special, or in unresolved_actors"""
    # Clone workflow and add an unregistered actor
    wf_dict = workflow_data.model_dump()
    wf_dict["steps"].append({
        "id": "unknown_step",
        "type": "approval",
        "actor": "Vice President of Unknowns"
    })
    wf, errors = validate_workflow_output(wf_dict, org_data)
    assert wf is None
    assert any("Vice President of Unknowns" in err for err in errors)

def test_guard_check_4_rule_numbers(org_data, workflow_data):
    """Check 4: Every number in rule when.value appears in that rule's source"""
    wf_dict = workflow_data.model_dump()
    # Modify rule value to 9999 which does NOT appear in source
    wf_dict["rules"][0]["when"]["value"] = 9999
    wf, errors = validate_workflow_output(wf_dict, org_data)
    assert wf is None
    assert any("9999" in err for err in errors)
