import logging
from typing import Any, Callable, Optional, Sequence, Union
from amount_coverage import amount_findings, find_amount_gaps
from guard import _compact, extract_tokens, normalize_amounts
from schemas import (
    AIReviewResponse,
    AmountDecision,
    ApproverDecision,
    Decision,
    ChainLeg,
    ChainTrace,
    ExecutionTrace,
    Organization,
    RequestForm,
    StepTrace,
    TraceMetrics,
    Workflow,
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

def resolve_actor(actor_name: str, form: RequestForm, org: Organization, workflow: Workflow) -> tuple[bool, Optional[str], Optional[str]]:
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

def plain_code_ai_review(form: RequestForm, required_fields: Optional[list[str]] = None) -> tuple[bool, str]:
    """
    Fallback plain-code completeness review.
    Required text is not a placeholder, and a business justification has at least 3 words.
    """
    values = form.model_dump()
    for field in required_fields or []:
        value = values.get(field)
        if isinstance(value, str) and value.strip().lower() in PLACEHOLDER_JUSTIFICATIONS:
            return False, f"fallback check: {field.replace('_', ' ')} is a placeholder ('{value.strip()}')"

    if "business_justification" in values:
        justification = values["business_justification"]
        if not justification or not str(justification).strip():
            return False, "fallback check: business justification is missing"
        stripped = str(justification).strip()
        if stripped.lower() in PLACEHOLDER_JUSTIFICATIONS:
            return False, f"fallback check: business justification is a placeholder ('{stripped}')"
        words = stripped.split()
        if len(words) < 3:
            return False, f"fallback check: business justification too short ({len(words)} words, minimum 3 required)"

    return True, "Completeness verified by fallback check: required information is present and meaningful"

REQUESTER_MANAGER = "requester.manager"


def _from_level(rule_source: str, level_source: str) -> bool:
    """Whether Gemini wrote this rule from this level's passage: one contains the other,
    or most of the rule's words are the level's."""
    rule_text, level_text = _compact(normalize_amounts(rule_source)), _compact(normalize_amounts(level_source))
    if rule_text and level_text and (rule_text in level_text or level_text in rule_text):
        return True
    rule_tokens, level_tokens = set(extract_tokens(rule_source)), set(extract_tokens(level_source))
    return bool(rule_tokens) and len(rule_tokens & level_tokens) / len(rule_tokens) >= 0.7


def _settle_amount(rules: list, finding: dict, level: str) -> bool:
    """Give the exact amount to one of the two levels by changing their rules' comparisons.
    Returns whether the chosen level now owns the amount.

    Only rules written from the two levels' passages lose the amount: a rule from
    another table at the same number ("$5,000 or more needs three quotes") stays as it
    is. When no rule of the chosen level can be matched to its passage, the rules that
    end the gap on that side gain the amount, which can add an approval but never skip
    one. When neither works (a rule written for 5,001), the decision doesn't take effect
    and the case still stops for a person.
    """
    amount = float(finding["amount"])
    at_amount = [r for r in rules if r.when.field == finding["field"]
                 and isinstance(r.when.value, (int, float)) and not isinstance(r.when.value, bool)
                 and float(r.when.value) == amount]
    lower = [r for r in at_amount if r.when.op in ("<", "<=") and _from_level(r.source, finding["below"])]
    upper = [r for r in at_amount if r.when.op in (">", ">=") and _from_level(r.source, finding["above"])]
    if level == "above":
        chosen, other, exclusive, inclusive, other_inclusive, other_exclusive = upper, lower, ">", ">=", "<=", "<"
    else:
        chosen, other, exclusive, inclusive, other_inclusive, other_exclusive = lower, upper, "<", "<=", ">=", ">"
    for rule in other:
        if rule.when.op == other_inclusive:
            rule.when.op = other_exclusive
    if not chosen:
        gain = [r for r in at_amount if r.when.op == exclusive]
        for rule in gain:
            rule.when.op = inclusive
        return bool(gain)
    for rule in chosen:
        if rule.when.op == exclusive:
            rule.when.op = inclusive
    return True


def with_decisions(
    workflow: Workflow, org: Organization, decisions: Sequence[Decision]
) -> tuple[Workflow, dict[str, str], list[AmountDecision]]:
    """The workflow as a person settled it.

    An approver the org chart doesn't have is replaced by the role the person named, in
    every step. An exact amount the policy leaves in no level (or in both, or can't say)
    goes to the level the person chose: its rules include the amount, the other level's
    exclude it. A decision changes nothing when it no longer fits: another workflow, a
    role that doesn't exist, an approver that isn't missing, an amount the policy no
    longer leaves open, or rules that don't stop at that amount.

    Returns the settled workflow, the original approver by step id, and the amount
    decisions that took effect.
    """
    mine = [d for d in decisions if d.workflow_id == workflow.opportunity_id]
    if not mine:
        return workflow, {}, []
    wf = workflow.model_copy(deep=True)
    stand_ins: dict[str, str] = {}
    amounts: list[AmountDecision] = []
    open_amounts = {(f["field"], float(f["amount"])): f for f in find_amount_gaps(wf.amount_tiers)}
    for d in mine:
        if isinstance(d, ApproverDecision):
            missing = {u.lower() for u in wf.unresolved_actors}
            # A role in the organization, or the head of the requester's own department
            known = d.role_id == REQUESTER_MANAGER or any(r.id == d.role_id for r in org.roles)
            if d.actor.lower() not in missing or not known:
                continue
            for step in wf.steps:
                if step.actor.lower() == d.actor.lower():
                    stand_ins[step.id] = step.actor
                    step.actor = d.role_id
            wf.unresolved_actors = [u for u in wf.unresolved_actors if u.lower() != d.actor.lower()]
        else:
            finding = open_amounts.pop((d.field, d.amount), None)  # the first decision for an amount wins
            if finding is not None and _settle_amount(wf.rules, finding, d.level):
                amounts.append(d)
    return wf, stand_ins, amounts


def run_workflow(
    workflow: Workflow,
    org: Organization,
    form_data: Union[dict, RequestForm],
    ai_reviewer: Optional[Callable[[RequestForm], AIReviewResponse]] = None,
    manual_handoffs_before: int = 4,
    decisions: Sequence[Decision] = (),
) -> ExecutionTrace:
    """
    Deterministic Workflow Runner.
    Never hardcodes 1,000 or 5,000; all thresholds come from workflow.rules.
    A person's decisions settle approvers and exact amounts the documents leave open.
    """
    form = RequestForm.model_validate(form_data) if isinstance(form_data, dict) else form_data
    form_dict = form.model_dump()
    workflow, stand_ins, amount_decisions = with_decisions(workflow, org, decisions)

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
    # 2. An amount the policy's tiers leave uncovered, or cover twice, has no
    #    defined approvals, so a person decides before anything runs
    # -------------------------------------------------------------------------
    for finding in amount_findings(workflow.amount_tiers, form_dict):
        amount = f"{finding['amount']:,.0f}" if float(finding["amount"]).is_integer() else f"{finding['amount']:,}"
        decided = next((d for d in amount_decisions
                        if d.field == finding["field"] and d.amount == float(finding["amount"])), None)
        if decided:
            trace_steps.append(
                StepTrace(
                    step_id=f"amount_decision_{finding['field']}",
                    type="task",
                    actor="system",
                    result="DONE",
                    reason=f"A person decided exactly {amount} goes to the level {decided.level} it",
                    source=finding["below"] if decided.level == "below" else finding["above"],
                )
            )
            continue
        reason = {
            "gap": f"No approval level in the policy covers exactly {amount} → human review",
            "overlap": f"Two approval levels in the policy both cover exactly {amount} → human review",
            "unclear": f"The policy's wording doesn't say which approval level covers exactly {amount} → human review",
        }[finding["kind"]]
        logger.info("Runner: amount %s is a policy %s -> NEEDS_HUMAN_REVIEW", amount, finding["kind"])
        return ExecutionTrace(
            request_id=form.request_id,
            status="NEEDS_HUMAN_REVIEW",
            steps=[
                *trace_steps,
                StepTrace(
                    step_id="amount_check",
                    type="task",
                    actor="system",
                    result="HUMAN_REVIEW",
                    reason=reason,
                    source=f"{finding['below']} / {finding['above']}",
                ),
            ],
            metrics=TraceMetrics(manual_handoffs_before=manual_handoffs_before, human_approvals=0, ai_checks=0),
        )

    # -------------------------------------------------------------------------
    # 3. Walk the steps in order
    # -------------------------------------------------------------------------
    for step in workflow.steps:
        # Check 'only_if' and 'also_if': a step for a range of amounts needs both
        unmet = None
        for rule_id in (step.only_if, step.also_if):
            rule = rules_by_id.get(rule_id) if rule_id else None
            if rule and not evaluate_condition(form_dict.get(rule.when.field), rule.when.op, rule.when.value):
                unmet = rule
                break
        if unmet is not None:
            rule = unmet
            field_val = form_dict.get(rule.when.field)
            val_display = int(field_val) if isinstance(field_val, (int, float)) and float(field_val).is_integer() else field_val
            thresh_display = int(rule.when.value) if isinstance(rule.when.value, (int, float)) and float(rule.when.value).is_integer() else rule.when.value
            trace_steps.append(
                StepTrace(
                    step_id=step.id,
                    type=step.type,
                    actor=step.actor,
                    stands_in_for=stand_ins.get(step.id),
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
                    stands_in_for=stand_ins.get(step.id),
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
                    stands_in_for=stand_ins.get(step.id),
                    result="PASSED",
                    reason=f"Approved by simulated {role_title}"
                    + (f", in place of {stand_ins[step.id]}" if step.id in stand_ins else ""),
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
                    decision_pass, review_reason = plain_code_ai_review(form, workflow.required_fields)
            else:
                # Use pure code fallback
                decision_pass, review_reason = plain_code_ai_review(form, workflow.required_fields)

            if decision_pass:
                trace_steps.append(
                    StepTrace(
                        step_id=step.id,
                        type="ai_review",
                        actor=step.actor,
                        stands_in_for=stand_ins.get(step.id),
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
                        stands_in_for=stand_ins.get(step.id),
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
                    stands_in_for=stand_ins.get(step.id),
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
                    stands_in_for=stand_ins.get(step.id),
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


def next_workflow(current: Workflow, workflows: list[Workflow]) -> Optional[Workflow]:
    """The workflow built to pick up this one's result: the first, in the given order, whose
    upstream_id is this workflow. Only that one was built against this workflow's fields."""
    if not current.hands_to:
        return None
    return next((w for w in workflows if w.upstream_id == current.opportunity_id), None)


def run_chain(
    workflows: list[Workflow],
    org: Organization,
    start_id: str,
    form_data: Union[dict, RequestForm],
    reviewer_for: Optional[Callable[[Workflow], Optional[Callable[[RequestForm], AIReviewResponse]]]] = None,
    handoffs_before: Optional[dict[str, int]] = None,
    decisions: Sequence[Decision] = (),
) -> ChainTrace:
    """Run a case through one department's workflow, then each workflow it hands to.

    The case keeps its data as it moves on, so the next department's form is already
    filled in. The chain stops at the first workflow that doesn't complete, and never
    visits a workflow twice.
    """
    by_id = {w.opportunity_id: w for w in workflows}
    if start_id not in by_id:
        raise KeyError(f"No built workflow '{start_id}'")
    form = RequestForm.model_validate(form_data) if isinstance(form_data, dict) else form_data
    data = form.model_dump()
    legs: list[ChainLeg] = []
    current: Optional[Workflow] = by_id[start_id]
    seen: set[str] = set()
    while current is not None and current.opportunity_id not in seen:
        seen.add(current.opportunity_id)
        reviewer = reviewer_for(current) if reviewer_for else None
        trace = run_workflow(current, org, data, reviewer, (handoffs_before or {}).get(current.opportunity_id, 0),
                             decisions)
        legs.append(ChainLeg(workflow_id=current.opportunity_id, workflow_name=current.workflow_name,
                             department=current.department, trace=trace))
        if trace.status != "COMPLETED":
            return ChainTrace(request_id=form.request_id, status=trace.status, legs=legs)
        following = next_workflow(current, workflows)
        if following is None:
            return ChainTrace(request_id=form.request_id, status="COMPLETED", legs=legs,
                              waiting_for=current.hands_to or None)
        current = following
    return ChainTrace(request_id=form.request_id, status="COMPLETED", legs=legs)
