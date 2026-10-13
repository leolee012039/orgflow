import os
import io
import json
import re
import logging
import unicodedata
from typing import Any, Optional, Union
from pydantic import ValidationError
from pypdf import PdfReader

from schemas import (
    STANDARD_FIELDS,
    AmountTier,
    DepartmentMap,
    FormField,
    Organization,
    PurchaseRequestForm,
    Workflow,
    WorkflowCandidate,
    WorkflowPlan,
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

# List markers such as ① and ⒈ would become digits under NFKC and run into the amount after them
_LIST_MARKERS = re.compile("[\u2460-\u24ff\u2776-\u2793\u3251-\u325f\u32b1-\u32bf]")


def normalize_text(text: str) -> str:
    """One spelling for characters that look the same: CJK compatibility ideographs (行 stored
    as U+F914), full-width digits and brackets. List markers become spaces first."""
    return unicodedata.normalize("NFKC", _LIST_MARKERS.sub(" ", text))


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
        # Some PDFs store look-alike code points (CJK compatibility ideographs, full-width digits):
        # 行 stored as U+F914 never matches the 行 Gemini writes until both are normalized
        return normalize_text(text)
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
    Indian amounts too: '5,00,000' -> '500000', '2 lakh' -> '200000', '1 crore' -> '10000000'.
    Look-alike characters are normalized first: '５０萬' is '50萬'.
    """
    text = normalize_text(text)
    # Indian grouping: twos after the first three, as in 5,00,000 and 1,25,50,000
    text = re.sub(r"(?<![\d,])\d{1,2}(?:,\d{2})+,\d{3}(?![\d,])", lambda m: m.group().replace(",", ""), text)
    text = re.sub(r"(?<=\d),(?=\d{3})", "", text)
    text = re.sub(
        r"(\d+(?:\.\d+)?)\s*(lakhs?|lacs?|crores?)\b",
        lambda m: _format_amount(round(float(m.group(1)) * (10_000_000 if m.group(2).lower().startswith("c") else 100_000))),
        text,
        flags=re.I,
    )
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
    # (?!\d|\.\d) lets a full stop end the number: "Above USD 5,000." states 5000
    return [_format_amount(float(m)) for m in re.findall(r"(?<![\d.])\d+(?:\.\d+)?(?!\d|\.\d)", normalized)]

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


def amount_tier_problems(tiers: list[AmountTier], doc_text: Optional[str] = None,
                         fields: Optional[set[str]] = None) -> list[str]:
    """Each tier's ends must be amounts its own passage states, and the passage must be in the documents."""
    errors: list[str] = []
    for i, tier in enumerate(tiers, 1):
        if fields is not None and tier.field not in fields:
            errors.append(f"Amount tier {i} applies to '{tier.field}', which is not a form field")
        if tier.min is None and tier.max is None:
            errors.append(f"Amount tier {i} has neither min nor max")
        elif tier.min is not None and tier.max is not None and tier.min >= tier.max:
            errors.append(f"Amount tier {i} min {_format_amount(tier.min)} is not below its max {_format_amount(tier.max)}")
        numbers = extract_numbers(tier.source)
        for end, value in (("min", tier.min), ("max", tier.max)):
            if value is not None and _format_amount(value) not in numbers:
                errors.append(f"Amount tier {i} {end} {_format_amount(value)} does not appear in its source: '{tier.source}'")
        if doc_text and not verify_quote_in_text(tier.source, doc_text):
            errors.append(f"Amount tier {i} source does not ground in uploaded documents: '{tier.source}'")
    return errors


def verified_amount_tiers(tiers: list[AmountTier], doc_text: Optional[str] = None,
                          fields: Optional[set[str]] = None) -> tuple[list[AmountTier], list[str]]:
    """All tiers, or none if any fails a check.

    The tiers only feed the coverage check, so a bad tier never fails the workflow. It
    drops them all instead of one: a missing tier could pair two others that don't meet.
    """
    problems = amount_tier_problems(tiers, doc_text, fields)
    return ([], problems) if problems else (tiers, [])

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

def _department_names(org: Optional[Organization]) -> Optional[dict[str, str]]:
    """Lower-cased name -> name as written, for matching department names."""
    return {d.name.lower(): d.name for d in org.departments} if org else None


def _check_quote(label: str, quote: str, doc_text: Optional[str]) -> list[str]:
    if doc_text and not verify_quote_in_text(quote, doc_text):
        return [f"{label} quote does not ground in uploaded documents: '{quote}'"]
    return []


def validate_department_map(
    data: Any,
    org: Optional[Organization] = None,
    doc_text: Optional[str] = None,
    max_departments: int = 10,
) -> tuple[Optional[DepartmentMap], list[str]]:
    """Every profile is a real department with quoted work; every handoff joins two real departments."""
    valid, dmap, errors = check_schema(data, DepartmentMap)
    if not valid:
        return None, errors
    assert dmap is not None
    known = _department_names(org)
    if not dmap.departments:
        errors.append("No department profiles")
    if len(dmap.departments) > max_departments:
        errors.append(f"At most {max_departments} department profiles, got {len(dmap.departments)}")
    names = [p.name.lower() for p in dmap.departments]
    if len(set(names)) != len(names):
        errors.append("Each department may have only one profile")
    for profile in dmap.departments:
        if known is not None and profile.name.lower() not in known:
            errors.append(f"Profile '{profile.name}' is not a department in the organization JSON")
        if not profile.work:
            errors.append(f"Profile '{profile.name}' lists no work; leave out departments the documents give no work to")
        for item in profile.work:
            errors.extend(_check_quote(f"Work '{item.task}' of '{profile.name}'", item.evidence.quote, doc_text))
    profiled = {p.name.lower() for p in dmap.departments}
    for h in dmap.handoffs:
        label = f"Handoff '{h.from_dept}' -> '{h.to}'"
        for end in (h.from_dept, h.to):
            if known is not None and end.lower() not in known:
                errors.append(f"{label} names '{end}', which is not a department in the organization JSON")
            elif end.lower() not in profiled:
                # No workflow could ever be planned there, so cases would wait for it forever
                errors.append(f"{label} names '{end}', which has no profile; profile it or leave the handoff out")
        if h.from_dept.lower() == h.to.lower():
            errors.append(f"{label} starts and ends in the same department")
        errors.extend(_check_quote(label, h.evidence.quote, doc_text))
    if errors:
        return None, errors
    # One spelling per department from here on: the organization's
    if known is not None:
        for profile in dmap.departments:
            profile.name = known[profile.name.lower()]
        for h in dmap.handoffs:
            h.from_dept, h.to = known[h.from_dept.lower()], known[h.to.lower()]
    return dmap, []


def _workflow_loop(plan: WorkflowPlan) -> Optional[list[str]]:
    """Workflow ids that hand cases round in a circle, if any: such a case would never finish."""
    def follows(w: WorkflowCandidate) -> list[WorkflowCandidate]:
        return [d for d in plan.workflows
                if w.hands_to and d.department == w.hands_to and d.starts_from == w.department]

    def walk(w: WorkflowCandidate, path: list[str]) -> Optional[list[str]]:
        if w.id in path:
            return path[path.index(w.id):] + [w.id]
        for d in follows(w):
            loop = walk(d, path + [w.id])
            if loop:
                return loop
        return None

    for w in plan.workflows:
        loop = walk(w, [])
        if loop:
            return loop
    return None


def validate_workflow_plan(
    data: Any,
    dmap: DepartmentMap,
    doc_text: Optional[str] = None,
    max_per_department: int = 3,
) -> tuple[Optional[WorkflowPlan], list[str]]:
    """Each mapped department gets 1-3 workflows, linked only along handoffs on the map."""
    valid, plan, errors = check_schema(data, WorkflowPlan)
    if not valid:
        return None, errors
    assert plan is not None
    mapped = {p.name.lower(): p.name for p in dmap.departments}
    handoffs = {(h.from_dept.lower(), h.to.lower()) for h in dmap.handoffs}
    ids = [w.id for w in plan.workflows]
    if len(set(ids)) != len(ids):
        errors.append("Workflow ids must be unique")
    for dept_key, dept in mapped.items():
        count = sum(w.department.lower() == dept_key for w in plan.workflows)
        if count == 0:
            errors.append(f"Department '{dept}' has no planned workflow")
        elif count > max_per_department:
            errors.append(f"Department '{dept}' has {count} planned workflows; plan at most {max_per_department}")
    for w in plan.workflows:
        own = w.department.lower()
        if own not in mapped:
            errors.append(f"Workflow '{w.id}' belongs to '{w.department}', which is not in the department map")
        if w.starts_from and (w.starts_from.lower(), own) not in handoffs:
            errors.append(f"Workflow '{w.id}' starts from '{w.starts_from}', but the map has no handoff "
                          f"'{w.starts_from}' -> '{w.department}'")
        if w.hands_to and (own, w.hands_to.lower()) not in handoffs:
            errors.append(f"Workflow '{w.id}' hands to '{w.hands_to}', but the map has no handoff "
                          f"'{w.department}' -> '{w.hands_to}'")
        if w.manual_handoffs < 0:
            errors.append(f"Workflow '{w.id}' has a negative manual_handoffs")
        if not w.evidence:
            errors.append(f"Workflow '{w.id}' has no evidence quote")
        if w.basis == "policy" and not any(ev.doc.startswith("policy") for ev in w.evidence):
            errors.append(f"Workflow '{w.id}' is based on a policy but quotes no policy document; "
                          "quote the policy passage or set basis to org_chart")
        for ev in w.evidence:
            errors.extend(_check_quote(f"Workflow '{w.id}' evidence", ev.quote, doc_text))
        if not re.fullmatch(r"[a-z0-9_]+", w.id):
            errors.append(f"Workflow id '{w.id}' must be snake_case (a-z, 0-9, _)")
    if errors:
        return None, errors
    # One spelling per department, the map's, so the web app can compare names exactly
    for w in plan.workflows:
        w.department = mapped[w.department.lower()]
        w.starts_from = mapped.get(w.starts_from.lower(), w.starts_from) if w.starts_from else None
        w.hands_to = mapped.get(w.hands_to.lower(), w.hands_to) if w.hands_to else None
    loop = _workflow_loop(plan)
    if loop:
        return None, [f"Workflows {' -> '.join(loop)} hand cases round in a loop, so a case would never finish; "
                      "break the loop by removing one starts_from or hands_to"]
    return plan, []


# The original NovaGear purchase request form, for workflows built without their own fields
LEGACY_FORM_FIELDS = set(PurchaseRequestForm.model_fields) - {"request_id"}

_CURRENCY_AMOUNT = re.compile(r"(?:USD|US\$|NT\$|NTD|TWD|新[臺台]幣|\$)\s*(\d{3,})|(\d{3,})\s*(?:元|dollars?)", re.I)
_FIELD_NAME = re.compile(r"[a-z][a-z0-9_]*")


def form_fields(wf: Workflow) -> set[str]:
    """The fields a request for this workflow carries."""
    return {f.name for f in wf.fields} | STANDARD_FIELDS if wf.fields else set(LEGACY_FORM_FIELDS)


def stated_amounts(text: str) -> list[int]:
    """Money amounts of 1,000 or more that the documents state, after normalize_amounts."""
    found = [int(a or b) for a, b in _CURRENCY_AMOUNT.findall(normalize_amounts(text))]
    return [n for n in found if n >= 1000]


def check_workflow_structure(wf: Workflow) -> list[str]:
    """The runner can only execute what it can resolve: known fields, rule ids and unique steps."""
    errors: list[str] = []
    fields = form_fields(wf)
    rule_ids = {r.id for r in wf.rules}
    if len(rule_ids) != len(wf.rules):
        errors.append("Rule ids must be unique")
    if len({s.id for s in wf.steps}) != len(wf.steps):
        errors.append("Step ids must be unique")
    if not any(s.type in ("approval", "task") for s in wf.steps):
        errors.append("Workflow has no approval or task step: nothing in it does any work")
    names = [f.name for f in wf.fields]
    if len(set(names)) != len(names):
        errors.append("Form field names must be unique")
    for f in wf.fields:
        if not _FIELD_NAME.fullmatch(f.name):
            errors.append(f"Form field '{f.name}' must be snake_case")
        if f.name in STANDARD_FIELDS:
            errors.append(f"Form field '{f.name}' is on every form already; leave it out of fields")
        if f.type == "choice" and not f.options:
            errors.append(f"Choice field '{f.name}' has no options")
    for field in wf.required_fields:
        if field not in fields:
            errors.append(f"Required field '{field}' is not a form field ({', '.join(sorted(fields))})")
    for rule in wf.rules:
        if rule.when.field not in fields:
            errors.append(f"Rule '{rule.id}' uses '{rule.when.field}', which is not a form field")
    for step in wf.steps:
        for key in ("only_if", "also_if"):
            rule_id = getattr(step, key)
            if rule_id and rule_id not in rule_ids:
                errors.append(f"Step '{step.id}' {key} '{rule_id}' is not a rule id")
        if step.also_if and not step.only_if:
            errors.append(f"Step '{step.id}' has also_if without only_if")
    return errors


def check_against_plan(wf: Workflow, planned: WorkflowCandidate, upstream_fields: Optional[list[FormField]]) -> list[str]:
    """The built workflow keeps the plan's place in the chain and uses the data that arrives with the case."""
    errors: list[str] = []
    if wf.department.lower() != planned.department.lower():
        errors.append(f"department must be '{planned.department}', got '{wf.department}'")
    for key in ("starts_from", "hands_to"):
        want, got = getattr(planned, key), getattr(wf, key)
        if (want or "").lower() != (got or "").lower():
            errors.append(f"{key} must be {want!r}, as planned, got {got!r}")
    if planned.starts_from:
        for step in wf.steps:
            if step.actor == "requester.manager":
                errors.append(f"Step '{step.id}' uses requester.manager, but this workflow starts from "
                              f"{planned.starts_from}'s handoff; use a role of {planned.department}")
    if upstream_fields is not None:
        upstream = {f.name for f in upstream_fields} | STANDARD_FIELDS
        for name in sorted(form_fields(wf) - upstream):
            errors.append(f"Form field '{name}' does not arrive from the upstream workflow; "
                          f"use only these: {', '.join(sorted(upstream))}")
    return errors


def validate_workflow_output(
    data: Any,
    org: Optional[Organization] = None,
    doc_text: Optional[str] = None,
    planned: Optional[WorkflowCandidate] = None,
    upstream_fields: Optional[list[FormField]] = None,
) -> tuple[Optional[Workflow], list[str]]:
    valid, wf, errors = check_schema(data, Workflow)
    if not valid:
        return None, errors
    assert wf is not None

    # Check 2: actors
    errors.extend(check_step_actors(wf, org))
    errors.extend(check_workflow_structure(wf))
    if planned is not None:
        errors.extend(check_against_plan(wf, planned, upstream_fields))

    # Amounts that decide approvals must become rules. Only the passages this workflow
    # is built on count: another department's amounts don't apply to it.
    # A form without a number field (one that arrives from upstream, say) can't hold such a rule.
    amount_text = " ".join(ev.quote for ev in planned.evidence) if planned is not None else doc_text
    has_number = any(f.type == "number" for f in wf.fields) if wf.fields else True
    if amount_text and has_number and not wf.rules and sum(s.type == "approval" for s in wf.steps) >= 2:
        amounts = stated_amounts(amount_text)
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
    errors.extend(check_rule_numbers(wf))

    # Check 3: source quotes in doc_text
    if doc_text:
        for rule in wf.rules:
            if not verify_quote_in_text(rule.source, doc_text):
                errors.append(f"Rule '{rule.id}' source does not ground in uploaded documents: '{rule.source}'")

    if errors:
        return None, errors
    if planned is not None:
        # The plan's spelling, so the web app can compare names exactly
        wf.department, wf.starts_from, wf.hands_to = planned.department, planned.starts_from, planned.hands_to
    wf.upstream_id = None  # only the pipeline sets this, from the workflow it was actually built against
    return wf, []
