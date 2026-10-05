"""Amount coverage: does every amount fall into exactly one of the policy's approval tiers?

Gemini lists the tiers and the passage each one comes from. Plain code then reads the
wording where one tier ends and the next begins. 「未達十萬元」 followed by 「逾十萬元」
leaves exactly 100,000 in no tier (a gap); 「十萬元以下」 followed by 「十萬元以上」 puts it
in both (an overlap).

A false finding on a real policy is worse than a missed one, so a finding needs the
wording on both sides to say so and nothing near the amount to say otherwise: 「逾十萬元
以上」, "at or above", 「（含）」 or 「（不含十萬元）」 all mean no finding.
"""

import re
from typing import Optional

from guard import _format_amount, normalize_amounts
from schemas import AmountTier

_CURRENCY = r"(?:新[臺台]幣|[臺台]幣|NT\$|NTD|TWD|USD|US\$|HK\$|S\$|RMB|JPY|人民幣|\$|¥|€|£)?"
_TO_AMOUNT = rf"\s*{_CURRENCY}\s*"  # between a word like 未達 and the amount
_FROM_AMOUNT = r"\s*(?:元|圓|dollars?)?\s*"  # between the amount and a word like 以上
# "not below", "no more than", "at or above" and 「等於或超過」 turn the plain word around
_NOT = r"(?<!not )(?<!no )(?<!or )"
_NUMBER = r"\d+(?:\.\d+)?"

# (end of the tier, what the word means, words before the amount, words after it)
_WORDING = [
    ("upper", "exclusive",
     rf"未達|未滿|不足|(?<![不或])低於|(?<![不或])少於|{_NOT}\b(?:below|under|less than(?! or equal)|lower than(?! or equal))",
     None),
    ("upper", "inclusive",
     r"(?:不|未|不得|不可|不應|不能|沒有)(?:超過|逾|高於|大於|多於)|等於或(?:低於|少於|小於)|\b(?:up to|at most|no more than"
     r"|not (?:to )?(?:more than|over|above|exceed(?:ing)?)|(?:less|lower) than or equal to"
     r"|(?:at|equal to|equal|is) or (?:below|under|less than|lower than))",
     r"以下|以內|\b(?:or less|or below|or under|and below|and under)\b"),
    ("lower", "exclusive",
     rf"(?<![不未或得可應能有])(?:逾|超過|高於|大於)|{_NOT}\b(?:above|over|more than(?! or equal)"
     r"|greater than(?! or equal)|(?<!not to )exceed(?:s|ing)?|in excess of)",
     None),
    ("lower", "inclusive",
     r"不低於|不少於|等於或(?:超過|高於|大於|多於)|\b(?:at least|no less than|not (?:less than|below|under)"
     r"|(?:greater|more) than or equal to"
     r"|(?:at|equal to|equal|meets?|meeting) or (?:above|over|more than|greater than|higher than|exceed(?:s|ing)?))",
     r"以上|\b(?:or more|or above|or over|and above|and over)\b"),
]
# Ranges include both ends: "USD 1,000 - USD 5,000", 「二萬元至十萬元」, "between 1,000 and 5,000".
_RANGE = re.compile(rf"(?:(?<![\d.])({_NUMBER}){_FROM_AMOUNT}(?:[-–—~～至到]|\bto\b)"
                    rf"|\bbetween{_TO_AMOUNT}({_NUMBER}){_FROM_AMOUNT}and)"
                    rf"{_TO_AMOUNT}({_NUMBER})(?!\d|\.\d)", re.I)
# Words next to the amount that say it is included, or excluded, whatever the main word says
_INCLUDED_BEFORE = re.compile(r"equal|\bat or\b|\bmeets? or\b|等於", re.I)
_INCLUDED_AFTER = re.compile(r"inclusive|including|(?<![不未包])含|(?<![不未])包含|以上|以下|以內"
                             r"|\bor (?:more|less|above|below|over|under)\b|\band (?:above|below|over|under)\b", re.I)
_EXCLUDED_NEAR = re.compile(r"不含|不包括|不包含|exclusive|excluding|not including", re.I)


def bound_wording(source: str, amount: float, end: str) -> set[str]:
    """What the passage says about `amount` as the tier's "upper" or "lower" end:
    {"exclusive"}, {"inclusive"}, both when it says both, or nothing it recognizes."""
    text = re.sub(r"\s+", " ", normalize_amounts(source))
    text = re.sub(r"(\d)\.0+(?!\d)", r"\1", text)  # 5,000.00 is 5000
    number = rf"(?<![\d.]){re.escape(_format_amount(amount))}(?!\d|\.\d)"
    found: set[str] = set()
    for tier_end, meaning, before, after in _WORDING:
        if tier_end != end:
            continue
        if re.search(rf"(?:{before}){_TO_AMOUNT}{number}", text, re.I):
            found.add(meaning)
        if after and re.search(rf"{number}{_FROM_AMOUNT}(?:{after})", text, re.I):
            found.add(meaning)
    for m in _RANGE.finditer(text):
        low, high = float(m.group(1) or m.group(2)), float(m.group(3))
        if 100 <= low < high and (low if end == "lower" else high) == amount:  # not 「第3至5條」 or 2026-10
            found.add("inclusive")
    for m in re.finditer(number, text):
        # Only the words between this amount and its neighbours: in 「1萬元以上未滿10萬元」
        # the 以上 belongs to 1萬, not to 10萬
        before = re.split(r"\d", text[max(0, m.start() - 30):m.start()])[-1]
        after = re.split(r"\d", text[m.end():m.end() + 20])[0]
        if _INCLUDED_BEFORE.search(before) or _INCLUDED_AFTER.search(after):
            found.add("inclusive")
        if _EXCLUDED_NEAR.search(before + " " + after):
            found.add("exclusive")
    return found


def find_amount_gaps(tiers: list[AmountTier]) -> list[dict]:
    """Amounts where one tier ends and the next begins, and the wording on both sides
    leaves the amount in no tier ("gap") or in both ("overlap").

    Only an amount where exactly one tier ends and exactly one begins is checked: two
    tiers ending at the same amount usually come from different tables (approvals and
    quotes, goods and services), and pairing across tables would invent findings.
    """
    findings = []
    for amount in sorted({t.max for t in tiers if t.max is not None}):
        ending = [t for t in tiers if t.max == amount]
        starting = [t for t in tiers if t.min == amount]
        if len(ending) != 1 or len(starting) != 1:
            continue
        below, above = ending[0], starting[0]
        ends = bound_wording(below.source, amount, "upper")
        starts = bound_wording(above.source, amount, "lower")
        if ends == starts == {"exclusive"}:
            kind = "gap"
        elif ends == starts == {"inclusive"}:
            kind = "overlap"
        else:
            continue
        findings.append({"kind": kind, "amount": amount, "below": below.source, "above": above.source})
    return findings


def amount_finding(tiers: list[AmountTier], amount: float) -> Optional[dict]:
    """The gap or overlap at exactly this amount, if the policy has one."""
    return next((f for f in find_amount_gaps(tiers) if f["amount"] == amount), None)
