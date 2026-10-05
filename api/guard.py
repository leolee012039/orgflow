import os
import json
import re
import logging
from typing import Any, Callable, Optional, Union
from pydantic import ValidationError

from schemas import (
    Organization,
    Opportunities,
    Workflow,
    OriginType,
)

logger = logging.getLogger("orgflow.guard")
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

def load_fixture(fixture_name: str) -> dict:
    path = os.path.join(FIXTURES_DIR, fixture_name)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# -----------------------------------------------------------------------------
# Check 1: Pydantic Schema Parsing
# -----------------------------------------------------------------------------

def check_schema(data: Any, model_class: type) -> tuple[bool, Optional[Any], list[str]]:
    try:
        if isinstance(data, str):
            parsed_data = json.loads(data)
        elif isinstance(data, dict):
            parsed_data = data
        else:
            return False, None, [f"Expected dict or JSON string, got {type(data).__name__}"]
        instance = model_class.model_validate(parsed_data)
        return True, instance, []
    except ValidationError as e:
        errors = [f"Schema error at {err['loc']}: {err['msg']}" for err in e.errors()]
        return False, None, errors
    except Exception as e:
        return False, None, [f"Invalid JSON data: {str(e)}"]

# -----------------------------------------------------------------------------
# Check 2: Step Actors Exist in Organization or unresolved_actors
# -----------------------------------------------------------------------------

SPECIAL_ACTORS = {"requester", "requester.manager", "orgflow_ai"}

def check_step_actors(workflow: Workflow, org: Optional[Organization]) -> list[str]:
    if org is None:
        return []

    valid_role_ids = {r.id.lower() for r in org.roles}
    valid_role_titles = {r.title.lower() for r in org.roles}
    unresolved = {a.lower() for a in workflow.unresolved_actors}

    errors: list[str] = []
    for step in workflow.steps:
        actor_lower = step.actor.lower()
        if (
            actor_lower in SPECIAL_ACTORS
            or actor_lower in valid_role_ids
            or actor_lower in valid_role_titles
            or actor_lower in unresolved
        ):
            continue
        errors.append(
            f"Step '{step.id}' actor '{step.actor}' is not in organization roles and not listed in unresolved_actors"
        )
    return errors

# -----------------------------------------------------------------------------
# Check 4: Rule when.value numbers appear in rule.source
# -----------------------------------------------------------------------------

def check_rule_numbers(workflow: Workflow) -> list[str]:
    errors: list[str] = []
    for rule in workflow.rules:
        # Convert rule value to normalized number string
        val = rule.when.value
        if isinstance(val, (int, float)):
            val_str = str(int(val)) if float(val).is_integer() else str(val)
        else:
            val_str = str(val).strip()

        # Remove commas between digits in source (e.g. 1,000 -> 1000)
        norm_source = re.sub(r"(\d),(\d)", r"\1\2", rule.source)

        # Check if the number appears in the normalized source string
        if val_str not in norm_source:
            errors.append(
                f"Rule '{rule.id}' threshold value {val_str} does not appear in its source quote: '{rule.source}'"
            )
    return errors

# -----------------------------------------------------------------------------
# Validation Wrappers
# -----------------------------------------------------------------------------

def validate_organization_output(data: Any) -> tuple[Optional[Organization], list[str]]:
    valid, org, errors = check_schema(data, Organization)
    if not valid:
        return None, errors
    return org, []

def validate_opportunities_output(data: Any, org: Optional[Organization] = None) -> tuple[Optional[Opportunities], list[str]]:
    valid, opps, errors = check_schema(data, Opportunities)
    if not valid:
        return None, errors
    if len(opps.opportunities) != 3:
        errors.append(f"Expected exactly 3 opportunities, got {len(opps.opportunities)}")
        return None, errors
    return opps, []

def validate_workflow_output(data: Any, org: Optional[Organization] = None) -> tuple[Optional[Workflow], list[str]]:
    valid, wf, errors = check_schema(data, Workflow)
    if not valid:
        return None, errors

    # Check 2: actors
    actor_errors = check_step_actors(wf, org)
    errors.extend(actor_errors)

    # Check 4: rule threshold numbers in source
    rule_errors = check_rule_numbers(wf)
    errors.extend(rule_errors)

    if errors:
        return None, errors
    return wf, []

# -----------------------------------------------------------------------------
# Guard Orchestrators (Schema -> Repair once -> Fixture fallback)
# -----------------------------------------------------------------------------

def guard_organization(
    data: Any,
    repair_func: Optional[Callable[[list[str]], Any]] = None,
) -> tuple[Organization, OriginType]:
    org, errors = validate_organization_output(data)
    if org is not None:
        logger.info("Guard: Organization validated successfully (origin: live)")
        return org, "live"

    logger.warning("Guard: Organization validation failed: %s", errors)
    if repair_func is not None:
        try:
            repaired_data = repair_func(errors)
            repaired_org, r_errors = validate_organization_output(repaired_data)
            if repaired_org is not None:
                logger.info("Guard: Organization repaired successfully (origin: repaired)")
                return repaired_org, "repaired"
            logger.warning("Guard: Organization repair failed: %s", r_errors)
        except Exception as e:
            logger.error("Guard: Repair attempt raised exception: %s", e)

    logger.info("Guard: Falling back to organization_fixture.json (origin: fixture)")
    fixture = load_fixture("organization_fixture.json")
    return Organization.model_validate(fixture), "fixture"

def guard_opportunities(
    data: Any,
    org: Optional[Organization] = None,
    repair_func: Optional[Callable[[list[str]], Any]] = None,
) -> tuple[Opportunities, OriginType]:
    opps, errors = validate_opportunities_output(data, org)
    if opps is not None:
        logger.info("Guard: Opportunities validated successfully (origin: live)")
        return opps, "live"

    logger.warning("Guard: Opportunities validation failed: %s", errors)
    if repair_func is not None:
        try:
            repaired_data = repair_func(errors)
            repaired_opps, r_errors = validate_opportunities_output(repaired_data, org)
            if repaired_opps is not None:
                logger.info("Guard: Opportunities repaired successfully (origin: repaired)")
                return repaired_opps, "repaired"
            logger.warning("Guard: Opportunities repair failed: %s", r_errors)
        except Exception as e:
            logger.error("Guard: Repair attempt raised exception: %s", e)

    logger.info("Guard: Falling back to opportunities_fixture.json (origin: fixture)")
    fixture = load_fixture("opportunities_fixture.json")
    return Opportunities.model_validate(fixture), "fixture"

def guard_workflow(
    data: Any,
    org: Optional[Organization] = None,
    repair_func: Optional[Callable[[list[str]], Any]] = None,
) -> tuple[Workflow, OriginType]:
    wf, errors = validate_workflow_output(data, org)
    if wf is not None:
        logger.info("Guard: Workflow validated successfully (origin: live)")
        return wf, "live"

    logger.warning("Guard: Workflow validation failed: %s", errors)
    if repair_func is not None:
        try:
            repaired_data = repair_func(errors)
            repaired_wf, r_errors = validate_workflow_output(repaired_data, org)
            if repaired_wf is not None:
                logger.info("Guard: Workflow repaired successfully (origin: repaired)")
                return repaired_wf, "repaired"
            logger.warning("Guard: Workflow repair failed: %s", r_errors)
        except Exception as e:
            logger.error("Guard: Repair attempt raised exception: %s", e)

    logger.info("Guard: Falling back to workflow_fixture.json (origin: fixture)")
    fixture = load_fixture("workflow_fixture.json")
    return Workflow.model_validate(fixture), "fixture"
