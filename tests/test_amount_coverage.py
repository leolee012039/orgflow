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


def test_any_currency_between_the_word_and_the_amount():
    # Larkspur Bay Logistics: "Below SGD 1,000" and "Above SGD 1,000" were read as no wording at all
    for currency in ("SGD", "AUD", "EUR", "GBP", "MYR", "KRW", "S$", "A$", "NT$", "RM", "€", "₩"):
        gap = tiers((None, 1000, f"Below {currency} 1,000: Customer Service Manager"),
                    (1000, None, f"Above {currency} 1,000: Finance Manager"))
        assert [f["kind"] for f in find_amount_gaps(gap)] == ["gap"], currency
        covered = tiers((None, 1000, f"Up to {currency} 1,000: Manager"), (1000, None, f"Above {currency} 1,000: Director"))
        assert find_amount_gaps(covered) == [], currency


def test_a_currency_after_the_amount():
    gap = tiers((None, 1000, "Below 1,000 SGD"), (1000, None, "Above 1,000 SGD"))
    assert [f["kind"] for f in find_amount_gaps(gap)] == ["gap"]
    overlap = tiers((None, 1000, "1,000 SGD or less"), (1000, None, "1,000 SGD or more"))
    assert [f["kind"] for f in find_amount_gaps(overlap)] == ["overlap"]
    covered = tiers((None, 1000, "Below 1,000 SGD"), (1000, None, "1,000 SGD or more"))
    assert find_amount_gaps(covered) == []


def test_indian_amounts():
    # Indian policies group digits in twos after the first three, and use lakh and crore
    assert extract_numbers("Above Rs. 5,00,000/-") == ["500000"]
    assert extract_numbers("INR 1,25,50,000") == ["12550000"]
    assert extract_numbers("up to ₹2 lakh") == ["200000"]
    assert extract_numbers("up to ₹2.5 lakhs") == ["250000"]
    assert extract_numbers("above INR 1 crore") == ["10000000"]
    assert extract_numbers("Rs 50 lac") == ["5000000"]
    # Three-digit groups and lists of small numbers are unchanged
    assert extract_numbers("USD 1,234,567") == ["1234567"]
    assert extract_numbers("clauses 4, 12, 300") == ["4", "12", "300"]


def test_indian_rupee_wording():
    for currency in ("Rs.", "Rs", "INR", "₹"):
        gap = tiers((None, 500000, f"Below {currency} 5,00,000/-: Finance Controller"),
                    (500000, None, f"Above {currency} 5,00,000/-: Chief Financial Officer"))
        assert [f["kind"] for f in find_amount_gaps(gap)] == ["gap"], currency
        covered = tiers((None, 500000, f"Up to {currency} 5 lakh: Finance Controller"),
                        (500000, None, f"Above {currency} 5 lakh: Chief Financial Officer"))
        assert find_amount_gaps(covered) == [], currency
    overlap = tiers((None, 200000, "Rs. 2,00,000/- and below"), (200000, None, "Rs. 2,00,000/- and above"))
    assert [f["kind"] for f in find_amount_gaps(overlap)] == ["overlap"]


def test_japac_amounts():
    # Korean 만 and 억, dots grouping thousands (Indonesia, Vietnam), juta and triệu
    assert extract_numbers("500만원 이상") == ["5000000"]
    assert extract_numbers("1억원 초과") == ["100000000"]
    assert extract_numbers("5천원") == ["5000"]
    assert extract_numbers("Rp 5.000.000") == ["5000000"]
    assert extract_numbers("Rp5.000.000,00") == ["5000000"]
    assert extract_numbers("Rp 50.000") == ["50000"]
    assert extract_numbers("10.000.000 VND") == ["10000000"]
    assert extract_numbers("50.000 đ") == ["50000"]
    assert extract_numbers("Rp 10 juta") == ["10000000"]
    assert extract_numbers("Rp 1,5 juta") == ["1500000"]
    assert extract_numbers("2 triệu đồng") == ["2000000"]
    # Not amounts: a date, a version, a section number, a day count in Korean
    assert extract_numbers("13.10.2026") == ["13.1", "2026"] or "13102026" not in extract_numbers("13.10.2026")
    assert extract_numbers("version 2.5") == ["2.5"]
    assert extract_numbers("3일만에") == ["3"]


def test_japac_boundary_words():
    cases = [
        # (below passage, above passage, amount, finding)
        ("100万円未満：部長", "100万円を超える場合：取締役", 1000000, "gap"),
        ("100万円未満：部長", "100万円以上：取締役", 1000000, None),
        ("100万円まで：部長", "100万円を超える場合：取締役", 1000000, None),
        ("100万円以下：部長", "100万円以上：取締役", 1000000, "overlap"),
        ("100만원 미만: 팀장", "100만원 초과: 본부장", 1000000, "gap"),
        ("100만원 미만: 팀장", "100만원 이상: 본부장", 1000000, None),
        ("100만원 이하: 팀장", "100만원 초과: 본부장", 1000000, None),
        ("低于5万元：经理", "高于5万元：总监", 50000, "gap"),
        ("不超过5万元：经理", "超过5万元：总监", 50000, None),
        ("Di bawah Rp 5.000.000: Manajer", "Di atas Rp 5.000.000: Direktur", 5000000, "gap"),
        ("Sampai dengan Rp 5.000.000: Manajer", "Di atas Rp 5.000.000: Direktur", 5000000, None),
        ("Kurang dari Rp 5.000.000: Manajer", "Rp 5.000.000 ke atas: Direktur", 5000000, None),
        ("Dưới 10.000.000 đồng: Trưởng phòng", "Trên 10.000.000 đồng: Giám đốc", 10000000, "gap"),
        ("Không quá 10.000.000 đồng: Trưởng phòng", "Trên 10.000.000 đồng: Giám đốc", 10000000, None),
        ("Below Rp 5.000.000: Manager", "Above Rp 5.000.000: Director", 5000000, "gap"),
    ]
    for below, above, amount, kind in cases:
        found = find_amount_gaps(tiers((None, amount, below), (amount, None, above)))
        assert [f["kind"] for f in found] == ([kind] if kind else []), (below, above)


def test_negated_boundary_words_are_not_read_as_plain_ones():
    # "tidak lebih dari" (not more than) and "không vượt quá" (not over) end a level inclusively
    covered = tiers((None, 5000000, "Tidak lebih dari Rp 5.000.000: Manajer"), (5000000, None, "Lebih dari Rp 5.000.000: Direktur"))
    assert find_amount_gaps(covered) == []
    covered = tiers((None, 10000000, "Không vượt quá 10.000.000 đồng: Trưởng phòng"), (10000000, None, "Vượt quá 10.000.000 đồng: Giám đốc"))
    assert find_amount_gaps(covered) == []
    covered = tiers((None, 1000000, "100万円を超えない場合：部長"), (1000000, None, "100万円を超える場合：取締役"))
    assert find_amount_gaps(covered) == []


def test_wording_that_says_both_is_unclear_not_a_gap():
    # 「逾…以上」 says "over" and "at or above" at once: OrgFlow can't prove a gap from the
    # words, so it asks a person to confirm which level owns the amount
    # (National Changhua University of Education's research purchasing rules, section 4)
    findings = find_amount_gaps(tiers((500000, 1000000, "逾新臺幣50萬元未達100萬元"), (1000000, None, "逾新臺幣 100 萬元以上")))
    assert [(f["kind"], f["amount"]) for f in findings] == [("unclear", 1000000)]
    assert amount_finding(tiers((500000, 1000000, "逾新臺幣50萬元未達100萬元"), (1000000, None, "逾新臺幣100萬元以上")),
                          {"estimated_cost": 1000000})["kind"] == "unclear"


def test_missing_wording_reports_nothing():
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


def test_no_finding_when_the_amount_is_covered_once():
    for below, above in PAIRS_COVERED_ONCE:
        amount = 5000 if "5,000" in below else 100000
        assert find_amount_gaps(tiers((None, amount, below), (amount, None, above))) == [], (below, above)


def test_wording_that_says_both_is_reported_as_unclear():
    for below, above in UNCLEAR_PAIRS:
        amount = 5000 if "5,000" in below else 100000
        findings = find_amount_gaps(tiers((None, amount, below), (amount, None, above)))
        assert [f["kind"] for f in findings] == ["unclear"], (below, above)


def test_a_note_in_brackets_settles_wording_that_says_both():
    # 「（含）」 next to 「逾…以上」 says which reading is meant
    assert find_amount_gaps(tiers((None, 100000, "未達新臺幣十萬元"), (100000, None, "逾新臺幣十萬元（含）以上"))) == []
    findings = find_amount_gaps(tiers((None, 100000, "未達新臺幣十萬元"), (100000, None, "逾新臺幣十萬元（不含）以上")))
    assert [f["kind"] for f in findings] == ["gap"]


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


# Found in review: wording that is clear must not become a finding
CLEAR_PAIRS = [
    # tax notes say nothing about the amount
    ("未達十萬元（含稅）", "十萬元以上（含稅）"),
    ("未達十萬元（不含稅）", "十萬元以上（不含稅）"),
    ("Up to $5,000 including tax", "Over $5,000 including tax"),
    ("Under $5,000 excluding VAT", "$5,000 or more excluding VAT"),
    # a range that starts with "over" excludes its first amount
    ("十萬元以下", "逾十萬元至一百萬元"),
    ("Up to $5,000", "Over $5,000 to $25,000"),
]


def test_clear_wording_found_in_review_reports_nothing():
    for below, above in CLEAR_PAIRS:
        amount = 5000 if "5,000" in below else 100000
        assert find_amount_gaps(tiers((None, amount, below), (amount, None, above))) == [], (below, above)


def test_one_sentence_quoted_for_both_levels_is_not_unclear():
    sentence = "未達十萬元者由單位主管核定，十萬元以上者由校長核定"
    assert find_amount_gaps(tiers((None, 100000, sentence), (100000, None, sentence))) == []


def test_an_unclear_finding_names_the_side_that_says_both():
    above = find_amount_gaps(tiers((None, 100000, "未達新臺幣十萬元"), (100000, None, "逾新臺幣十萬元以上")))
    assert above[0]["unclear_side"] == "above"
    below = find_amount_gaps(tiers((None, 100000, "逾一萬元未達十萬元以下"), (100000, None, "逾十萬元")))
    assert below[0]["kind"] == "unclear" and below[0]["unclear_side"] == "below"
