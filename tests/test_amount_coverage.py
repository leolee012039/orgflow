"""Amount coverage: gaps and overlaps between the policy's approval tiers, read by plain code."""

from amount_coverage import amount_finding, bound_wording, find_amount_gaps
from guard import extract_numbers, load_fixture, validate_workflow_output, verified_amount_tiers
from runner import run_workflow
from schemas import AmountTier, Organization, Workflow

GYM_TIERS = [
    AmountTier(max=20000, source="新臺幣二萬元以下 單位主管核准"),
    AmountTier(min=20000, max=100000, source="逾新臺幣二萬元，未達新臺幣十萬元 單位主管及財務經理核准"),
    AmountTier(min=100000, source="逾新臺幣十萬元 單位主管、財務經理及區經理核准後，送陳總經理核定"),
]
NOVAGEAR_TIERS = [AmountTier.model_validate(t) for t in load_fixture("workflow_fixture.json")["amount_tiers"]]


def tiers(*rows: tuple) -> list[AmountTier]:
    return [AmountTier(min=lo, max=hi, source=src) for lo, hi, src in rows]


def test_gym_policy_leaves_exactly_100000_uncovered():
    findings = find_amount_gaps(GYM_TIERS)
    assert [(f["kind"], f["amount"]) for f in findings] == [("gap", 100000)]
    assert "未達新臺幣十萬元" in findings[0]["below"]
    assert "逾新臺幣十萬元" in findings[0]["above"]


def test_novagear_tiers_cover_every_amount_once():
    assert find_amount_gaps(NOVAGEAR_TIERS) == []


def test_inclusive_on_both_sides_is_an_overlap():
    findings = find_amount_gaps(tiers((None, 100000, "十萬元以下：主任核准"), (100000, None, "十萬元以上：校長核准")))
    assert [(f["kind"], f["amount"]) for f in findings] == [("overlap", 100000)]


def test_english_wording():
    gap = tiers((None, 5000, "Under USD 5,000: Manager"), (5000, None, "Over USD 5,000: Director"))
    assert [f["kind"] for f in find_amount_gaps(gap)] == ["gap"]
    covered = tiers((None, 5000, "Up to USD 5,000: Manager"), (5000, None, "Over USD 5,000: Director"))
    assert find_amount_gaps(covered) == []
    no_more = tiers((None, 5000, "No more than $5,000: Manager"), (5000, None, "More than $5,000: Director"))
    assert find_amount_gaps(no_more) == []


def test_unclear_or_missing_wording_reports_nothing():
    # 「逾…以上」 says both: OrgFlow does not claim a gap it can't prove from the words
    assert find_amount_gaps(tiers((500000, 1000000, "逾新臺幣50萬元未達100萬元"), (1000000, None, "逾新臺幣 100 萬元以上"))) == []
    # Gemini says the tiers meet at 100000, but the passages never say how
    assert find_amount_gaps(tiers((None, 100000, "Tier A 100,000"), (100000, None, "Tier B 100,000"))) == []


def test_negations_flip_the_meaning():
    assert bound_wording("不超過新臺幣十萬元", 100000, "upper") == {"inclusive"}
    assert bound_wording("不逾十萬元", 100000, "upper") == {"inclusive"}
    assert bound_wording("不低於十萬元", 100000, "lower") == {"inclusive"}
    assert bound_wording("not exceeding USD 5,000", 5000, "upper") == {"inclusive"}
    assert bound_wording("not exceeding USD 5,000", 5000, "lower") == set()
    assert bound_wording("not to exceed $5,000", 5000, "upper") == {"inclusive"}
    assert bound_wording("not to exceed $5,000", 5000, "lower") == set()
    assert bound_wording("不得超過新臺幣十萬元", 100000, "upper") == {"inclusive"}
    assert bound_wording("不得逾新臺幣十萬元", 100000, "lower") == set()
    assert bound_wording("沒有超過十萬元", 100000, "lower") == set()
    assert bound_wording("1萬元以上未滿10萬元", 100000, "upper") == {"exclusive"}
    assert bound_wording("1萬元以上未滿10萬元", 10000, "lower") == {"inclusive"}


def test_ranges_include_both_ends():
    assert bound_wording("USD 1,000 - USD 5,000", 1000, "lower") == {"inclusive"}
    assert bound_wording("USD 1,000 - USD 5,000", 5000, "upper") == {"inclusive"}
    assert bound_wording("二萬元至十萬元", 100000, "upper") == {"inclusive"}


PAIRS_COVERED_ONCE = [
    # "or equal" written before the comparison word
    ("less than $5,000", "equal to or greater than $5,000"),
    ("at or below $5,000", "above $5,000"),
    ("below $5,000", "at or above $5,000"),
    ("less than $5,000", "equal or exceed $5,000"),
    ("less than $5,000", "meet or exceed $5,000"),
    ("equal to or less than $5,000", "over $5,000"),
    ("Under $5,000 inclusive", "Over $5,000"),
    ("Under $5,000.", "$5,000 or more."),
    ("less than $5,000", "not\nless than $5,000"),
    ("未達十萬元", "等於或超過十萬元"),
    ("等於或低於十萬元", "高於十萬元"),
    # notes in brackets
    ("十萬元以下", "十萬元以上（不含十萬元）"),
    ("十萬元以下（不含十萬元）", "十萬元以上"),
    ("未達新臺幣十萬元", "逾新臺幣十萬元（含）以上"),
]
UNCLEAR_PAIRS = [
    # a word between the amount and 以上 must not hide the inclusive reading
    ("未達5,000美元", "逾5,000美元以上"),
    ("未達新臺幣拾萬元", "逾新臺幣拾萬元整以上"),
    ("under 5,000 USD", "over 5,000 USD or more"),
]


def test_no_finding_when_the_amount_is_covered_once_or_the_wording_is_unclear():
    for below, above in PAIRS_COVERED_ONCE + UNCLEAR_PAIRS:
        amount = 5000 if "5,000" in below else 100000
        assert find_amount_gaps(tiers((None, amount, below), (amount, None, above))) == [], (below, above)


def test_levels_from_two_tables_are_not_paired():
    approvals = [(None, 5000, "Up to $5,000: Manager"), (5000, None, "Over $5,000: Director")]
    quotes = [(None, 5000, "under $5,000: one quote"), (5000, None, "$5,000 or more: three quotes")]
    assert find_amount_gaps(tiers(*approvals, *quotes)) == []


def test_section_numbers_and_dates_are_not_ranges():
    assert bound_wording("第3至5條規定未達五千元者", 5000, "upper") == {"exclusive"}
    assert bound_wording("2026-10修正：逾5,000元", 5000, "lower") == {"exclusive"}


def test_a_full_stop_ends_a_number():
    assert "5000" in extract_numbers("Above USD 5,000.")


def test_amount_finding_only_matches_the_boundary():
    assert amount_finding(GYM_TIERS, {"estimated_cost": 100000})["kind"] == "gap"
    assert amount_finding(GYM_TIERS, {"estimated_cost": 99999}) is None
    assert amount_finding(GYM_TIERS, {"estimated_cost": 20000}) is None


# --- Guard ---------------------------------------------------------------------

def _gym_workflow(**changes) -> Workflow:
    data = {
        "workflow_name": "採購核准", "opportunity_id": "purchase", "required_fields": ["estimated_cost"],
        "rules": [
            {"id": "r_fin", "when": {"field": "estimated_cost", "op": ">", "value": 20000},
             "source": "逾新臺幣二萬元，未達新臺幣十萬元 單位主管及財務經理核准"},
            {"id": "r_area", "when": {"field": "estimated_cost", "op": ">", "value": 100000},
             "source": "逾新臺幣十萬元 單位主管、財務經理及區經理核准後，送陳總經理核定"},
        ],
        "steps": [
            {"id": "head", "type": "approval", "actor": "requester.manager"},
            {"id": "finance", "type": "approval", "actor": "finance_manager", "only_if": "r_fin"},
            {"id": "procure", "type": "task", "actor": "finance_manager"},
        ],
        "amount_tiers": [t.model_dump() for t in GYM_TIERS],
        "explanation": "x",
    }
    return Workflow.model_validate({**data, **changes})


def test_tiers_whose_ends_appear_in_their_passages_are_kept():
    assert verified_amount_tiers(GYM_TIERS) == (GYM_TIERS, [])


def test_one_bad_tier_drops_them_all():
    moved = [t.model_copy() for t in GYM_TIERS]
    moved[2].min = 100001
    kept, problems = verified_amount_tiers(moved)
    assert kept == []
    assert any("100001 does not appear" in p for p in problems)


def test_tiers_never_fail_the_workflow():
    # A side analysis must not turn an uploaded policy into a 422: no tiers is a valid answer
    wf, problems = validate_workflow_output(_gym_workflow(amount_tiers=[]).model_dump())
    assert wf is not None, problems
    moved = [t.model_dump() for t in GYM_TIERS]
    moved[2]["min"] = 100001
    wf, problems = validate_workflow_output(_gym_workflow(amount_tiers=moved).model_dump())
    assert wf is not None, problems


def test_novagear_fixture_still_passes_the_whole_guard():
    from sample_docs import DOC_TEXT

    org = Organization.model_validate(load_fixture("novagear/organization.json"))
    wf, problems = validate_workflow_output(load_fixture("workflow_fixture.json"), org, DOC_TEXT)
    assert wf is not None, problems


# --- Runner --------------------------------------------------------------------

GYM_ORG = Organization.model_validate({
    "company": "翔鷹健身",
    "departments": [{"name": "財務部", "head_role_id": "finance_manager"}],
    "roles": [{"id": "finance_manager", "title": "財務經理", "department": "財務部"}],
})


def _run(amount: float):
    return run_workflow(_gym_workflow(), GYM_ORG, {"department": "財務部", "estimated_cost": amount})


def test_runner_stops_at_the_uncovered_amount():
    trace = _run(100000)
    assert trace.status == "NEEDS_HUMAN_REVIEW"
    assert [s.step_id for s in trace.steps] == ["amount_check"]
    assert "No approval level in the policy covers exactly 100,000" in trace.steps[0].reason
    assert trace.metrics.human_approvals == 0


def test_runner_runs_amounts_the_tiers_cover():
    assert _run(60000).status == "COMPLETED"
    assert _run(20000).status == "COMPLETED"
