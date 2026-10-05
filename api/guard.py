import os
import io
import json
import re
import logging
from typing import Any, Callable, Optional, Union
from pydantic import ValidationError
from pypdf import PdfReader

from schemas import (
    Organization,
    Opportunities,
    PurchaseRequestForm,
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
# PDF Text Extraction and Quote Verification (Check 3)
# -----------------------------------------------------------------------------

def extract_pdf_text(source: Union[str, bytes, io.BytesIO]) -> str:
    """Extract text server-side from PDF bytes, path, or file stream using pypdf."""
    try:
        if isinstance(source, bytes):
            reader = PdfReader(io.BytesIO(source))
        elif isinstance(source, str):
            reader = PdfReader(source)
        else:
            reader = PdfReader(source)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return text
    except Exception as e:
        logger.error("Failed to extract PDF text: %s", e)
        return ""

CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "壹": 1, "二": 2, "貳": 2, "兩": 2, "两": 2, "三": 3, "參": 3,
             "四": 4, "肆": 4, "五": 5, "伍": 5, "六": 6, "陸": 6, "七": 7, "柒": 7, "八": 8, "捌": 8,
             "九": 9, "玖": 9}
CN_SMALL_UNITS = {"十": 10, "拾": 10, "百": 100, "佰": 100, "千": 1000, "仟": 1000}
CN_BIG_UNITS = {"萬": 10_000, "万": 10_000, "億": 100_000_000, "亿": 100_000_000}
CN_NUMERAL = "".join([*CN_DIGITS, *CN_SMALL_UNITS, *CN_BIG_UNITS])


def chinese_numeral_to_int(text: str) -> int:
    """'五萬' -> 50000, '十五萬' -> 150000, '一百萬' -> 1000000, '五千' -> 5000."""
    total, section, digit = 0, 0, 0
    for ch in text:
        if ch in CN_DIGITS:
            digit = CN_DIGITS[ch]
        elif ch in CN_SMALL_UNITS:
            section += (digit or 1) * CN_SMALL_UNITS[ch]
            digit = 0
        elif ch in CN_BIG_UNITS:
            total = (total + section + digit) * CN_BIG_UNITS[ch]
            section, digit = 0, 0
    return total + section + digit


def _format_amount(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def normalize_amounts(text: str) -> str:
    """Write every amount as plain digits so English and Chinese policies compare the same way.

    '1,000' -> '1000', '30萬' -> '300000', '5 千萬' -> '50000000', '新臺幣五萬元' -> '新臺幣50000元'.
    """
    text = re.sub(r"(?<=\d),(?=\d{3})", "", text)
    multipliers = {"千萬": 10_000_000, "百萬": 1_000_000, "十萬": 100_000, "萬": 10_000, "万": 10_000,
                   "千": 1_000, "億": 100_000_000, "亿": 100_000_000}
    text = re.sub(
        r"(\d+(?:\.\d+)?)\s*(千萬|百萬|十萬|萬|万|千|億|亿)",
        lambda m: _format_amount(float(m.group(1)) * multipliers[m.group(2)]),
        text,
    )
    # Chinese numerals are converted only when they are clearly money, so 「一級主管」 stays as it is.
    return re.sub(
        rf"(?<=[臺台]幣)\s*([{CN_NUMERAL}]+)|([{CN_NUMERAL}]+)(?=\s*元)",
        lambda m: str(chinese_numeral_to_int(m.group(1) or m.group(2))),
        text,
    )


def extract_numbers(text: str) -> list[str]:
    """Every number in the text after normalize_amounts. Works next to Chinese characters,
    where a regex word boundary (\\b) would not fire."""
    normalized = normalize_amounts(text)
    return [_format_amount(float(m)) for m in re.findall(r"(?<![\d.])\d+(?:\.\d+)?(?![\d.])", normalized)]

def extract_tokens(text: str) -> list[str]:
    """
    Extract tokens: English words/numbers, or individual CJK characters.
    Words in English, characters for CJK.
    """
    tokens: list[str] = []
    for match in re.finditer(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]", text):
        token = match.group(0).lower()
        tokens.append(token)
    return tokens

def _compact(text: str) -> str:
    """Lowercase, with whitespace and punctuation removed."""
    return re.sub(r"[\s\W_]+", "", text).lower()


def verify_quote_in_text(quote: str, doc_text: str) -> bool:
    """
    Check 3 semantics:
    1. Every number in the quote appears in doc_text (ignoring thousands separators).
    2. At least 70% of quote's tokens appear within the same 3-line window in doc_text.
    """
    if not quote or not quote.strip():
        return False
    if not doc_text or not doc_text.strip():
        return False
    quote = normalize_amounts(quote)
    doc_text = normalize_amounts(doc_text)

    # 0. Exact match once spacing is ignored. This also covers PDFs whose text comes out
    #    one character per line, such as vertical CJK org charts.
    if _compact(quote) and _compact(quote) in _compact(doc_text):
        return True

    # 1. Number check
    quote_numbers = extract_numbers(quote)
    doc_numbers = set(extract_numbers(doc_text))
    for num in quote_numbers:
        if num not in doc_numbers:
            return False

    # 2. Token overlap in a 3-line sliding window
    quote_tokens = extract_tokens(quote)
    if not quote_tokens:
        return False

    doc_lines = [line.strip() for line in doc_text.splitlines() if line.strip()]
    if not doc_lines:
        return False

    total_quote_tokens = len(quote_tokens)

    # Slide 3-line window
    num_lines = len(doc_lines)
    for i in range(num_lines):
        window_lines = doc_lines[i : min(i + 3, num_lines)]
        window_text = " ".join(window_lines)
        window_tokens = set(extract_tokens(window_text))

        # Check tokens present in this window
        matched_count = sum(1 for tok in quote_tokens if tok in window_tokens)
        ratio = matched_count / total_quote_tokens
        if ratio >= 0.70:
            return True

    return False

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
    department_names = {d.name.lower() for d in org.departments}
    unresolved = {a.lower() for a in workflow.unresolved_actors}

    errors: list[str] = []
    for step in workflow.steps:
        actor_lower = step.actor.lower()
        if (
            actor_lower in SPECIAL_ACTORS
            or actor_lower in valid_role_ids
            or actor_lower in valid_role_titles
            or actor_lower in department_names
            or actor_lower in unresolved
        ):
            continue
        errors.append(
            f"Step '{step.id}' actor '{step.actor}' is not an organization role or department and not listed in unresolved_actors"
        )
    return errors

# -----------------------------------------------------------------------------
# Check 4: Rule when.value numbers appear in rule.source
# -----------------------------------------------------------------------------

def check_rule_numbers(workflow: Workflow) -> list[str]:
    errors: list[str] = []
    for rule in workflow.rules:
        val = rule.when.value
        if isinstance(val, (int, float)):
            if _format_amount(val) not in extract_numbers(rule.source):
                errors.append(
                    f"Rule '{rule.id}' threshold value {_format_amount(val)} does not appear in its source quote: "
                    f"'{rule.source}' (write amounts in full, for example 12萬元 is 120000)"
                )
        elif str(val).strip() not in rule.source:
            errors.append(f"Rule '{rule.id}' value '{val}' does not appear in its source quote: '{rule.source}'")
    return errors


def check_amount_tiers(workflow: Workflow) -> list[str]:
    """Each tier's ends are amounts its own passage states, so the coverage check reads real wording."""
    errors: list[str] = []
    for i, tier in enumerate(workflow.amount_tiers, 1):
        if tier.min is None and tier.max is None:
            errors.append(f"Amount tier {i} has neither min nor max")
        elif tier.min is not None and tier.max is not None and tier.min >= tier.max:
            errors.append(f"Amount tier {i} min {_format_amount(tier.min)} is not below its max {_format_amount(tier.max)}")
        numbers = extract_numbers(tier.source)
        for end, value in (("min", tier.min), ("max", tier.max)):
            if value is not None and _format_amount(value) not in numbers:
                errors.append(
                    f"Amount tier {i} {end} {_format_amount(value)} does not appear in its source: '{tier.source}' "
                    "(use the amount the policy writes at that end, in full, without adding or subtracting 1)"
                )
    if not workflow.amount_tiers and any(
        r.when.field == "estimated_cost" and isinstance(r.when.value, (int, float)) for r in workflow.rules
    ):
        errors.append("The rules depend on estimated_cost, but amount_tiers is empty. "
                      "List each approval tier of the policy in amount_tiers.")
    return errors

# -----------------------------------------------------------------------------
# Validation Wrappers
# -----------------------------------------------------------------------------

def check_org_consistency(org: Organization) -> list[str]:
    """Department heads and reporting lines must point at roles that exist."""
    role_ids = {r.id for r in org.roles}
    errors: list[str] = []
    if not org.departments:
        errors.append("No departments found")
    if not org.roles:
        errors.append("No roles found")
    if len(role_ids) != len(org.roles):
        errors.append("Role ids must be unique")
    for dept in org.departments:
        if dept.head_role_id is not None and dept.head_role_id not in role_ids:
            errors.append(f"Department '{dept.name}' head_role_id '{dept.head_role_id}' is not a role id")
    for role in org.roles:
        if role.reports_to is not None and role.reports_to not in role_ids:
            errors.append(f"Role '{role.id}' reports_to '{role.reports_to}' is not a role id")
    return errors


def check_org_grounding(org: Organization, doc_text: str) -> list[str]:
    """Every department name and role title must appear in the uploaded documents."""
    errors: list[str] = []
    for dept in org.departments:
        if not verify_quote_in_text(dept.name, doc_text):
            errors.append(f"Department '{dept.name}' does not appear in the uploaded documents")
    for role in org.roles:
        if not verify_quote_in_text(role.title, doc_text):
            errors.append(f"Role title '{role.title}' does not appear in the uploaded documents")
    return errors


def validate_organization_output(
    data: Any, doc_text: Optional[str] = None
) -> tuple[Optional[Organization], list[str]]:
    valid, org, errors = check_schema(data, Organization)
    if not valid:
        return None, errors
    assert org is not None

    errors.extend(check_org_consistency(org))
    if doc_text:
        errors.extend(check_org_grounding(org, doc_text))

    # Check 3 on evidence quotes if doc_text is provided
    if doc_text and org is not None:
        for rel in org.relationships:
            if rel.evidence and rel.evidence.quote:
                if not verify_quote_in_text(rel.evidence.quote, doc_text):
                    errors.append(
                        f"Relationship evidence quote does not ground in uploaded documents: '{rel.evidence.quote}'"
                    )

    if errors:
        return None, errors
    return org, []

def validate_opportunities_output(
    data: Any,
    org: Optional[Organization] = None,
    doc_text: Optional[str] = None,
) -> tuple[Optional[Opportunities], list[str]]:
    valid, opps, errors = check_schema(data, Opportunities)
    if not valid:
        return None, errors
    assert opps is not None
    if len(opps.opportunities) != 3:
        errors.append(f"Expected exactly 3 opportunities, got {len(opps.opportunities)}")
        return None, errors

    executable = [o.id for o in opps.opportunities if o.executable]
    if executable != [opps.opportunities[0].id]:
        errors.append(f"Only the top-ranked opportunity must be executable; executable now: {executable}")
    if len({o.id for o in opps.opportunities}) != 3:
        errors.append("Opportunity ids must be unique")
    known_departments = {d.name.lower() for d in org.departments} if org else None
    for opp in opps.opportunities:
        if not opp.evidence:
            errors.append(f"Opportunity '{opp.id}' has no evidence quote")
        if known_departments is not None:
            for dept in opp.departments:
                if dept.lower() not in known_departments:
                    errors.append(f"Opportunity '{opp.id}' names unknown department '{dept}'")

    # Check 3 on opportunity evidence quotes
    if doc_text and opps is not None:
        for opp in opps.opportunities:
            for ev in opp.evidence:
                if not verify_quote_in_text(ev.quote, doc_text):
                    errors.append(
                        f"Opportunity '{opp.id}' evidence quote does not ground in uploaded documents: '{ev.quote}'"
                    )

    if errors:
        return None, errors
    return opps, []

FORM_FIELDS = set(PurchaseRequestForm.model_fields) - {"request_id"}

_CURRENCY_AMOUNT = re.compile(r"(?:USD|US\$|NT\$|NTD|TWD|新[臺台]幣|\$)\s*(\d{3,})|(\d{3,})\s*(?:元|dollars?)", re.I)


def stated_amounts(text: str) -> list[int]:
    """Money amounts of 1,000 or more that the documents state, after normalize_amounts."""
    found = [int(a or b) for a, b in _CURRENCY_AMOUNT.findall(normalize_amounts(text))]
    return [n for n in found if n >= 1000]


def check_workflow_structure(wf: Workflow) -> list[str]:
    """The runner can only execute what it can resolve: known fields, rule ids and unique steps."""
    errors: list[str] = []
    rule_ids = {r.id for r in wf.rules}
    if len(rule_ids) != len(wf.rules):
        errors.append("Rule ids must be unique")
    if len({s.id for s in wf.steps}) != len(wf.steps):
        errors.append("Step ids must be unique")
    if not any(s.type == "approval" for s in wf.steps):
        errors.append("Workflow has no approval step")
    for field in wf.required_fields:
        if field not in FORM_FIELDS:
            errors.append(f"Required field '{field}' is not a request form field ({', '.join(sorted(FORM_FIELDS))})")
    for rule in wf.rules:
        if rule.when.field not in FORM_FIELDS:
            errors.append(f"Rule '{rule.id}' uses '{rule.when.field}', which is not a request form field")
    for step in wf.steps:
        if step.only_if and step.only_if not in rule_ids:
            errors.append(f"Step '{step.id}' only_if '{step.only_if}' is not a rule id")
    return errors


def validate_workflow_output(
    data: Any,
    org: Optional[Organization] = None,
    doc_text: Optional[str] = None,
) -> tuple[Optional[Workflow], list[str]]:
    valid, wf, errors = check_schema(data, Workflow)
    if not valid:
        return None, errors
    assert wf is not None

    # Check 2: actors
    actor_errors = check_step_actors(wf, org)
    errors.extend(actor_errors)

    errors.extend(check_workflow_structure(wf))
    if doc_text and not wf.rules and sum(s.type == "approval" for s in wf.steps) >= 2:
        amounts = stated_amounts(doc_text)
        if amounts:
            errors.append(
                f"The documents state amount limits (for example {amounts[0]:,}) but the workflow has no rules. "
                "Express each amount limit that decides an approval as a rule and use it in only_if."
            )
    if doc_text:
        for name in wf.unresolved_actors:
            if not verify_quote_in_text(name, doc_text):
                errors.append(f"Unresolved actor '{name}' does not appear in the uploaded documents")

    # Check 4: rule threshold numbers in source
    rule_errors = check_rule_numbers(wf)
    errors.extend(rule_errors)
    errors.extend(check_amount_tiers(wf))

    # Check 3: source quotes in doc_text
    if doc_text and wf is not None:
        for rule in wf.rules:
            if not verify_quote_in_text(rule.source, doc_text):
                errors.append(
                    f"Rule '{rule.id}' source does not ground in uploaded documents: '{rule.source}'"
                )
        for i, tier in enumerate(wf.amount_tiers, 1):
            if not verify_quote_in_text(tier.source, doc_text):
                errors.append(f"Amount tier {i} source does not ground in uploaded documents: '{tier.source}'")

    if errors:
        return None, errors
    return wf, []

# -----------------------------------------------------------------------------
# Guard Orchestrators (Schema -> Repair once -> Fixture fallback)
# -----------------------------------------------------------------------------

def guard_organization(
    data: Any,
    doc_text: Optional[str] = None,
    repair_func: Optional[Callable[[list[str]], Any]] = None,
) -> tuple[Organization, OriginType]:
    org, errors = validate_organization_output(data, doc_text)
    if org is not None:
        logger.info("Guard: Organization validated successfully (origin: live)")
        return org, "live"

    logger.warning("Guard: Organization validation failed: %s", errors)
    if repair_func is not None:
        try:
            repaired_data = repair_func(errors)
            repaired_org, r_errors = validate_organization_output(repaired_data, doc_text)
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
    doc_text: Optional[str] = None,
    repair_func: Optional[Callable[[list[str]], Any]] = None,
) -> tuple[Opportunities, OriginType]:
    opps, errors = validate_opportunities_output(data, org, doc_text)
    if opps is not None:
        logger.info("Guard: Opportunities validated successfully (origin: live)")
        return opps, "live"

    logger.warning("Guard: Opportunities validation failed: %s", errors)
    if repair_func is not None:
        try:
            repaired_data = repair_func(errors)
            repaired_opps, r_errors = validate_opportunities_output(repaired_data, org, doc_text)
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
    doc_text: Optional[str] = None,
    repair_func: Optional[Callable[[list[str]], Any]] = None,
) -> tuple[Workflow, OriginType]:
    wf, errors = validate_workflow_output(data, org, doc_text)
    if wf is not None:
        logger.info("Guard: Workflow validated successfully (origin: live)")
        return wf, "live"

    logger.warning("Guard: Workflow validation failed: %s", errors)
    if repair_func is not None:
        try:
            repaired_data = repair_func(errors)
            repaired_wf, r_errors = validate_workflow_output(repaired_data, org, doc_text)
            if repaired_wf is not None:
                logger.info("Guard: Workflow repaired successfully (origin: repaired)")
                return repaired_wf, "repaired"
            logger.warning("Guard: Workflow repair failed: %s", r_errors)
        except Exception as e:
            logger.error("Guard: Repair attempt raised exception: %s", e)

    logger.info("Guard: Falling back to workflow_fixture.json (origin: fixture)")
    fixture = load_fixture("workflow_fixture.json")
    return Workflow.model_validate(fixture), "fixture"
