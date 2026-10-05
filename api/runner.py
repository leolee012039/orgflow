import logging
from typing import Any, Callable, Optional, Union
from schemas import (
    Workflow,
    Organization,
    PurchaseRequestForm,
    ExecutionTrace,
    StepTrace,
    TraceMetrics,
    AIReviewResponse,
)

logger = logging.getLogger("orgflow.runner")

PLACEHOLDER_JUSTIFICATIONS = {"n/a", "na", "tbd", "-", "none", "null", "test", "nil"}

def evaluate_condition(field_val: Any, op: str, target_val: Any) -> bool:
    try:
        if isinstance(target_val, (int, float)) and isinstance(field_val, (int, float, str)):
            field_val = float(field_val)
            target_val = float(target_val)
        if op == "<":
            return field_val < target_val
        elif op == "<=":
            return field_val <= target_val
        elif op == ">":
            return field_val > target_val
        elif op == ">=":
            return field_val >= target_val
        elif op == "==":
            return field_val == target_val
    except Exception as e:
        logger.warning("Error evaluating condition %s %s %s: %s", field_val, op, target_val, e)
        return False
    return False

def resolve_actor(actor_name: str, form: PurchaseRequestForm, org: Organization, workflow: Workflow) -> tuple[bool, Optional[str], Optional[str]]:
    """
    Resolves an actor against the organization.
    Returns: (is_resolved, display_title, error_reason)
    """
    # 1. Unresolved actors explicitly declared in workflow
    for u in workflow.unresolved_actors:
        if u.lower() == actor_name.lower():
            return False, None, f"Role '{actor_name}' is not in the org chart → human review"

    # 2. Special actor: requester
    if actor_name.lower() == "requester":
        return True, f"Requester ({form.requester})", None

    # 3. Special actor: requester.manager
    if actor_name.lower() == "requester.manager":
        # Find department head
        dept_match = None
        for dept in org.departments:
            if dept.name.lower() == form.department.lower():
                dept_match = dept
                break
        if not dept_match:
            return False, None, f"Requester department '{form.department}' not found in organization"
        
        if not dept_match.head_role_id:
            return False, None, f"The org chart names no head for '{dept_match.name}' → human review"

        # Find head role
        head_role = None
        for role in org.roles:
            if role.id.lower() == dept_match.head_role_id.lower():
                head_role = role
                break
        if not head_role:
            return False, None, f"Department head role '{dept_match.head_role_id}' not found in organization"
        return True, head_role.title, None

    # 4. Special actor: orgflow_ai
    if actor_name.lower() == "orgflow_ai":
        return True, "OrgFlow AI", None

    # 5. Organization role lookup by id or title
    for role in org.roles:
        if role.id.lower() == actor_name.lower() or role.title.lower() == actor_name.lower():
            return True, role.title, None

    # 6. A department acting as a unit, e.g. "the accounting office reviews"
    for dept in org.departments:
        if dept.name.lower() == actor_name.lower():
            return True, dept.name, None

    # Not found in organization
    return False, None, f"Role '{actor_name}' is missing from the org chart → human review"

def plain_code_ai_review(form: PurchaseRequestForm) -> tuple[bool, str]:
    """
    Fallback plain-code completeness review.
    Checks required information is present, not a placeholder, and at least 3 words.
    """
    justification = form.business_justification
    if not justification or not justification.strip():
        return False, "fallback check: business justification is missing"

    stripped = justification.strip()
    if stripped.lower() in PLACEHOLDER_JUSTIFICATIONS:
        return False, f"fallback check: business justification is a placeholder ('{stripped}')"

    words = stripped.split()
    if len(words) < 3:
        return False, f"fallback check: business justification too short ({len(words)} words, minimum 3 required)"

    return True, "Completeness verified by fallback check: required information is present and meaningful"

def run_workflow(
    workflow: Workflow,
    org: Organization,
    form_data: Union[dict, PurchaseRequestForm],
    ai_reviewer: Optional[Callable[[PurchaseRequestForm], AIReviewResponse]] = None,
    manual_handoffs_before: int = 4,
) -> ExecutionTrace:
    """
    Deterministic Workflow Runner.
    Never hardcodes 1,000 or 5,000; all thresholds come from workflow.rules.
    """
    if isinstance(form_data, dict):
        form = PurchaseRequestForm.model_validate(form_data)
        form_dict = form_data
    else:
        form = form_data
        form_dict = form.model_dump()

    trace_steps: list[StepTrace] = []
    rules_by_id = {r.id: r for r in workflow.rules}
    human_approvals = 0
    ai_checks = 0

    # -------------------------------------------------------------------------
    # 1. Required fields check
    # -------------------------------------------------------------------------
    missing_fields = []
    for field in workflow.required_fields:
        val = form_dict.get(field)
        if val is None:
            missing_fields.append(field)
        elif isinstance(val, str) and not val.strip():
            missing_fields.append(field)

    if missing_fields:
        logger.info("Runner: Missing required fields %s -> RETURNED", missing_fields)
        return ExecutionTrace(
            request_id=form.request_id,
            status="RETURNED",
            steps=[
                StepTrace(
                    step_id="submission_check",
                    type="task",
                    actor="system",
                    result="RETURNED",
                    reason=f"Missing required field(s): {', '.join(missing_fields)}",
                )
            ],
            metrics=TraceMetrics(manual_handoffs_before=manual_handoffs_before, human_approvals=0, ai_checks=0),
        )

    # -------------------------------------------------------------------------
    # 2. Walk the steps in order
    # -------------------------------------------------------------------------
    for step in workflow.steps:
        # Check 'only_if' condition
        if step.only_if:
            rule = rules_by_id.get(step.only_if)
            if rule:
                field_val = form_dict.get(rule.when.field)
                cond_met = evaluate_condition(field_val, rule.when.op, rule.when.value)
                if not cond_met:
                    val_display = int(field_val) if isinstance(field_val, (int, float)) and float(field_val).is_integer() else field_val
                    thresh_display = int(rule.when.value) if isinstance(rule.when.value, (int, float)) and float(rule.when.value).is_integer() else rule.when.value
                    trace_steps.append(
                        StepTrace(
                            step_id=step.id,
                            type=step.type,
                            actor=step.actor,
                            result="SKIPPED",
                            reason=f"{rule.id} not met: {val_display} {rule.when.op} {thresh_display} is false",
                            rule_id=rule.id,
                            source=rule.source,
                        )
                    )
                    continue

        # Resolve actor against organization
        resolved, role_title, actor_error = resolve_actor(step.actor, form, org, workflow)
        if not resolved:
            trace_steps.append(
                StepTrace(
                    step_id=step.id,
                    type=step.type,
                    actor=step.actor,
                    result="HUMAN_REVIEW",
                    reason=actor_error or f"Actor '{step.actor}' unresolved",
                )
            )
            return ExecutionTrace(
                request_id=form.request_id,
                status="NEEDS_HUMAN_REVIEW",
                steps=trace_steps,
                metrics=TraceMetrics(
                    manual_handoffs_before=manual_handoffs_before,
                    human_approvals=human_approvals,
                    ai_checks=ai_checks,
                ),
            )

        # Execute step according to type
        if step.type == "approval":
            human_approvals += 1
            trace_steps.append(
                StepTrace(
                    step_id=step.id,
                    type="approval",
                    actor=step.actor,
                    result="PASSED",
                    reason=f"Approved by simulated {role_title}",
                )
            )

        elif step.type == "ai_review":
            ai_checks += 1
            decision_pass = False
            review_reason = ""

            # Try AI reviewer if provided
            if ai_reviewer is not None:
                try:
                    res = ai_reviewer(form)
                    if res.decision == "PASS":
                        decision_pass = True
                        review_reason = "Policy section 2 check passed by Gemini"
                    else:
                        decision_pass = False
                        review_reason = f"Gemini review requested human review: {', '.join(res.reasons)}"
                except Exception as e:
                    logger.warning("AI Reviewer failed (%s); using fallback check", e)
                    decision_pass, review_reason = plain_code_ai_review(form)
            else:
                # Use pure code fallback
                decision_pass, review_reason = plain_code_ai_review(form)

            if decision_pass:
                trace_steps.append(
                    StepTrace(
                        step_id=step.id,
                        type="ai_review",
                        actor=step.actor,
                        result="PASSED",
                        reason=review_reason,
                    )
                )
            else:
                trace_steps.append(
                    StepTrace(
                        step_id=step.id,
                        type="ai_review",
                        actor=step.actor,
                        result="HUMAN_REVIEW",
                        reason=review_reason,
                    )
                )
                return ExecutionTrace(
                    request_id=form.request_id,
                    status="NEEDS_HUMAN_REVIEW",
                    steps=trace_steps,
                    metrics=TraceMetrics(
                        manual_handoffs_before=manual_handoffs_before,
                        human_approvals=human_approvals,
                        ai_checks=ai_checks,
                    ),
                )

        elif step.type == "task":
            trace_steps.append(
                StepTrace(
                    step_id=step.id,
                    type="task",
                    actor=step.actor,
                    result="DONE",
                    reason=f"Task assigned to {role_title} (simulated)",
                )
            )

        elif step.type == "notification":
            trace_steps.append(
                StepTrace(
                    step_id=step.id,
                    type="notification",
                    actor=step.actor,
                    result="DONE",
                    reason=f"{role_title} notified (simulated)",
                )
            )

    return ExecutionTrace(
        request_id=form.request_id,
        status="COMPLETED",
        steps=trace_steps,
        metrics=TraceMetrics(
            manual_handoffs_before=manual_handoffs_before,
            human_approvals=human_approvals,
            ai_checks=ai_checks,
        ),
    )
