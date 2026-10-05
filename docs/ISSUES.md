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

## 6. Amounts that no approval level covers

- A policy can say 「逾二萬元，未達十萬元」 for one level and 「逾十萬元」 for the next. Exactly NT$100,000 is in neither, so the policy doesn't say who approves it. The rules alone hid this: the runner approved NT$100,000 with the lower level's approvers.
- Fix direction: have Gemini list the amount levels, then check the boundaries with plain code.
- Status: **fixed** (2026-10-05). The workflow architect lists `amount_tiers` (the amounts each level states at its ends, with the passage). The guard checks that each end appears in its passage. `api/coverage.py` then reads the wording on both sides of every shared boundary (未達/逾/以上/以下, below/above/up to/at least, ranges such as "USD 1,000 - USD 5,000", and negations such as 不超過 and "not exceeding"). It reports a gap when both sides exclude the amount and an overlap when both include it. Unclear wording (「逾 100 萬元以上」) produces no finding. A request for exactly that amount stops before any approval. Live evaluation: found the planted gap at 100,000 in the Xiangying Fitness sample, and reported nothing for NovaGear, NTU or NTTU (`docs/EVAL.md`).
- Limits: only boundaries where two levels share the same number are checked. A jump such as "up to 4,999" then "from 5,000" is not reported.
- **Review of 074d010 found false findings** (2026-10-05, every case reproduced):
  1. "Or equal" written before the comparison word was missed, so these gave a false gap: "less than $5,000" + "equal to or greater than $5,000"; "at or below" / "at or above"; "meet or exceed"; "Under $5,000 inclusive"; 「等於或超過十萬元」.
  2. Notes in brackets were ignored: 「十萬元以上（不含十萬元）」 gave a false overlap; 「逾新臺幣十萬元（含）以上」 gave a false gap.
  3. Words between the amount and 以上 hid the inclusive side: 「逾5,000美元以上」, 「逾新臺幣拾萬元整以上」, "over 5,000 USD or more".
  4. Levels from two different tables were paired with each other, giving a gap and an overlap at the same amount.
  5. The guard required `amount_tiers` whenever a rule used `estimated_cost`, contradicting the prompt. An uploaded policy could fail with 422 over a side analysis.
  - Also: an amount followed by a full stop ("Above USD 5,000.") was not read as a number anywhere, including rule checks; `coverage.py` shadows the PyPI `coverage` package.
  - Status: **fixed**, see the next commit.

## 7. A busy Gemini endpoint made a call wait for the full time limit

- Found 2026-10-05 in the evaluation rerun: Vertex answered `429 RESOURCE_EXHAUSTED` for the scanned NovaGear organization call. The stage waited the full 60 s and returned "unverified".
- Cause: ADK reports a failed model call as an event (`error_code`, `error_message`) and can keep the run open afterwards. `api/agents/runtime.py` only read text from events, so it waited for the time limit. The client was also built without retry options, which means it never retried a 429.
- Effect: during judging, a busy moment would freeze a stage for 60 s. Uploaded documents then show "couldn't verify"; the sample falls back to its fixture only after the wait.
- Status: **fixed.** `_run` raises as soon as an error event arrives and closes the run. Every agent uses `gemini()`, which retries 429/5xx twice (about 2 s and 4 s later). Checked live with a model name that doesn't exist: the error came back in 1.6 s. Tests: `tests/test_runtime.py`.

## 8. Review of the department workflows (793a48e, 2ea2b25)

Found 2026-10-05 by an adversarial review; each case was reproduced with saved answers, no Gemini calls.

1. **A case could reach a workflow that was built for a different upstream.** The runner and the page matched the next workflow by department pair. With two Operations workflows handing to Procurement, the case went to a Procurement workflow built against the other one's fields and came back RETURNED.
2. **Some downstream workflows could never run.** The runner picked the first match in build order, while "Build all" and the start points used plan order.
3. **Department names in different case.** The backend ignored case; the page compared exactly. A workflow for "procurement" appeared in no department section, and a lowercase starts_from skipped the upstream field check.
4. **A plan in which two workflows hand to each other locked both**: each waited for the other, and "Build all" did nothing.
5. **One failed build in "Build all" dropped workflows that could still build**, because it used the state from the render when the button was clicked.
6. **Builds kept going after "Analyze another company"**, and could save company A's workflows into company B.
7. **A number too large for a float (10^400) returned 500** from /api/run and /api/run_chain.
- Also: a handoff to a department with no profile left cases waiting forever; a saved sample workflow could be used against an upstream it doesn't fit; a failed save looked saved.
- Status: **fixed.** A built workflow records `upstream_id`, set by code to the workflow it was built against, and cases follow only that link (first in plan order, on both sides). Guards rewrite every department name to the organization's spelling, reject plans whose workflows hand cases round in a loop, reject handoffs to departments without a profile, and use a saved workflow only if it passes the checks against the actual upstream. "Build all" drops only the workflows whose upstream failed. Each company gets its own Workspace component and late builds are dropped. Request numbers must be below 10^15 (422 otherwise). A failed save is shown. Tests: `tests/test_departments.py`; page logic checked against the saved NovaGear answers.

## 4. Different job titles may be reported as missing roles

- A policy may say "Director" while a real org chart says 協理 or "Head of Procurement". The workflow architect would list the approver as unresolved, which is a false gap.
- Fix direction: a "possible match, please confirm" state instead of a definite gap.
- Status: **partly fixed.** An approver that the org chart text mentions is reported as `possible_match` ("please confirm"), not as a gap. Synonyms that the org chart never spells out (機關首長 = 校長) are still reported as missing.
