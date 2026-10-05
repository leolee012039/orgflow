"""Department map, workflow plan, building one department's workflow, and chained runs across departments.

No test here calls Gemini: agent calls are replaced with fakes or saved answers.
"""

import asyncio
import json

from fastapi.testclient import TestClient

import main
import pipeline
from agents import department_analyst, request_reviewer, workflow_architect, workflow_planner
from agents.runtime import AgentResult
from guard import validate_department_map, validate_workflow_output, validate_workflow_plan
from runner import next_workflow, run_chain
from sample_docs import (
    CREDIT,
    DISCOUNT,
    DOC_TEXT,
    DOCS,
    OPERATIONS,
    PAYMENT,
    PROCUREMENT,
    all_workflows,
    department_map,
    fixture,
    org,
    planned,
    upload_files,
    workflow,
)
from schemas import AIReviewResponse, RequestForm

PURCHASE = {"requester": "Emma Chen", "department": "Operations", "requested_item": "MacBook Pro",
            "estimated_cost": 2400, "business_justification": "Laptop for a new product designer on the team."}


# --- Department map -------------------------------------------------------------------

def test_saved_map_passes_the_guard():
    dmap, problems = validate_department_map(fixture("department_map.json"), org(), DOC_TEXT)
    assert problems == [] and dmap is not None
    assert {(h.from_dept, h.to) for h in dmap.handoffs} >= {("Operations", "Procurement"), ("Procurement", "Finance")}


def test_map_rejects_unknown_departments_and_invented_quotes():
    data = fixture("department_map.json")
    data["departments"][0]["name"] = "Marketing"
    data["handoffs"].append({"from": "Sales", "to": "Legal", "what": "contracts",
                             "evidence": {"doc": "policy_1", "quote": "Sales sends every contract to Legal."}})
    data["handoffs"].append({"from": "Finance", "to": "Finance", "what": "itself",
                             "evidence": {"doc": "org_chart", "quote": "Validates amounts, policy rules, and required approvals."}})
    dmap, problems = validate_department_map(data, org(), DOC_TEXT)
    assert dmap is None
    assert any("'Marketing' is not a department" in p for p in problems)
    assert any("'Legal'" in p for p in problems)
    assert any("Sales sends every contract" in p for p in problems)
    assert any("same department" in p for p in problems)


def test_map_uses_the_organizations_spelling():
    data = fixture("department_map.json")
    data["departments"][0]["name"] = data["departments"][0]["name"].lower()
    data["handoffs"][0]["to"] = data["handoffs"][0]["to"].upper()
    dmap, problems = validate_department_map(data, org(), DOC_TEXT)
    assert problems == []
    assert {d.name for d in dmap.departments} == {"Sales", "Operations", "Finance", "Procurement"}
    assert all(h.to in {"Sales", "Operations", "Finance", "Procurement"} for h in dmap.handoffs)


def test_map_rejects_a_handoff_to_a_department_without_a_profile():
    data = fixture("department_map.json")
    data["departments"] = [d for d in data["departments"] if d["name"] != "Procurement"]
    _, problems = validate_department_map(data, org(), DOC_TEXT)
    assert any("'Procurement', which has no profile" in p for p in problems)


def test_map_rejects_a_department_with_no_work():
    data = fixture("department_map.json")
    data["departments"][0]["work"] = []
    _, problems = validate_department_map(data, org(), DOC_TEXT)
    assert any("lists no work" in p for p in problems)


# --- Workflow plan --------------------------------------------------------------------

def test_saved_plan_passes_the_guard_and_covers_every_department():
    plan, problems = validate_workflow_plan(fixture("workflow_plan.json"), department_map(), DOC_TEXT)
    assert problems == [] and plan is not None
    assert {w.department for w in plan.workflows} == {"Sales", "Operations", "Finance", "Procurement"}


def test_plan_links_only_along_handoffs_on_the_map():
    data = fixture("workflow_plan.json")
    sales = next(w for w in data["workflows"] if w["department"] == "Sales")
    sales["hands_to"] = "Procurement"  # the map has no Sales -> Procurement handoff
    _, problems = validate_workflow_plan(data, department_map(), DOC_TEXT)
    assert any("no handoff 'Sales' -> 'Procurement'" in p for p in problems)


def test_plan_uses_the_maps_spelling():
    data = fixture("workflow_plan.json")
    for w in data["workflows"]:
        w["department"] = w["department"].lower()
        w["starts_from"] = w["starts_from"].upper() if w["starts_from"] else None
    plan, problems = validate_workflow_plan(data, department_map(), DOC_TEXT)
    assert problems == []
    procurement = next(w for w in plan.workflows if w.id == PROCUREMENT)
    assert (procurement.department, procurement.starts_from, procurement.hands_to) == ("Procurement", "Operations", "Finance")


def test_plan_rejects_workflows_that_hand_cases_round_in_a_loop():
    data = fixture("workflow_plan.json")
    dmap = department_map()
    dmap.handoffs.append(dmap.handoffs[0].model_copy(update={"from_dept": "Finance", "to": "Operations"}))
    for w in data["workflows"]:
        if w["id"] == OPERATIONS:
            w["starts_from"] = "Finance"
        if w["id"] == PAYMENT:
            w["hands_to"] = "Operations"
    _, problems = validate_workflow_plan(data, dmap, DOC_TEXT)
    assert any("loop" in p for p in problems)


def test_plan_needs_every_department_and_policy_quotes_for_policy_basis():
    data = fixture("workflow_plan.json")
    data["workflows"] = [w for w in data["workflows"] if w["department"] != "Sales"]
    data["workflows"][0]["evidence"] = [{"doc": "org_chart", "quote": "Submits operational purchase requests."}]
    _, problems = validate_workflow_plan(data, department_map(), DOC_TEXT)
    assert any("'Sales' has no planned workflow" in p for p in problems)
    assert any("quotes no policy document" in p for p in problems)


# --- Building one department's workflow -----------------------------------------------

def test_every_saved_workflow_passes_the_guard_with_its_upstream():
    upstreams = {PROCUREMENT: OPERATIONS, PAYMENT: PROCUREMENT, CREDIT: DISCOUNT}
    for wf_id in (OPERATIONS, PROCUREMENT, PAYMENT, DISCOUNT, CREDIT):
        up = upstreams.get(wf_id)
        upstream_fields = pipeline.fields_of(workflow(up)) if up else None
        wf, problems = validate_workflow_output(fixture(f"workflows/{wf_id}.json"), org(), DOC_TEXT,
                                                planned(wf_id), upstream_fields)
        assert problems == [] and wf is not None, (wf_id, problems)


def test_a_handoff_workflow_may_only_use_data_that_arrives_with_the_case():
    data = fixture(f"workflows/{PROCUREMENT}.json")
    data["fields"].append({"name": "vendor_name", "label": "Vendor", "type": "text", "options": []})
    _, problems = validate_workflow_output(data, org(), DOC_TEXT, planned(PROCUREMENT),
                                           pipeline.fields_of(workflow(OPERATIONS)))
    assert any("'vendor_name' does not arrive from the upstream workflow" in p for p in problems)


def test_a_handoff_workflow_keeps_its_place_and_has_no_requester_manager():
    data = fixture(f"workflows/{PROCUREMENT}.json")
    data["hands_to"] = None
    data["steps"][4]["actor"] = "requester.manager"
    _, problems = validate_workflow_output(data, org(), DOC_TEXT, planned(PROCUREMENT))
    assert any("hands_to must be 'Finance'" in p for p in problems)
    assert any("uses requester.manager" in p for p in problems)


def test_rules_and_fields_must_match():
    data = fixture(f"workflows/{DISCOUNT}.json")
    data["rules"][0]["when"]["field"] = "estimated_cost"
    data["fields"].append({"name": "requester", "label": "Requester", "type": "text", "options": []})
    _, problems = validate_workflow_output(data, org(), DOC_TEXT, planned(DISCOUNT))
    assert any("uses 'estimated_cost', which is not a form field" in p for p in problems)
    assert any("'requester' is on every form already" in p for p in problems)


def test_another_departments_amounts_dont_force_rules():
    # The credit check has no amounts in its passages, although the purchasing policy has many
    data = fixture(f"workflows/{CREDIT}.json")
    data["steps"].insert(1, {"id": "a1", "type": "approval", "actor": "finance_manager"})
    data["steps"].insert(2, {"id": "a2", "type": "approval", "actor": "accountant"})
    wf, problems = validate_workflow_output(data, org(), DOC_TEXT, planned(CREDIT),
                                            pipeline.fields_of(workflow(DISCOUNT)))
    assert problems == [] and wf is not None


# --- Stages with fake agents ----------------------------------------------------------

def test_map_and_plan_stages(monkeypatch):
    async def fake_map(docs, organization):
        return AgentResult(fixture("department_map.json"), None, 7000)

    async def fake_plan(docs, organization, dmap):
        assert {d["name"] for d in dmap["departments"]} == {"Sales", "Operations", "Finance", "Procurement"}
        return AgentResult(fixture("workflow_plan.json"), None, 9000)

    monkeypatch.setattr(department_analyst, "analyze", fake_map)
    monkeypatch.setattr(workflow_planner, "plan", fake_plan)
    dmap = asyncio.run(pipeline.map_departments(DOCS, org()))
    assert dmap.origin == "live"
    plan = asyncio.run(pipeline.plan_workflows(DOCS, org(), dmap.value))
    assert plan.origin == "live" and len(plan.value.workflows) == 5


def test_build_stage_passes_upstream_fields_and_reports_findings(monkeypatch):
    seen = {}

    async def fake_design(docs, organization, planned_json, upstream_fields):
        seen["upstream"] = upstream_fields
        return AgentResult(fixture(f"workflows/{DISCOUNT}.json"), None, 6000)

    monkeypatch.setattr(workflow_architect, "design", fake_design)
    result = asyncio.run(pipeline.build_workflow(DOCS, org(), planned(DISCOUNT)))
    assert result.origin == "live" and seen["upstream"] is None
    assert [(g["field"], g["amount"], g["kind"]) for g in result.extras["amount_gaps"]] == \
        [("discount_percentage", 10.0, "gap")]

    async def fake_design_credit(docs, organization, planned_json, upstream_fields):
        seen["upstream"] = upstream_fields
        return AgentResult(fixture(f"workflows/{CREDIT}.json"), None, 6000)

    monkeypatch.setattr(workflow_architect, "design", fake_design_credit)
    result = asyncio.run(pipeline.build_workflow(DOCS, org(), planned(CREDIT), workflow(DISCOUNT)))
    assert result.origin == "live"
    assert [f["name"] for f in seen["upstream"]] == ["customer", "product", "list_price", "discount_percentage", "reason"]


def test_build_falls_back_to_the_saved_workflow_for_the_sample(monkeypatch):
    async def bad(*args):
        return AgentResult({"workflow_name": 1}, None, 10)

    monkeypatch.setattr(workflow_architect, "design", bad)
    monkeypatch.setattr(workflow_architect, "repair", bad)
    result = asyncio.run(pipeline.build_workflow(DOCS, org(), planned(OPERATIONS)))
    assert result.origin == "fixture" and result.value.department == "Operations"
    assert result.extras["gaps"][0]["actor"] == "Director"
    result = asyncio.run(pipeline.build_workflow(DOCS, org(), planned(PROCUREMENT), workflow(OPERATIONS)))
    assert result.origin == "fixture" and result.value.upstream_id == OPERATIONS


def test_a_saved_workflow_is_not_used_against_a_different_upstream(monkeypatch):
    async def bad(*args):
        return AgentResult({"workflow_name": 1}, None, 10)

    monkeypatch.setattr(workflow_architect, "design", bad)
    monkeypatch.setattr(workflow_architect, "repair", bad)
    upstream = workflow(OPERATIONS)
    upstream.fields[0].name = "item_name"  # built live with other field names than the saved Procurement expects
    result = asyncio.run(pipeline.build_workflow(DOCS, org(), planned(PROCUREMENT), upstream))
    assert result.origin == "unverified" and result.value is None


def test_the_link_to_the_upstream_is_set_by_code_not_by_gemini(monkeypatch):
    async def fake_design(docs, organization, planned_json, upstream_fields):
        data = fixture(f"workflows/{PROCUREMENT}.json")
        data["upstream_id"] = "something_gemini_made_up"
        return AgentResult(data, None, 10)

    monkeypatch.setattr(workflow_architect, "design", fake_design)
    linked = asyncio.run(pipeline.build_workflow(DOCS, org(), planned(PROCUREMENT), workflow(OPERATIONS)))
    assert linked.value.upstream_id == OPERATIONS
    alone = asyncio.run(pipeline.build_workflow(DOCS, org(), planned(PROCUREMENT)))
    assert alone.value.upstream_id is None


# --- Chained runs ---------------------------------------------------------------------

def test_next_workflow_follows_the_handoff():
    workflows = all_workflows()
    assert next_workflow(workflow(OPERATIONS), workflows).opportunity_id == PROCUREMENT
    assert next_workflow(workflow(PROCUREMENT), workflows).opportunity_id == PAYMENT
    assert next_workflow(workflow(DISCOUNT), workflows).opportunity_id == CREDIT
    assert next_workflow(workflow(PAYMENT), workflows) is None


def test_a_purchase_moves_through_three_departments():
    trace = run_chain(all_workflows(), org(), OPERATIONS, PURCHASE)
    assert trace.status == "COMPLETED" and trace.waiting_for is None
    assert [leg.department for leg in trace.legs] == ["Operations", "Procurement", "Finance"]
    procurement = {s.step_id: s.result for s in trace.legs[1].trace.steps}
    assert procurement["step_obtain_two_quotes"] == "DONE"  # 2,400 is between 1,000 and 5,000
    assert procurement["step_obtain_one_quote"] == procurement["step_obtain_three_quotes"] == "SKIPPED"


def test_the_chain_stops_where_a_department_stops():
    trace = run_chain(all_workflows(), org(), OPERATIONS, {**PURCHASE, "estimated_cost": 8000})
    assert trace.status == "NEEDS_HUMAN_REVIEW"
    assert [leg.department for leg in trace.legs] == ["Operations"]  # the Director doesn't exist
    assert trace.legs[0].trace.steps[-1].actor == "Director"


def test_a_chain_waits_for_a_department_with_no_built_workflow():
    workflows = [w for w in all_workflows() if w.opportunity_id != PAYMENT]
    trace = run_chain(workflows, org(), OPERATIONS, PURCHASE)
    assert trace.status == "COMPLETED" and trace.waiting_for == "Finance"
    assert [leg.department for leg in trace.legs] == ["Operations", "Procurement"]


def test_a_chain_never_loops():
    loop = [workflow(OPERATIONS), workflow(PROCUREMENT)]
    loop[1].hands_to, loop[0].upstream_id = "Operations", PROCUREMENT
    trace = run_chain(loop, org(), OPERATIONS, PURCHASE)
    assert [leg.workflow_id for leg in trace.legs] == [OPERATIONS, PROCUREMENT]


def test_a_case_goes_only_to_the_workflow_built_against_its_workflow():
    # A second Operations workflow also hands to Procurement, with fields Procurement never saw
    other = workflow(OPERATIONS)
    other.opportunity_id = "operations_equipment_request"
    other.fields[0].name = "equipment"
    workflows = [other, *all_workflows()]
    assert next_workflow(other, workflows) is None  # Procurement was built against the purchase request
    assert next_workflow(workflow(OPERATIONS), workflows).opportunity_id == PROCUREMENT
    trace = run_chain(workflows, org(), OPERATIONS, PURCHASE)
    assert [leg.department for leg in trace.legs] == ["Operations", "Procurement", "Finance"]


def test_numbers_too_large_to_compare_are_refused():
    body = {"workflows": [w.model_dump() for w in all_workflows()], "organization": fixture("organization.json"),
            "start_id": OPERATIONS, "request": {**PURCHASE, "estimated_cost": 10**400}}
    assert client.post("/api/run_chain", json=body).status_code == 422


def test_exactly_ten_percent_discount_stops_before_any_approval():
    case = {"requester": "Ken Ito", "department": "Sales", "customer": "Acme", "product": "Headset",
            "list_price": 300, "discount_percentage": 10, "reason": "Annual renewal for a key account."}
    trace = run_chain(all_workflows(), org(), DISCOUNT, case)
    assert trace.status == "NEEDS_HUMAN_REVIEW"
    assert trace.legs[0].trace.steps[0].step_id == "amount_check"
    assert "exactly 10" in trace.legs[0].trace.steps[0].reason


# --- Endpoints ------------------------------------------------------------------------

client = TestClient(main.app)
ORG_JSON = json.dumps(fixture("organization.json"))


def test_map_plan_and_build_endpoints(monkeypatch):
    async def fake_map(docs, organization):
        return AgentResult(fixture("department_map.json"), None, 7000)

    async def fake_plan(docs, organization, dmap):
        return AgentResult(fixture("workflow_plan.json"), None, 9000)

    async def fake_design(docs, organization, planned_json, upstream_fields):
        return AgentResult(fixture(f"workflows/{PROCUREMENT}.json"), None, 6000)

    monkeypatch.setattr(department_analyst, "analyze", fake_map)
    monkeypatch.setattr(workflow_planner, "plan", fake_plan)
    monkeypatch.setattr(workflow_architect, "design", fake_design)

    resp = client.post("/api/map", files=upload_files(), data={"organization": ORG_JSON})
    assert resp.status_code == 200 and resp.json()["handoffs"][0]["from"]
    resp = client.post("/api/plan", files=upload_files(),
                       data={"organization": ORG_JSON, "department_map": json.dumps(fixture("department_map.json"))})
    assert resp.status_code == 200 and len(resp.json()["workflows"]) == 5
    resp = client.post("/api/build", files=upload_files(), data={
        "organization": ORG_JSON, "planned": json.dumps(planned(PROCUREMENT).model_dump()),
        "upstream": json.dumps(fixture(f"workflows/{OPERATIONS}.json"))})
    assert resp.status_code == 200
    body = resp.json()
    assert body["department"] == "Procurement" and body["gaps"] == [] and body["origin"] == "live"


def test_run_chain_endpoint(monkeypatch):
    monkeypatch.setattr(request_reviewer, "make_reviewer", lambda check, fields: (
        lambda f: AIReviewResponse(decision="PASS", reasons=[])))
    body = {"workflows": [w.model_dump() for w in all_workflows()], "organization": fixture("organization.json"),
            "start_id": OPERATIONS, "request": PURCHASE, "handoffs_before": {OPERATIONS: 3}}
    resp = client.post("/api/run_chain", json=body)
    assert resp.status_code == 200
    trace = resp.json()
    assert [leg["department"] for leg in trace["legs"]] == ["Operations", "Procurement", "Finance"]
    assert trace["legs"][0]["trace"]["metrics"]["manual_handoffs_before"] == 3
    assert trace["legs"][0]["trace"]["steps"][0]["reason"] == "Policy section 2 check passed by Gemini"


def test_run_chain_endpoint_needs_a_built_start():
    body = {"workflows": [], "organization": fixture("organization.json"), "start_id": "nope", "request": PURCHASE}
    assert client.post("/api/run_chain", json=body).status_code == 422


def test_run_endpoint_runs_one_department(monkeypatch):
    monkeypatch.setattr(request_reviewer, "make_reviewer", lambda check, fields: (
        lambda f: AIReviewResponse(decision="PASS", reasons=[])))
    body = {"workflow": fixture(f"workflows/{OPERATIONS}.json"), "organization": fixture("organization.json"),
            "request": {**PURCHASE, "estimated_cost": 8000}, "manual_handoffs_before": 4}
    trace = client.post("/api/run", json=body).json()
    assert trace["status"] == "NEEDS_HUMAN_REVIEW"
    assert "not in the org chart" in trace["steps"][-1]["reason"]


def test_reviewer_sees_the_whole_case(monkeypatch):
    seen = {}

    def fake_make_reviewer(check, fields):
        def review(form: RequestForm):
            seen["form"] = form.model_dump()
            return AIReviewResponse(decision="PASS", reasons=[])
        return review

    monkeypatch.setattr(request_reviewer, "make_reviewer", fake_make_reviewer)
    asyncio.run(pipeline.run_request(workflow(DISCOUNT), org(), RequestForm(
        requester="Ken Ito", department="Sales", customer="Acme", product="Headset", list_price=300,
        discount_percentage=15, reason="Annual renewal for a key account.")))
    assert seen["form"]["customer"] == "Acme" and seen["form"]["discount_percentage"] == 15
