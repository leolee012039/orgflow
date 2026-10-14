"""Findings of the second review with ECC's reviewers (docs/ISSUES.md #30), each pinned by a test."""

import time

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import main
import pipeline
from agents import runtime
from amount_coverage import find_amount_gaps
from guard import extract_numbers, names_in_text, normalize_amounts
from schemas import MAX_RULES, MAX_SOURCE_TEXT, AmountTier, Rule, RuleWhen, Workflow


def tiers(*rows):
    return [AmountTier(field="amount", min=lo, max=hi, source=src) for lo, hi, src in rows]


def kinds(below, above, amount):
    return [f["kind"] for f in find_amount_gaps(tiers((None, amount, below), (amount, None, above)))]


def test_a_long_run_of_digits_is_read_in_linear_time():
    # Before: 20,000 digits took about 40 s, from patterns that restarted at every digit
    for tail in ("", "萬", "만원", " lakh", " juta"):
        started = time.perf_counter()
        normalize_amounts("1" * 20000 + tail)
        assert time.perf_counter() - started < 1, tail


def test_a_dotted_amount_can_end_a_sentence():
    assert extract_numbers("Rp 5.000.000.") == ["5000000"]
    assert extract_numbers("Limit is Rp 5.000.000. Next") == ["5000000"]
    assert extract_numbers("Rp 50.000.") == ["50000"]


def test_korean_units_followed_by_a_word_are_not_amounts():
    for text in ("고객 100 만족", "5 만큼", "3 만약", "4 억울", "200 만났다"):
        assert normalize_amounts(text) == text, text
    assert extract_numbers("500만원 이상") == ["5000000"]
    assert extract_numbers("300만 이상") == ["3000000"]
    assert extract_numbers("1억원이 넘는") == ["100000000"]
    assert extract_numbers("5천만원") == ["50000000"]
    assert extract_numbers("ver 3 tỷ lệ") == ["3"]
    assert extract_numbers("2 tỷ đồng") == ["2000000000"]


def test_until_words_later_in_the_sentence_dont_make_a_gap_unclear():
    assert kinds("100万円未満：部長", "100万円を超える場合は社長決裁まで必要", 1000000) == ["gap"]
    assert kinds("100만원 미만: 팀장", "100만원 초과 시 사장님 승인까지 필요", 1000000) == ["gap"]
    assert kinds("100만원 미만: 팀장", "100만원 초과: 팀장 이상", 1000000) == ["gap"]
    # Right after the amount they still mean "up to and including"
    assert kinds("100万円まで：部長", "100万円を超える場合：取締役", 1000000) == []
    assert kinds("100만원까지: 팀장", "100만원 초과: 본부장", 1000000) == []


def test_negated_indonesian_and_vietnamese_comparisons():
    assert kinds("Tidak boleh lebih dari Rp 5.000.000: Manajer", "Lebih dari Rp 5.000.000: Direktur", 5000000) == []
    # "ít hơn" (less than) is not "hơn" (more than): no "over" is read from it
    assert kinds("Ít hơn 10.000.000 đồng: Trưởng phòng", "Hơn 10.000.000 đồng: Giám đốc", 10000000) != ["overlap"]


def test_a_role_name_in_latin_letters_must_be_whole_words():
    chart = "Chris Wong, Sales Manager\nDirector of Engineering\nItems team\nNice officer"
    assert not names_in_text("HR", chart)
    assert not names_in_text("CTO", chart)
    assert not names_in_text("IT", chart)
    assert not names_in_text("CEO", chart)
    assert names_in_text("Sales Manager", chart)
    assert names_in_text("Director of Engineering", "Director of\nEngineering")
    assert names_in_text("R&D Manager", "Head: R & D Manager")
    # CJK titles are still found with spacing removed (an org chart extracted one character per line)
    assert names_in_text("主計室", "人\n事\n室\n主\n計\n室")


def test_only_real_html_entities_are_decoded():
    data = runtime._parse_json('{"a": "People &amp; Culture", "b": "Legal&regulatory affairs", "c": "Sales&notices",'
                               ' "d": "a &lt; b", "e": "R&D", "f": "&#39;quoted&#39;"}')
    assert data == {"a": "People & Culture", "b": "Legal&regulatory affairs", "c": "Sales&notices",
                    "d": "a < b", "e": "R&D", "f": "'quoted'"}


def test_quoted_sources_and_rule_lists_are_bounded():
    Rule(id="r", when=RuleWhen(field="amount", op=">", value=1), source="x" * MAX_SOURCE_TEXT)
    with pytest.raises(ValidationError):
        Rule(id="r", when=RuleWhen(field="amount", op=">", value=1), source="1" * (MAX_SOURCE_TEXT + 1))
    with pytest.raises(ValidationError):
        AmountTier(field="amount", min=1, source="1" * (MAX_SOURCE_TEXT + 1))
    wf = pipeline.load_fixture("novagear/workflows/operations_purchase_request_submission.json")
    wf["rules"] = [dict(wf["rules"][0], id=f"r{i}") for i in range(MAX_RULES + 1)]
    with pytest.raises(ValidationError):
        Workflow.model_validate(wf)


def test_run_chain_refuses_an_endless_source_from_anyone():
    wf = pipeline.load_fixture("novagear/workflows/operations_purchase_request_submission.json")
    wf["amount_tiers"] = [{"field": "estimated_cost", "min": 1, "source": "1" * 100_000}]
    org = pipeline.load_fixture("novagear/organization.json")
    body = {"workflows": [wf], "organization": org, "start_id": wf["opportunity_id"],
            "request": {"request_id": "X", "requester": "A", "department": "Operations", "estimated_cost": 5}}
    started = time.perf_counter()
    res = TestClient(main.app).post("/api/run_chain", json=body)
    assert res.status_code == 422 and time.perf_counter() - started < 5


def test_a_sample_workflow_with_other_rules_or_approvers_is_not_the_sample():
    wf = Workflow.model_validate(pipeline.load_fixture("novagear/workflows/operations_purchase_request_submission.json"))
    assert pipeline.is_sample_workflow(wf)
    changed_rule = wf.model_copy(deep=True)
    changed_rule.rules[0].when.value = 1
    assert not pipeline.is_sample_workflow(changed_rule)
    changed_actor = wf.model_copy(deep=True)
    changed_actor.steps[0].actor = "someone_else"
    assert not pipeline.is_sample_workflow(changed_actor)
