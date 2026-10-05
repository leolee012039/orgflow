"""Amount coverage: does every amount fall into exactly one of the policy's approval tiers?

Gemini lists the tiers and the passage each one comes from. Plain code then reads the
wording where one tier ends and the next begins. 「未達十萬元」 followed by 「逾十萬元」
leaves exactly 100,000 in no tier (a gap); 「十萬元以下」 followed by 「十萬元以上」 puts it
in both (an overlap). A finding needs the wording on both sides to say so, so a tier
Gemini misread can't produce one, and unclear wording such as 「逾十萬元以上」 produces none.
"""

import re
from typing import Optional

from guard import _format_amount, normalize_amounts
from schemas import AmountTier

_CURRENCY = r"(?:新[臺台]幣|[臺台]幣|NT\$|NTD|TWD|USD|US\$|HK\$|S\$|RMB|JPY|人民幣|\$|¥|€|£)?"
_TO_AMOUNT = rf"\s*{_CURRENCY}\s*"  # between a word like 未達 and the amount
_FROM_AMOUNT = r"\s*(?:元|圓|dollars?)?\s*"  # between the amount and a word like 以上
_NOT = r"(?<!not )(?<!no )"
_NUMBER = r"\d+(?:\.\d+)?"

# (end of the tier, what the word means, words before the amount, words after it)
_WORDING = [
    ("upper", "exclusive",
     rf"未達|未滿|不足|(?<!不)低於|(?<!不)少於|{_NOT}\b(?:below|under|less than(?! or equal)|lower than(?! or equal))",
     None),
    ("upper", "inclusive",
     r"不超過|未超過|不逾|未逾|不高於|不多於|\b(?:up to|at most|no more than|not (?:more than|over|above|exceed(?:ing)?)"
     r"|(?:less|lower) than or equal to)",
     r"以下|以內|\b(?:or less|or below|and below|and under)\b"),
    ("lower", "exclusive",
     rf"(?<![不未])逾|(?<![不未])超過|(?<!不)高於|(?<!不)大於|{_NOT}\b(?:above|over|more than(?! or equal)"
     r"|greater than(?! or equal)|exceed(?:s|ing)?|in excess of)",
     None),
    ("lower", "inclusive",
     r"不低於|不少於|\b(?:at least|no less than|not (?:less than|below|under)|(?:greater|more) than or equal to)",
     r"以上|\b(?:or more|or above|and above|and over)\b"),
]
# "USD 1,000 - USD 5,000", 「二萬元至十萬元」, "between 1,000 and 5,000": both ends included.
_RANGE = re.compile(rf"(?<![\d.])({_NUMBER}){_FROM_AMOUNT}(?:[-–—~～至到]|\bto\b|\band\b){_TO_AMOUNT}({_NUMBER})(?![\d.])",
                    re.I)


def bound_wording(source: str, amount: float, end: str) -> set[str]:
    """What the passage says about `amount` as the tier's "upper" or "lower" end:
    {"exclusive"}, {"inclusive"}, both when it says both, or nothing it recognizes."""
    text = normalize_amounts(source)
    number = rf"(?<![\d.]){re.escape(_format_amount(amount))}(?![\d.])"
    found: set[str] = set()
    for tier_end, meaning, before, after in _WORDING:
        if tier_end != end:
            continue
        if re.search(rf"(?:{before}){_TO_AMOUNT}{number}", text, re.I):
            found.add(meaning)
        if after and re.search(rf"{number}{_FROM_AMOUNT}(?:{after})", text, re.I):
            found.add(meaning)
    for m in _RANGE.finditer(text):
        if float(m.group(1 if end == "lower" else 2)) == amount:
            found.add("inclusive")
    return found


def find_amount_gaps(tiers: list[AmountTier]) -> list[dict]:
    """Amounts where one tier ends and the next begins, and the wording on both sides
    leaves the amount in no tier ("gap") or in both ("overlap")."""
    findings: dict[tuple[str, float], dict] = {}
    for below in tiers:
        if below.max is None:
            continue
        for above in tiers:
            if above is below or above.min != below.max:
                continue
            amount = below.max
            ends = bound_wording(below.source, amount, "upper")
            starts = bound_wording(above.source, amount, "lower")
            if ends == starts == {"exclusive"}:
                kind = "gap"
            elif ends == starts == {"inclusive"}:
                kind = "overlap"
            else:
                continue
            findings.setdefault((kind, amount), {
                "kind": kind, "amount": amount, "below": below.source, "above": above.source,
            })
    return sorted(findings.values(), key=lambda f: f["amount"])


def amount_finding(tiers: list[AmountTier], amount: float) -> Optional[dict]:
    """The gap or overlap at exactly this amount, if the policy has one."""
    return next((f for f in find_amount_gaps(tiers) if f["amount"] == amount), None)
