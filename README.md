# OrgFlow

**Stop requests from getting stuck between departments.**

OrgFlow reads a company's org chart and policies, maps how work moves from department to department, builds a workflow for each department that hands cases to the next, and shows exactly where the company's own rules leave a request with no one to approve it. Gemini reads the documents; plain code checks every answer against them and runs every case.

Built for the Google Cloud AI Builder Cup 2026 (theme: Future of Work and Enterprise Productivity).

- **Live app:** https://aibul-510701.web.app (the NovaGear sample works without an account)
- **Demo video:** added with the submission
- **Evaluation on real documents:** [docs/EVAL.md](docs/EVAL.md)

## The problem

Every company runs on two documents that were written by different people at different times: the org chart and the policies. Nobody checks one against the other until a request gets stuck.

- A purchasing policy requires **Director** approval above USD 5,000, but the org chart has no Director. Every large request waits in someone's inbox.
- A discount policy gives "below 10%" to Sales Representatives and "above 10%" to Sales Managers. A quote for **exactly 10%** belongs to no one.
- Work changes hands by email and spreadsheets between departments. Before anyone can automate it, a consultant spends weeks interviewing people to draw the process.

## What OrgFlow does

1. **Reads the organization.** Departments, roles and who reports to whom, from the org chart PDF (text or scanned).
2. **Maps the departments.** What each department does and what it hands to which other department, each with the line in the documents that says so.
3. **Plans a workflow per department.** One to three per department, linked along the handoffs: a purchase request in Operations runs on through Procurement and Finance.
4. **Builds each workflow.** The form, the rules taken from the policy, the approval steps. Every rule quotes the passage it came from.
5. **Finds where cases get stuck.** Approvers the org chart doesn't have, amounts no approval level covers, amounts two levels both cover, and wording that says both at once.
6. **Lets a person decide once.** Name who approves in place of the missing Director, or which level owns exactly 10%. Every case after that follows the decision, and the routing slip says so.
7. **Runs cases across departments.** A routing slip is stamped step by step as the case moves from one department's workflow into the next.

## A finding in real documents

National Changhua University of Education's research purchasing rules (amended 2 April 2025) set three approval levels. The second ends at 「未達新臺幣150萬元」 ("below NT$1,500,000"); the third begins 「逾新臺幣150萬元以上」, which says "over" and "at or above" at once. Whether a purchase of exactly NT$1,500,000 is approved by the 總務長 (Dean of General Affairs) or the president cannot be read from the words. Given the university's public organization regulations and these rules, OrgFlow built 11 workflows on Gemini's first answers and flagged exactly this amount for a person to confirm.

Sources: [organization regulations](https://personnelweb.ncue.edu.tw/var/file/1/1001/attach/73/pta_24345_9114766_02987.pdf), [research purchasing rules](https://generalweb.ncue.edu.tw/var/file/4/1004/img/131/838494933.pdf). The evaluation runs six document sets: three real universities, a fictional gym chain in Traditional Chinese, and the sample in English and as scanned images. In the latest run, four built every planned workflow: the scanned sample and the gym chain, with their planted problems found; National Taiwan University, with no problem found; and the Changhua rules above. The live sample built four of five on a slow evening, and one university's 18-page regulations ran past the time limit. Details in [docs/EVAL.md](docs/EVAL.md).

## How it works

```
Browser: Next.js static site on Firebase Hosting
  │  Google sign-in (Firebase Authentication); companies, decisions and cases saved in Firestore
  │  calls the API directly on Cloud Run
  ▼
Cloud Run (asia-east1): Python 3.12, FastAPI
  ├─ Six Google ADK agents on Gemini 3.8 Flash (Vertex AI)
  │    document_reader        scanned PDF → text
  │    organization_analyst   org chart → departments, roles, reporting lines
  │    department_analyst     what each department does, and its handoffs
  │    workflow_planner       1-3 workflows per department, linked along the handoffs
  │    workflow_architect     one workflow: form, rules with quotes, steps, amount levels
  │    request_reviewer       checks a request's information makes sense (the only call while a case runs)
  ├─ Guard (plain code): checks every agent answer before anyone sees it
  ├─ Amount coverage (plain code): reads the wording where one approval level ends and the next begins
  └─ Runner (plain code): moves cases through the workflows and across departments
Cloud Logging: one structured JSON event per Gemini call, guard result and case
```

**Gemini reads, code decides.** Gemini writes each rule once, with the passage it came from. When a case runs, plain code compares the numbers, so the same request always gets the same answer. Gemini is never asked who should approve.

**Every answer is checked against the documents.** The guard rejects an answer when a quote doesn't appear in the PDFs, a role isn't in the org chart, a handoff isn't in the department map, a downstream workflow uses data its upstream doesn't send, or a plan hands cases round in a loop. A failed answer gets one correction request with the list of problems; if that fails too, OrgFlow shows nothing instead of guessing.

**Problems are found by code, not by Gemini.** A missing approver is an approver the workflow needs that the organization doesn't have. An amount problem comes from reading the words on both sides of a boundary: 「未達」 / "below" exclude the amount, 「以上」 / "or more" include it, and a note such as 「（含）」 settles it.

**People decide; code applies the decision.** A decision changes only the rules written from the two levels' own passages, applies only while the policy leaves that amount open, and never makes a case skip an approval the policy requires.

## Google Cloud

| Service | Used for |
|---|---|
| Vertex AI, Gemini 3.8 Flash | All document reading and design, `thinking_level=low`, retries on 429/5xx, a second request after 20 s, 90 s limit per call |
| Agent Development Kit (ADK) | Six agents with typed output schemas |
| Cloud Run | The API, built from source with Cloud Build |
| Firebase Hosting | The web app |
| Firebase Authentication | Google sign-in; the API verifies the ID token for uploaded documents |
| Cloud Firestore | Saved companies, built workflows, decisions and cases, with owner-only security rules and read-only sharing |
| Cloud Logging | Structured events for every Gemini call, guard result and case |

## Privacy and limits

- Uploaded PDFs are read in memory and not stored. Firestore keeps what OrgFlow derived from them, under the signer's account. Logs record events, timings and counts, not document text.
- Analyzing your own documents needs a Google sign-in and is limited to about 30 analyses and 300 later steps per person per day (counted per server instance). The NovaGear sample opens from Gemini's checked, saved reading, so it opens at once; uploaded documents are always read live.
- Without an account, the sample builds only from its saved answers, and its cases get Gemini's review a few hundred times a day; a changed workflow gets the plain-code check instead. One setting pauses every Gemini call in an emergency ([docs/RUNBOOK.md](docs/RUNBOOK.md)).
- Approvals are simulated: OrgFlow does not yet send requests to real approvers.
- Very long documents can take longer than the 90 s limit per stage. Handoffs that the policies give to "any unit" are not mapped yet. Known issues are tracked in [docs/ISSUES.md](docs/ISSUES.md).

## Run it locally

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/), Node.js 20 or later, and a Google Cloud project with Vertex AI enabled (`gcloud auth application-default login`).

```bash
# API
cp api/.env.example api/.env   # then set your project id
cd api && uv run --project .. uvicorn main:app --port 8080

# Web app (another terminal)
cd web && npm install
NEXT_PUBLIC_API_BASE=http://localhost:8080 npm run dev
```

`api/.env`: `GOOGLE_GENAI_USE_VERTEXAI=True`, `GOOGLE_CLOUD_PROJECT=<your project>`, `GOOGLE_CLOUD_LOCATION=global`, `GEMINI_MODEL=gemini-3.8-flash`. Sign-in is on unless `ORGFLOW_REQUIRE_AUTH=0`, which is meant for local development only: without the `NEXT_PUBLIC_FIREBASE_*` settings in `web/.env.local` (see `web/.env.example`) the app runs without accounts. Every setting is listed in `api/.env.example`.

## Tests and evaluation

```bash
uv run --group dev pytest -q                                              # 159 tests, no Gemini calls
uv run --group dev --with pymupdf python scripts/eval_documents.py         # all six document sets, live Gemini
```

The Request Reviewer, the agent that runs inside every case, is also evaluated with Google's agents-cli: 12 of 12 decisions right, and 12 of 12 at 5/5 from a Gemini judge grading it against its own contract ([evals/README.md](evals/README.md)).

Tests replace every agent with a fake or a saved answer and fail if one tries to call Gemini; `tests/test_abuse.py` checks what an anonymous or greedy caller can make OrgFlow spend. GitHub Actions runs the tests, type check and lint on every push. The evaluation downloads the real documents, runs every stage live, builds every linked workflow, runs cases just below, at and above every threshold, and writes [docs/EVAL.md](docs/EVAL.md).

## Deploy

```bash
# --update-env-vars keeps settings already on the service; ^@^ makes @ the separator, because ALLOWED_ORIGINS has commas
gcloud run deploy orgflow-api --source . --region asia-east1 --allow-unauthenticated --max-instances 2 --memory 1Gi \
  --update-env-vars "^@^GOOGLE_GENAI_USE_VERTEXAI=True@GOOGLE_CLOUD_PROJECT=<project>@GOOGLE_CLOUD_LOCATION=global@GEMINI_MODEL=gemini-3.8-flash@ORGFLOW_REQUIRE_AUTH=1@FIREBASE_PROJECT_ID=<project>@ALLOWED_ORIGINS=https://<project>.web.app,https://<project>.firebaseapp.com"
cd web && NEXT_PUBLIC_API_BASE=<Cloud Run URL> npm run build && cd ..
firebase deploy --only hosting,firestore:rules
```

On Cloud Run the API refuses to start when sign-in is turned off or `ALLOWED_ORIGINS` is missing, so a revision with incomplete settings never takes traffic. After each deploy, follow [docs/DEPLOY_CHECKLIST.md](docs/DEPLOY_CHECKLIST.md); when something goes wrong, [docs/RUNBOOK.md](docs/RUNBOOK.md).

## Repository

```
api/            FastAPI app: agents/, guard.py, amount_coverage.py, runner.py, pipeline.py, auth.py
api/fixtures/   the NovaGear sample's saved answers
web/            Next.js app: the console (map, workflows, cases, documents)
tests/          pytest suite
scripts/        evaluation and sample PDF generators
demo_assets/    sample PDFs: NovaGear (English), Xiangying Fitness (Traditional Chinese)
docs/           EVAL.md, ISSUES.md, DEPLOY_CHECKLIST.md, RUNBOOK.md, MOVE_PROJECT.md, SPEC.md (the archived build brief)
firestore.rules Firestore security rules
```
