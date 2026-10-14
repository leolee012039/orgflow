"""Amount coverage: does every amount fall into exactly one of the policy's approval tiers?

Gemini lists the tiers and the passage each one comes from. Plain code then reads the
wording where one tier ends and the next begins. 「未達十萬元」 followed by 「逾十萬元」
leaves exactly 100,000 in no tier (a gap); 「十萬元以下」 followed by 「十萬元以上」 puts it
in both (an overlap).

A false finding on a real policy is worse than a missed one, so a finding needs the
wording on both sides to say so and nothing near the amount to say otherwise: "at or
above", 「（含）」 or 「（不含十萬元）」 all mean no gap. A note on the amount settles it
whatever the main word says; 「（含稅）」 or "excluding VAT" is not such a note.

Wording that says both at once, like 「逾十萬元以上」 ("over, and at or above"), is
reported as unclear: the words can't tell which level owns the amount, so a person
confirms it.
"""

import re
from typing import Optional

from guard import _format_amount, normalize_amounts
from schemas import AmountTier

# Any currency between the word and the amount: an ISO code (SGD, AUD, EUR ...), a prefixed dollar (S$, NT$, A$),
# RM, Rp and Rs., a symbol, or a Chinese or Japanese name. Words a policy writes there are never three capitals.
_CURRENCY = (r"(?:新[臺台][幣币]|[臺台][幣币]|人民[幣币]|港[幣币]|日圓|日元|[A-Z]{1,3}\$|[A-Z]{3}(?![A-Za-z])|RM|Rp|Rs\.?|"
             r"\$|¥|€|£|₩|₹|₱|฿|₫|円)?")
_TO_AMOUNT = rf"\s*{_CURRENCY}\s*"  # between a word like 未達 and the amount
# Between the amount and a word like 以上, or "SGD"; Indian amounts often end in "/-" (Rs. 5,00,000/-),
# Korean ones in 원, Vietnamese ones in đồng
_FROM_AMOUNT = r"\s*(?:/-)?\s*(?:元|圓|円|원|đồng|đ|dong|บาท|dollars?|rupees?|rupiah|[A-Z]{3}(?![A-Za-z]))?\s*"
# "not below", "no more than", "at or above" and 「等於或超過」 turn the plain word around
_NOT = r"(?<!not )(?<!no )(?<!or )"
_NUMBER = r"\d+(?:\.\d+)?"

# (end of the tier, what the word means, words before the amount, words after it).
# Chinese words come in traditional and simplified forms (低於 低于, 超過 超过). Japanese and Korean put the
# word after the amount: 100万円未満, 100万円を超える, 100만원 미만, 100만원 초과. Indonesian (di bawah, di atas,
# sampai dengan) and Vietnamese (dưới, trên, không quá) put it before; "tidak" and "không" negate it.
_WORDING = [
    ("upper", "exclusive",
     rf"未[達达]|未[滿満]|不足|(?<![不或])低[於于]|(?<![不或])少[於于]|{_NOT}\b(?:below|under|less than(?! or equal)"
     r"|lower than(?! or equal))|\b(?:di bawah|(?<!tidak )kurang dari)|\bdưới",
     r"未[滿満]|미만"),
    ("upper", "inclusive",
     r"(?:不|未|不得|不可|不[應应]|不能|[沒没]有)(?:超[過过]|逾|高[於于]|大[於于]|多[於于])|等[於于]或(?:低[於于]|少[於于]|小[於于])"
     r"|\b(?:up to|at most|no more than"
     r"|not (?:to )?(?:more than|over|above|exceed(?:ing)?)|(?:less|lower) than or equal to"
     r"|(?:at|equal to|equal|is) or (?:below|under|less than|lower than))"
     r"|\b(?:sampai dengan|s\.d\.|hingga|maksimal|maksimum|paling banyak|tidak (?:boleh )?lebih dari"
     r"|tidak (?:boleh )?melebihi)"
     r"|\b(?:không quá|tối đa|không vượt quá|không hơn)",
     r"以下|以[內内]|まで|까지|이하|を?超えない|\b(?:or less|or below|or under|and below|and under|ke bawah|trở xuống)\b"),
    ("lower", "exclusive",
     rf"(?<![不未或得可應应能有])(?:逾|超[過过]|高[於于]|大[於于])|{_NOT}\b(?:above|over|more than(?! or equal)"
     r"|greater than(?! or equal)|(?<!not to )exceed(?:s|ing)?|in excess of)"
     r"|\b(?:di atas|(?<!tidak )(?<!boleh )lebih dari|(?<!tidak )(?<!boleh )melebihi)"
     r"|\b(?:trên|(?<!không )vượt quá|(?<!không )(?<!ít )hơn)",
     r"を?超え(?!ない)|超(?![過过え])|초과"),
    ("lower", "inclusive",
     r"不低[於于]|不少[於于]|等[於于]或(?:超[過过]|高[於于]|大[於于]|多[於于])|\b(?:at least|no less than|not (?:less than|below|under)"
     r"|(?:greater|more) than or equal to"
     r"|(?:at|equal to|equal|meets?|meeting) or (?:above|over|more than|greater than|higher than|exceed(?:s|ing)?))"
     r"|\b(?:minimal|minimum|paling sedikit|sekurang-kurangnya|tidak kurang dari|mulai)|\b(?:từ|tối thiểu|ít nhất)",
     r"以上|이상|\b(?:or more|or above|or over|and above|and over|ke atas|trở lên)\b"),
]
# Ranges include both ends: "USD 1,000 - USD 5,000", 「二萬元至十萬元」, "between 1,000 and 5,000",
# 「100万円から500万円まで」, "Rp 5.000.000 sampai dengan Rp 10.000.000", "từ 5.000.000 đến 10.000.000".
_RANGE = re.compile(rf"(?:(?<![\d.])({_NUMBER}){_FROM_AMOUNT}(?:[-–—~～至到]|から|\bto\b|\bsampai(?: dengan)?\b|\bhingga\b|\bđến\b)"
                    rf"|\bbetween{_TO_AMOUNT}({_NUMBER}){_FROM_AMOUNT}and)"
                    rf"{_TO_AMOUNT}({_NUMBER})(?!\d|\.\d)", re.I)
# Words next to the amount that say it is included, whatever the main word says
_INCLUDED_BEFORE = re.compile(r"equal|\bat or\b|\bmeets? or\b|等[於于]", re.I)
# Searched in the 20 characters after the amount, so only words that can't belong to the rest of the sentence:
# まで, 까지, 이상 and 이하 also end ordinary phrases (社長決裁まで必要, 팀장 이상), so they count only right after
# the amount, through the words after it in _WORDING (ISSUES.md #30)
_INCLUDED_AFTER = re.compile(r"以上|以下|以[內内]"
                             r"|\bor (?:more|less|above|below|over|under)\b|\band (?:above|below|over|under)\b", re.I)


def _prepared(source: str, amount: float) -> tuple[str, str]:
    """The passage with amounts as plain digits, and a pattern for this amount in it."""
    text = re.sub(r"\s+", " ", normalize_amounts(source))
    text = re.sub(r"(\d)\.0+(?!\d)", r"\1", text)  # 5,000.00 is 5000
    return text, rf"(?<![\d.]){re.escape(_format_amount(amount))}(?!\d|\.\d)"


def _near(text: str, match: re.Match) -> tuple[str, str]:
    """The words between this amount and its neighbours: in 「1萬元以上未滿10萬元」
    the 以上 belongs to 1萬, not to 10萬."""
    before = re.split(r"\d", text[max(0, match.start() - 30):match.start()])[-1]
    after = re.split(r"\d", text[match.end():match.end() + 20])[0]
    return before, after


def _notes(number: str) -> list[tuple[str, re.Pattern]]:
    """Notes that settle the amount on their own. Only a real note counts: 「（含稅）」,
    "including tax" or "excluding VAT" say nothing about the amount."""
    note = r"[(]\s*(不)?(?:含|包含|包括)\s*(?:本數)?\s*[)]"  # 「（含）」 「（不含）」 right after the amount
    return [
        ("chinese", re.compile(rf"{number}{_FROM_AMOUNT}{note}")),
        # 「（不含十萬元）」: a note that names the amount
        ("chinese", re.compile(rf"[(]\s*(不)?(?:含|包含|包括)\s*(?:本數)?{_TO_AMOUNT}{number}{_FROM_AMOUNT}[)]")),
        # "Under $5,000 inclusive", "(exclusive)"
        ("english", re.compile(rf"{number}{_FROM_AMOUNT}[(,]?\s*(inclusive|exclusive)\b(?!\s+of)", re.I)),
        # "(including $5,000)", "(not including 5,000)"
        ("english", re.compile(rf"[(]\s*(including|excluding|not including){_TO_AMOUNT}{number}{_FROM_AMOUNT}[)]", re.I)),
    ]


def noted_wording(source: str, amount: float) -> set[str]:
    """What a note on the amount says, like 「（含）」, 「（不含十萬元）」 or "inclusive"."""
    text, number = _prepared(source, amount)
    found: set[str] = set()
    for language, pattern in _notes(number):
        for m in pattern.finditer(text):
            word = (m.group(1) or "").lower()
            if language == "chinese":
                found.add("exclusive" if word == "不" else "inclusive")
            else:
                found.add("inclusive" if word in ("inclusive", "including") else "exclusive")
    return found


def _occurrences(source: str, amount: float, end: str) -> list[set[str]]:
    """What the words around each occurrence of `amount` say about the tier's "upper" or
    "lower" end. One occurrence can say both: 「逾十萬元以上」."""
    text, number = _prepared(source, amount)
    # Where a range starts or ends at this amount: 「二萬元至十萬元」
    range_ends: set[int] = set()
    for m in _RANGE.finditer(text):
        low_group = 1 if m.group(1) else 2
        low, high = float(m.group(low_group)), float(m.group(3))
        if 100 <= low < high:  # not 「第3至5條」 or 2026-10
            if end == "lower" and low == amount:
                range_ends.add(m.start(low_group))
            if end == "upper" and high == amount:
                range_ends.add(m.start(3))
    out = []
    for m in re.finditer(number, text):
        before, after = _near(text, m)
        found: set[str] = set()
        for tier_end, meaning, words_before, words_after in _WORDING:
            if tier_end != end:
                continue
            if re.search(rf"(?:{words_before}){_TO_AMOUNT}$", before, re.I):
                found.add(meaning)
            if words_after and re.match(rf"{_FROM_AMOUNT}(?:{words_after})", after, re.I):
                found.add(meaning)
        if _INCLUDED_BEFORE.search(before) or _INCLUDED_AFTER.search(after):
            found.add("inclusive")
        # A range includes its ends, unless the word before it says otherwise: 「逾十萬元至一百萬元」
        if m.start() in range_ends and "exclusive" not in found:
            found.add("inclusive")
        out.append(found)
    return out


def bound_wording(source: str, amount: float, end: str) -> set[str]:
    """What the passage says about `amount` as the tier's "upper" or "lower" end:
    {"exclusive"}, {"inclusive"}, both when it says both, or nothing it recognizes."""
    return set().union(*_occurrences(source, amount, end))


def _side(source: str, amount: float, end: str) -> tuple[set[str], bool]:
    """What the passage says about this end of its tier, and whether a single mention
    says both. A note on the amount settles it."""
    noted = noted_wording(source, amount)
    if len(noted) == 1:
        return noted, False
    occurrences = _occurrences(source, amount, end)
    return set().union(*occurrences), any(len(o) == 2 for o in occurrences)


def tier_end(source: str, amount: float, end: str) -> set[str]:
    """What the passage says about this end of its tier, a note on the amount first."""
    return _side(source, amount, end)[0]


def find_amount_gaps(tiers: list[AmountTier]) -> list[dict]:
    """Amounts where one tier ends and the next begins, and the wording on both sides
    leaves the amount in no tier ("gap"), in both ("overlap"), or can't say ("unclear":
    one mention of the amount says both, like 「逾十萬元以上」).

    Only an amount where exactly one tier ends and exactly one begins is checked: two
    tiers ending at the same amount usually come from different tables (approvals and
    quotes, goods and services), and pairing across tables would invent findings. A
    passage that mentions the amount twice with different words (one sentence quoted
    for both tiers) is not unclear: the words belong to different tiers.
    """
    findings = []
    for field in sorted({t.field for t in tiers}):  # an amount and a discount rate never meet
        same_field = [t for t in tiers if t.field == field]
        for amount in sorted({t.max for t in same_field if t.max is not None}):
            ending = [t for t in same_field if t.max == amount]
            starting = [t for t in same_field if t.min == amount]
            if len(ending) != 1 or len(starting) != 1:
                continue
            below, above = ending[0], starting[0]
            ends, ends_both = _side(below.source, amount, "upper")
            starts, starts_both = _side(above.source, amount, "lower")
            finding = {"field": field, "amount": amount, "below": below.source, "above": above.source}
            if ends == starts == {"exclusive"}:
                finding["kind"] = "gap"
            elif ends == starts == {"inclusive"}:
                finding["kind"] = "overlap"
            elif ends and starts and (ends_both or starts_both):
                finding["kind"] = "unclear"
                finding["unclear_side"] = "above" if starts_both else "below"
            else:
                continue  # covered once, or wording OrgFlow can't read either way
            findings.append(finding)
    return findings


def amount_findings(tiers: list[AmountTier], values: dict) -> list[dict]:
    """Every gap or overlap that this request's numbers fall on exactly."""
    hits = []
    for finding in find_amount_gaps(tiers):
        value = values.get(finding["field"])
        try:
            if value is not None and float(value) == finding["amount"]:
                hits.append(finding)
        except (TypeError, ValueError):
            continue
    return hits


def amount_finding(tiers: list[AmountTier], values: dict) -> Optional[dict]:
    """The gap or overlap that this request's numbers fall on exactly, if the policy has one."""
    hits = amount_findings(tiers, values)
    return hits[0] if hits else None
