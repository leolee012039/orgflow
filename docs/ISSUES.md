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

## 9. Handoffs from "every unit" are not mapped

- Seen 2026-10-05 in the evaluation: National Taitung University got 10 department profiles and 10 built workflows, but no handoffs, so no chains. Its procurement rules say 「採購案逾新臺幣五萬元者，應送總務處辦理」: any unit sends large purchases to 總務處. A handoff needs one sending department, and "any unit" is not one.
- Effect: companies whose policies address every unit get workflows per department but no chained runs.
- Fix direction: allow a handoff from "any department" and let each department's workflow hand to the receiver.
- Status: open, a known limit of the MVP.

## 4. Different job titles may be reported as missing roles

- A policy may say "Director" while a real org chart says 協理 or "Head of Procurement". The workflow architect would list the approver as unresolved, which is a false gap.
- Fix direction: a "possible match, please confirm" state instead of a definite gap.
- Status: **partly fixed.** An approver that the org chart text mentions is reported as `possible_match` ("please confirm"), not as a gap. Synonyms that the org chart never spells out (機關首長 = 校長) are still reported as missing.

## 10. A real university's purchasing rules: the approval levels were never checked

Found 2026-10-05 running National Changhua University of Education's organization regulations (in force 1 Aug 2026) and research purchasing rules (amended 2 Apr 2025).

1. **Look-alike characters.** The regulations PDF stores 44 characters such as 行, 立 and 理 as CJK compatibility ideographs (U+F9xx). A quote with the ordinary 行 never matched the document, and those characters were not even read as Chinese.
2. **No workflow took a request through the approval levels.** The rules set who approves by amount (up to NT$1,000,000 the dean or unit head, then the 總務長, then the president), but any unit may send a request, so no handoff led there and the planner never planned that workflow. The amount levels were therefore never checked.
3. **"The dean or head of the unit the requester belongs to" became a missing role.** 「隸屬院長或一級行政單位主管」 is the requester's own unit head, not a job title, but it was reported as an approver to confirm.
4. **Wording that says both was never reported.** The top level reads 「逾新臺幣150萬元以上」, "over" and "at or above" at once, after a level that ends 「未達150萬元」. Whether exactly NT$1,500,000 goes to the 總務長 or the president can't be read from the words; OrgFlow deliberately reported nothing for such wording.
- Status: **fixed.** Extracted text and quotes are NFKC-normalized before any comparison. The planner plans exactly one workflow per set of approval levels, in the sending department or, when any unit may send, in the department that handles the requests. The architect uses `requester.manager` for the requester's own unit head however the documents phrase it. Wording that says both is reported as **unclear** ("please confirm"), unless a note in brackets such as 「（含）」 settles it. After the fix the university's 11 workflows all passed on Gemini's first answer and the only finding is exactly NT$1,500,000. Tests: `tests/test_amount_coverage.py`, `tests/test_real_documents.py`.

## 11. The sample's live answers vary between runs

- Seen 2026-10-05 locally: one NovaGear run missed the Operations → Procurement handoff, and the first version of the approval-levels rule (issue 10) planned NovaGear's purchase approvals twice, in Operations and in Finance, so the missing Director was reported twice.
- Effect: the sample, which judges try first, can show a different map from one run to the next.
- Status: the duplicate is **fixed** by "never plan the same approval levels in two departments". The missed handoff is Gemini's variation between runs; watch it in the evaluation.

## 12. Review of decisions and "unclear" wording

Found 2026-10-05 by an adversarial review of the decisions change; each case was reproduced with code, no Gemini calls.

1. **New false findings on clear wording.** Any 含 / including / excluding near the amount was read as a note, so 「未達十萬元（含稅）」 / 「十萬元以上（含稅）」 became an overlap and "excluding VAT" a gap. A range that starts with "over" (「逾十萬元至一百萬元」) read as both ways, and one sentence quoted for both levels made the lower level "unclear".
2. **An amount decision changed a rule from another table.** With `<5000` Manager, `>5000` Director and `>=5000` three quotes, choosing "the level below" turned the quotes rule into `>5000`, so a 5,000 request skipped the quotes approval.
3. **Old amount decisions applied after a rebuild**, when the policy no longer left the amount open.
4. **A decision that changed no rule was still recorded as followed**, and the case completed with every approval skipped (a rule written for 5,001).
5. Smaller: every saved decision was sent with every case, so more than 50 would make every run fail; ① and ⒈ became digits under NFKC and joined the amount after them; the stand-in list didn't say who already approves; "It followed N decisions" counted skipped steps; a shared read-only company showed "Change"; Firestore didn't check that decisions are a list.
- Status: **fixed.** Only real notes settle an amount: 「（含）」, 「（不含十萬元）」, "inclusive", "(excluding 5,000)". Each mention of the amount is read on its own, and only a mention that says both ways is unclear (the finding names that side). A range's first amount isn't included when "over" comes before it. An amount decision changes only rules written from the two levels' passages, applies only while the policy leaves that amount open, and counts only when the chosen level then owns the amount; otherwise the case still stops for a person. The page sends only decisions that settle a current problem, list markers become spaces before NFKC, the stand-in list marks roles that already approve, and Firestore accepts at most 200 decisions as a list. Tests: `tests/test_amount_coverage.py`, `tests/test_decisions.py`, `tests/test_real_documents.py`.

## 13. Long real documents and slow hours ran past the 60 s limit

- Seen 2026-10-05 evening: the organization or plan stage of three real universities stopped at 60 s, and the NovaGear organization call took 81 s once (it usually takes 9-20 s). No 429s: Gemini was simply slow, and the 20 s hedge doesn't help when both calls take 40 s or more.
- Status: **partly fixed.** The limit is 90 s (`GEMINI_TIMEOUT_S`), in line with the page's "long documents take up to two minutes". With it, National Taiwan University and National Changhua University of Education pass; National Taitung University's 18-page organization regulations still ran past 90 s in that run (47 s earlier the same day).

## 14. Seen while recording the demo (2026-10-06)

1. **The requester's own unit head is still sometimes listed as an approver to confirm.** In one of two university runs, 「隸屬院長或一級行政單位主管」 came back as an approver to confirm instead of `requester.manager`, although the architect's instruction now names that wording. Gemini's answer varies between runs; the decision feature lets a person settle it ("the requester's department head").
2. **Two departments that hand work to each other draw a clipped label.** On the university map, 總務處 → 主計室 and 主計室 → 總務處 overlap: one label is cut and the return arrow loops above the box.
- Status: open, cosmetic and run-to-run variation; not blocking the submission.


## 15. Submission audit (2026-10-06)

An external read-only audit of f66a35f found what an anonymous or greedy caller could make OrgFlow spend, and gaps in settings, sharing and operations.

1. **`/api/run_chain` reached Gemini without an account and without a limit**, with the reviewer's check and the form taken from the request. Fixed: without an account, Gemini reviews only the sample's own checks, up to `ORGFLOW_ANON_RUN_LIMIT` a day; anything else gets the plain-code check, so cases still run. Forms are limited to 30 fields of text, numbers or yes/no, 2,000 characters each; workflows to 30 steps and a chain to 30 workflows. `/api/run`, unused by the web app, is gone.
2. **Only `/api/analyze` counted against the daily limit.** Fixed: map, plan, build and case runs count against `ORGFLOW_STAGE_LIMIT` (300) per signed-in user.
3. **Sign-in was off unless turned on.** It was on in production, but a redeploy without the setting would have opened every endpoint. Fixed: on unless `ORGFLOW_REQUIRE_AUTH=0`, and on Cloud Run the API refuses to start with sign-in off or `ALLOWED_ORIGINS` missing.
4. **The sample PDFs let anyone build a workflow with Gemini** by asking for one the sample doesn't include. Fixed: without an account, the sample builds only from its saved answers; anything else answers 401.
5. **Anyone could list every shared workspace.** Fixed: the rules allow reading one shared workspace by its link, and listing only one's own.
6. **Guard problems quoting the documents went to Cloud Logging.** Fixed: logs keep the number of problems.
7. Also fixed: an emergency switch (`ORGFLOW_GEMINI_OFF=1`) pauses every live Gemini call; the test guard now fails a test that reaches Gemini instead of letting the fallback hide it; Docker installs the locked versions; `.dockerignore`; security headers on Hosting; complete `.env.example` files; the archived SPEC is marked as such; CI on GitHub Actions; DEPLOY_CHECKLIST.md and RUNBOOK.md.
- Still open, by choice: limits are counted in memory per instance (approximate, documented); uploads are read before the sign-in check, because only the documents tell whether they are the sample; a workflow with several AI checks reviews them all with the first check's wording; commit emails become public with the repository.

## 16. Firestore rules: no checks on what a workspace holds (2026-10-07)

- Found with the Firebase security rules auditor checklist (score 4 of 5: no unauthorized access). Create checked only the owner and the share flag, so a workspace could be created with any fields and sizes, and with more decisions than an update allows. Any field but `shared` and `decisions` could take any type: an owner could turn `built` into text and break the page for the people it is shared with. Nothing limited name length or the number of workflows and cases.
- Status: **fixed.** Create and update share one check: only the fields the web app writes, their types, and the app's limits (30 workflows, 30 cases, 50 decisions, a 200-character name). `scripts/test_firestore_rules.py` runs 27 cases through the Firebase Rules test API, with no emulator and no data touched; the same rules also passed against the real saved workspace.
- Note for testing: the Rules test API reads an ISO date string as a timestamp, so `analyzedAt` accepts either. Creating unlimited workspaces can't be limited in rules; each analysis has a daily limit instead.


## 17. Every live workflow build failed with 400 INVALID_ARGUMENT (2026-10-08)

- Found by running a gym's org chart with four policies end to end after moving to the new project: the map and the plan were built live, then every build answered `400 INVALID_ARGUMENT: Request contains an invalid argument`, the repair too, and the page showed nothing built. The NovaGear sample built live the same way failed too, so the documents were not the cause.
- Cause: on 6 Oct the step limit was written as `Field(max_length=30)` on `Workflow.steps`, which puts `maxItems` in the architect's answer format, and Gemini rejects a format with `maxItems`. Three direct calls confirmed it: the format as is fails, the same format without `maxItems` works. The sample was never affected (it builds from saved answers), and tests never call Gemini, so nothing noticed for two days.
- Status: **fixed.** The limit is a validator, checked after the answer arrives. `tests/test_answer_formats.py` fails if any agent's answer format contains `maxItems`, and checks the limit still holds; both fail on the old code. NovaGear built live again in 8 s.

## 18. "Build all" left problems unreported (2026-10-08)

- Found with the same gym documents: the plan had 10 workflows, "Build all" built 8 (each department's first workflow and the workflows chained to it), and the page said "No problems in the 8 built workflows". Building the other two by hand showed both planted problems: a refund approver the org chart doesn't have, and no approval level for exactly NT$30,000.
- Status: **fixed.** "Build all" builds every planned workflow, each after the workflow it starts from (`web/src/lib/chain.ts`); the evaluation builds the same set. A plan has at most 3 workflows per department, so this adds a few Gemini calls per company.
- Still open: when a policy names a role that exists elsewhere in the company (one branch has an operations supervisor, the other doesn't), the workflow routes to that role without saying so.
- Building everything sent up to a dozen builds at once, and on a slow afternoon several Gemini answers took 80-90 s (one past the 90 s limit). "Build all" now sends at most 3 at a time. A failed build shows on its department and can be built again.
- The same run showed React's duplicate-key warning: the printed report keyed handoffs by department only, so two different handoffs between the same departments collided. Keys now include what is handed over. Rerun: 9 of 12 built, both planted problems found, plus one nobody planted (the Tainan branch has no T3 Fitness Manager, whom its training policy requires), and no warnings.

## 19. Review with ECC's reviewers (2026-10-09)

Four reviewers (FastAPI, React, security, silent failures) read the code; each item below was checked against the code before it was listed.
- **Cost:** a signed-in `/api/run_chain` accepts up to 30 client-written workflows of 30 steps, and every `ai_review` step calls Gemini with a check text of any length: one request, one unit of the daily limit, up to 900 Gemini calls.
- **Gemini failures blamed on the documents:** a 400/403/429 from Vertex is repaired once (a second doomed call), then answered as 422 "check that the PDFs contain selectable text", with the raw error (project and model details) in `problems`; failed calls are logged at INFO, so nothing can alert. This is how the 6-8 Oct build failure stayed hidden.
- **Amounts:** a blank number field is sent as 0 (`Number("")`), and a non-numeric amount makes every amount rule "not met", so its approvals are skipped and the case completes. A rule's field need not be required.
- **Sign-in check blocks the server:** `verify_firebase_token` runs synchronously inside async handlers and fetches Google's certificates on every call, uncached.
- **Silent saves:** saving cases and decisions swallows errors; the page keeps showing "Decided" after a failed save.
- **Shared links:** a viewer can run cases on a shared workspace; the page shows them as saved, the write is rejected silently.
- **"No problems" overclaims:** the card counts only built workflows, ignores failed or unbuilt ones, and amount levels dropped by the checks (all or nothing) leave no trace on the page.
- **"Gemini ran N checks"** counts plain-code fallback checks as Gemini's.
- Lower: PDF parsing on the event loop; a stage can outlast Cloud Run's 300 s; New analysis doesn't cancel a running one; no sign-out on phones; the logo link changes only the URL; a live-region timer announces every second; no CSP; unpinned uv image.
- Status: **fixed**, except the "Lower" line, which stays open by choice.
  - A case runs at most 10 Gemini checks, and each counts against the caller's daily limit; an AI check's text is at most 1,000 characters; a placeholder in a required field is caught by plain code before Gemini is asked.
  - When Gemini doesn't answer (paused, timed out, an API error) there is no repair call, the answer is 503 "Gemini didn't answer just now … nothing is wrong with your documents", and failed calls are logged as WARNING.
  - A case whose amount is blank, a word or NaN is returned to the requester; the web form keeps a blank amount blank.
  - Google's certificates are cached for an hour (10 s timeout), non-JWT tokens are refused without a fetch, and the sign-in check runs off the event loop.
  - Failed saves of workflows, cases and decisions say so; only the owner's changes are saved, and a shared company's Cases page says its cases aren't saved.
  - "No problems" counts only built workflows and says how many aren't built; workflows whose amount levels didn't pass are listed.
  - Gemini's checks and plain code's are counted apart, and a code check is stamped "Checked by code".
  - Checked: 183 tests (tests/test_review_fixes.py and new cases in test_abuse.py), an adversarial review of the diff (no blockers), and a local live run: Xiangying Fitness built 7 of 7 workflows and found both planted problems in both branches; a blank amount was returned; a full case completed; with Gemini paused the page showed the new message and the API answered 503. The same run found a missing key on the department map's chips, now fixed.
