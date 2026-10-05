# Known issues

Found on 2026-10-05 during the council review of business value. Each entry: what breaks, how it was confirmed, status.

## 1. Amounts next to Chinese characters are not extracted

- `api/guard.py` `extract_numbers` uses `\b`. In Python's Unicode regex, CJK characters are word characters, so there is no word boundary in 「新台幣50,000元」.
- Confirmed: `extract_numbers('採購金額超過新台幣50,000元者，5萬元以下')` returns `[]`. Amounts written as 「5萬」 are also not understood.
- Effect: threshold checks (guard check 4) and quote checks fail on Chinese policies, so the stage falls back to the NovaGear fixture.
- Status: **fixed.** `normalize_amounts` writes every amount as digits (1,000 / 30萬 / 5 千萬 / 五萬元 / 新臺幣三千元) and number extraction no longer uses `\b`. Tests in `tests/test_real_documents.py`.

## 2. Someone else's documents can come back as NovaGear

- `api/pipeline.py` falls back to the NovaGear fixtures for organization, opportunities and workflow when the guard rejects two answers. The only notice is one grey line in the UI.
- Effect: a judge who uploads their own PDFs may see NovaGear's org chart, which looks like faked output.
- Fix direction: use the fixture only for the NovaGear sample; for other documents show "needs human review" with the guard's problems.
- Status: **fixed.** Fixtures are used only when both PDFs match `api/fixtures/sample_documents.json` (sha256, written by `scripts/make_demo_pdfs.py`). Other documents get HTTP 422 with the guard's problems, shown on the page.

## 3. Scanned PDFs have no text to check quotes against

- `extract_pdf_text` uses pypdf, which returns no text for image-only PDFs. Every quote check then fails.
- Fix direction: when pypdf returns little or no text, ask Gemini to transcribe the PDF and check quotes against that transcript.
- Status: **fixed.** When a PDF has fewer than 40 visible characters per page, Gemini transcribes it once (cached by sha256) and the guard checks quotes against the transcript. Live check 2026-10-05 with JPEG-only versions of the NovaGear PDFs: both transcribed in 5–6 s, all three stages passed on the first answer, the Director gap was found.

## 5. Real run: National Taiwan University (2026-10-05)

Inputs, unchanged: NTU organization table (`ntuinfo.ntu.edu.tw/pdf/p1_2_0_strusys.pdf`) and NTU purchase request rules (`請購作業規範112.1.7修正.pdf`), uploaded to the live API.

- **Organization collapsed after repair.** The first answer named about 30 colleges and offices with dean ids that were not roles (the org table lists units, not heads). The guard rejected it, and the repair "fixed" it by deleting almost everything: 1 department, 3 roles. Cause: `head_role_id` is required, and the repair prompt does not forbid dropping correct content.
- **False gaps.** The workflow listed 採購組 and 主計室 as approvers missing from the org chart. 主計室 is on the NTU org table; it was lost in the collapsed organization.
- **No rules.** The policy states thresholds (「院系所未逾 30 萬元之請購：由請購單位主管核定」, 「200 萬元以上由校長核定」), but the workflow had no rules, so every approval was unconditional. The guard did not notice.
- **Vertical text.** The org table extracts one character per line, which also weakens quote checks against it.
- **Latency.** Organization took 28 s with the repair, opportunities 21 s.
- Status: **fixed for this pair** (rerun 2026-10-05, local backend): all three stages passed on the first answer (13 s, 11 s, 11 s); 4 rules with Chinese quotes (逾 10 萬, 逾 30 萬會主計室, 100 萬以上, 未達 100 萬); units (研究發展處, 採購組, 主計室) approve as units. Fixes: `head_role_id` optional, repair prompt keeps correct content, workflow architect writes amounts in full, guard rejects an empty rule set when the documents state amounts, departments can be actors, quote check ignores spacing (vertical text).
- Still open: the policy's 「機關首長或其授權人員」 stays unresolved. It may be the 校長 under another name, or a real gap (the delegate is not named). Shown as "missing"; see item 4.

## 4. Different job titles may be reported as missing roles

- A policy may say "Director" while a real org chart says 協理 or "Head of Procurement". The workflow architect would list the approver as unresolved, which is a false gap.
- Fix direction: a "possible match, please confirm" state instead of a definite gap.
- Status: **partly fixed.** An approver that the org chart text mentions is reported as `possible_match` ("please confirm"), not as a gap. Synonyms that the org chart never spells out (機關首長 = 校長) are still reported as missing.
