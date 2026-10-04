# OrgFlow build brief (paste this whole file into Gemini)

You are the engineer building **OrgFlow** for the Google Cloud AI Builder Cup 2026. I am Leo, the product owner. Read this whole brief before doing anything. Your first action: create the repo folder and save this brief, unchanged, as `docs/SPEC.md` so you can re-read it in later sessions.

## 0. How we work together

- Work **one phase at a time** (section 14). At the end of each phase, stop and wait for me to type `continue`.
- Report to me in **Traditional Chinese, short sentences, plain words**. Each report has three parts: what you did, the actual command output that proves it works (tests, curl, URLs), and what is not verified yet.
- Never say something works unless you ran it and saw it work. If a test fails, show the failure.
- **Ask me before** you deploy, enable a paid Google Cloud API, create cloud resources, or delete any file.
- Keep code, UI text, README and comments in **English** (submission rules require English).
- Commit to git after every meaningful step, with clear messages. The commit history is our proof that all code was written during the hackathon.

## 1. What we are building

One sentence: a company uploads its org chart and purchasing policy as PDFs; Gemini understands the organization, proposes 3 automation opportunities on its own, compiles one of them into a validated workflow JSON, and a deterministic runner executes a real purchase request through it.

The demo story (must finish in **under 3 minutes**, target 2:45):

| Time | Screen |
|---|---|
| 0:00–0:20 | Upload 2 PDFs (org chart, purchasing policy) |
| 0:20–0:50 | Organization understood: CEO, 4 departments, 8 department roles, who reports to whom |
| 0:50–1:15 | 3 automation opportunities; "Purchase Request & Approval" ranked first |
| 1:15–1:45 | Generated workflow: steps, rules, and the policy quote behind each rule |
| 1:45–2:45 | Run Emma Chen's USD 2,400 MacBook Pro request → Manager ✓, Finance ✓, Director not required → Procurement → COMPLETED |

Theme: **Future of Work & Enterprise Productivity**. Scoring weights: Technical merit & GenAI 40% (robustness, Google Cloud architectural depth), problem fit & impact 25%, innovation 25%, UX 10%.

## 2. Hard rules (breaking any of these can disqualify us)

1. **Fresh code only.** Write everything from scratch now. Do not copy code from other repositories or from Leo's other projects. Installing libraries from npm/PyPI is fine.
2. **Google Cloud only.** Deploy on Cloud Run and Firebase Hosting. Do not use Vercel, Supabase, AWS, Netlify or any non-Google hosting or database.
3. **Gemini only.** The product's AI is Gemini. Do not call OpenAI, Anthropic or any other model provider.
4. **Public GitHub repo.** Never commit secrets. `.env*` goes in `.gitignore` from the first commit. Before each commit, check `git diff --cached` for keys.
5. **No copyrighted or third-party content** in the repo or UI. NovaGear is a fictional company we created.
6. **Stay in scope** (section 15). If an idea is not on the list, write it down in `docs/IDEAS.md` and do not build it.

## 3. Environment facts

- Windows 11, PowerShell. The parent folder path contains Chinese characters: `C:\antigravity檔案資料夾\AI_Builder_Cup_OrgFlow\`. Create the repo at `C:\antigravity檔案資料夾\AI_Builder_Cup_OrgFlow\orgflow`. If a tool breaks because of the path, tell me and propose `C:\dev\orgflow` instead.
- Installed: Node 24, npm 11, git, GitHub CLI `gh` (logged in as `leolee012039`), `uv` 0.11. System Python is 3.10, which is too old: use `uv` to install and pin **Python 3.12** for the backend.
- **Not installed:** Google Cloud CLI (`gcloud`) and Firebase CLI (`firebase`). Phase 0 installs them; Leo will log in himself when you ask.
- Leo puts the AI Studio key in `api/.env` as `GOOGLE_API_KEY` himself. Never print it, log it, or ask him to paste it into the chat.
- Original demo materials (for reference only, do not commit the zips): `C:\Users\user\Downloads\AI_Builder_Cup_OrgFlow_英文版.zip` and `..._中文版.zip`.

## 4. Architecture

```
Browser (Next.js static site on Firebase Hosting)
   │  loads page from Firebase Hosting
   │  calls the API DIRECTLY on Cloud Run (NOT through a Firebase rewrite:
   │  Firebase Hosting rewrites have a 60-second limit and return 504)
   ▼
Cloud Run (asia-east1) · Python 3.12 · FastAPI
   ├── AI pipeline (Google ADK 2 Workflow)
   │     ① Organization Analyst  → organization.json
   │     ② Opportunity Analyst   → opportunities.json
   │     ③ Workflow Architect    → workflow.json
   │     every output goes through the Guard (pure code)
   │     Guard: schema → actors exist → quotes exist in PDF → repair once → fixture
   ├── Workflow Runner (pure code, deterministic)
   │     only the ai_review step calls Gemini
   └── Cloud Logging: one structured JSON log line per step
Gemini 3.8 Flash
   local dev: AI Studio API key; Cloud Run: Vertex AI, location "global"
```

- No database. The browser keeps each JSON and sends it back with the next call. PDFs are small; send them with every call that needs them.
- Model name comes from env `GEMINI_MODEL`, default `gemini-3.8-flash`.
- Auth: if `GOOGLE_API_KEY` is set → AI Studio (`GOOGLE_GENAI_USE_VERTEXAI=False`). On Cloud Run → Vertex AI (`GOOGLE_GENAI_USE_VERTEXAI=True`, `GOOGLE_CLOUD_LOCATION=global`), and the Cloud Run service account needs the Vertex AI User role.
- ADK: use `google-adk` 2.x. Each agent is an ADK `Agent` with an `output_schema`. **Time box:** if ADK blocks you for more than half a day, switch to direct `google-genai` calls with a JSON response schema. Keep the same prompts and schemas. Tell me when you switch.
- **Time budget:** each Gemini call times out at 25 seconds. If the Guard's repair attempt fails or the time budget runs out, return the fixture. Each response carries `"origin": "live" | "repaired" | "fixture"`.

## 5. Data contracts (define them as Pydantic models in `api/schemas.py`)

**organization.json**
```json
{
  "company": "NovaGear Inc.",
  "departments": [{ "name": "Operations", "head_role_id": "operations_manager" }],
  "roles": [{ "id": "operations_manager", "title": "Operations Manager",
              "department": "Operations", "reports_to": "ceo",
              "responsibilities": ["Approve departmental purchase needs and business necessity."] }],
  "relationships": [{ "from": "Operations", "to": "Finance", "description": "...",
                      "evidence": { "doc": "policy", "quote": "..." } }]
}
```
NovaGear has 9 roles in total: CEO (department `null`) plus 8 department roles.

**opportunities.json**: exactly 3 items, ranked.
```json
{ "opportunities": [{ "id": "purchase_request_approval", "name": "Purchase Request & Approval",
    "departments": ["Operations", "Finance", "Procurement"], "manual_handoffs": 4,
    "impact": "HIGH", "why": "...", "executable": true,
    "evidence": [{ "doc": "policy", "quote": "..." }] }] }
```
Only the purchase opportunity is `executable: true`. The others are shown as "Blueprint only". Every opportunity needs at least one evidence quote from the documents.

**workflow.json**
```json
{
  "workflow_name": "Purchase Request Approval",
  "opportunity_id": "purchase_request_approval",
  "required_fields": ["requester", "department", "item", "estimated_cost", "business_justification"],
  "rules": [
    { "id": "r_finance",  "when": { "field": "estimated_cost", "op": ">=", "value": 1000 },
      "source": "USD 1,000 - USD 5,000  Manager approval + Finance validation" },
    { "id": "r_director", "when": { "field": "estimated_cost", "op": ">",  "value": 5000 },
      "source": "Above USD 5,000  Manager approval + Finance validation + Director approval" }
  ],
  "steps": [
    { "id": "completeness_review", "type": "ai_review", "actor": "orgflow_ai",
      "check": "Policy section 2: required information is present and meaningful",
      "on_fail": "human_review" },
    { "id": "manager_approval",   "type": "approval",     "actor": "requester.manager" },
    { "id": "finance_validation", "type": "approval",     "actor": "finance_manager", "only_if": "r_finance" },
    { "id": "director_approval",  "type": "approval",     "actor": "Director",        "only_if": "r_director" },
    { "id": "procurement",        "type": "task",         "actor": "procurement_specialist" },
    { "id": "notify_requester",   "type": "notification", "actor": "requester" }
  ],
  "unresolved_actors": ["Director"],
  "explanation": "..."
}
```
Allowed step types: `approval`, `ai_review`, `task`, `notification`. Allowed `op`: `<`, `<=`, `>`, `>=`, `==`. Special actors: `requester`, `requester.manager` (the head of the requester's department), `orgflow_ai`.

**trace.json**
```json
{ "request_id": "PR-2026-0142", "status": "COMPLETED",
  "steps": [{ "step_id": "director_approval", "type": "approval", "actor": "Director",
              "result": "SKIPPED", "reason": "r_director not met: 2400 > 5000 is false",
              "rule_id": "r_director", "source": "Above USD 5,000 ..." }],
  "metrics": { "manual_handoffs_before": 4, "human_approvals": 2, "ai_checks": 1 } }
```
`status` is one of `COMPLETED`, `RETURNED`, `NEEDS_HUMAN_REVIEW`. Step `result` is one of `PASSED`, `SKIPPED`, `DONE`, `RETURNED`, `HUMAN_REVIEW`.

## 6. Runner semantics (`api/runner.py`, pure code)

The runner never hardcodes 1,000 or 5,000. All thresholds come from `workflow.rules`.

1. Required fields: if any field in `required_fields` is missing or blank → `RETURNED`, stop. No approval happens.
2. Walk the steps in order:
   - If `only_if` names a rule and the rule is false → `SKIPPED`, with the rule and its source quote as the reason.
   - Resolve the actor against organization.json. If the actor is in `unresolved_actors` or cannot be found → `HUMAN_REVIEW`, overall status `NEEDS_HUMAN_REVIEW`, stop. The reason says which role is missing from the org chart.
   - `approval` → `PASSED`, "Approved by simulated <role title>".
   - `ai_review` → one Gemini call with a response schema `{ "decision": "PASS" | "NEEDS_HUMAN_REVIEW", "reasons": [...] }`. It may only check what policy section 2 says. It can never reject on its own: anything other than PASS becomes `HUMAN_REVIEW`. If Gemini fails or times out, use a plain-code fallback (field not empty, not a placeholder such as "N/A", "TBD", "-", at least 3 words) and say "fallback check" in the reason.
   - `task` → `DONE`, "Procurement task created (simulated)".
   - `notification` → `DONE`, "Requester notified (simulated)".
3. If every step finished → `COMPLETED`.

## 7. Guard semantics (`api/guard.py`, pure code)

Run these checks in order on every agent output:
1. It parses into the Pydantic schema.
2. Every step actor exists in organization.json, or is a special actor, or is listed in `unresolved_actors`.
3. Every `source` and `evidence.quote` really comes from the uploaded PDF text. Extract the text server-side with `pypdf`. **Do not require an exact match**: Chinese PDF extraction scrambles word order (the Chinese policy "金額介於 USD 1,000 至 USD 5,000" extracts as "金額介於 至 USD 1,000 USD 5,000"). The rule: every number in the quote appears in the document, and at least 70% of the quote's tokens (words for English, characters for CJK) appear within the same 3-line window. Write tests for an exact English quote (pass), a scrambled Chinese quote (pass), and an invented quote (fail).
4. Every number in a rule's `when.value` appears in that rule's `source` (ignore thousands separators: `1,000` equals `1000`).

If any check fails: send the error list back to the same agent once ("repair"). If it still fails, or the time budget runs out, return the matching fixture from `api/fixtures/`. Log which path was taken.

## 8. Agent instructions (put each in `api/agents/<name>.py`)

- **Organization Analyst:** analyze only the supplied documents. Extract departments, roles, reporting lines and explicit cross-functional relationships. Never invent departments or roles. Output JSON only.
- **Opportunity Analyst:** from organization.json plus the policy, find exactly 3 repetitive or rule-based workflows that involve several roles or departments. Prefer clear handoffs, explicit approval rules, repetitive checks, and workflows that can be demonstrated safely. Every opportunity needs an evidence quote. Do not assume integrations that are not in the documents.
- **Workflow Architect:** compile the chosen opportunity into workflow.json using only the 4 step types. Every actor must exist in organization.json; if the policy names an approver the org chart does not have (NovaGear's "Director"), list it in `unresolved_actors` instead of inventing or mapping it. Every rule needs the policy text it came from in `source`.

## 9. API (`api/main.py`)

| Endpoint | Input | Output |
|---|---|---|
| `GET /api/health` | – | `{ "ok": true, "model": "<GEMINI_MODEL>" }` |
| `POST /api/analyze` | multipart: `org_chart` PDF, `policy` PDF | organization.json + `origin` |
| `POST /api/opportunities` | the 2 PDFs + organization.json | opportunities.json + `origin` |
| `POST /api/workflow` | the 2 PDFs + organization.json + opportunity id | workflow.json + `origin` |
| `POST /api/run` | workflow.json + organization.json + request form JSON | trace.json |

Limits: only `application/pdf`, each file ≤ 5 MB, 2 files max. CORS allows `http://localhost:3000` and our two Firebase Hosting domains only (env `ALLOWED_ORIGINS`). No login.

## 10. Frontend (`web/`)

- Next.js App Router, TypeScript, `output: 'export'` (static files only). API base URL from `NEXT_PUBLIC_API_BASE`.
- One page, 5 steps top to bottom: Upload → Understand → Recommend → Generate → Run. English UI.
- Step 1 has a "Use NovaGear demo files" button that loads the two clean PDFs from `web/public/demo/`.
- Step 2 shows a summary line ("CEO · 4 departments · 8 roles") and a simple org tree. No drag-and-drop graph.
- Step 3 shows 3 cards. Only the executable one has a "Generate workflow" button; the others say "Blueprint only".
- Step 4 shows the steps as a vertical flow. Each rule shows its policy quote. Unresolved actors are highlighted with "Not found in org chart → human review".
- Step 5 shows the request form pre-filled with Emma Chen (PR-2026-0142, Operations, MacBook Pro, USD 2,400, "Laptop required for a new Product Designer supporting the Operations team."). After "Run", play the trace one step at a time (about 600 ms per step), then show the metrics.
- Show a small, honest label when `origin` is `fixture` (for example "cached result").
- Clean, calm design. Readable at phone width. Visible keyboard focus.

## 11. Demo assets (clean versions, generated by a script)

Write `scripts/make_demo_pdfs.py` (reportlab) that writes `demo_assets/en/NovaGear_Organization_Chart.pdf` and `demo_assets/en/NovaGear_Purchasing_Policy.pdf`, and copy them to `web/public/demo/`.

- **Org chart:** company profile; CEO Alex Morgan; the 4 departments and 8 roles; the role responsibilities table. **Remove** the "Cross-functional Relationship" paragraph and the "Primary Demo Flow" line from the original. The AI must discover the flow by itself.
- **Policy:** sections 1–4 of the original (purpose, required information, approval rules table, procurement handoff), wording kept. **Remove** section 5 "Decision Examples" (it contains the demo answer) and section 6 (it mentions OrgFlow, which a real company policy would not).
- **Purchase request:** no PDF. The request comes from the web form.
- Traditional Chinese versions are optional and come later (section 15). If we make them, the policy says only "Director", never "部門主管／Director".

## 12. Deployment (ask me before running any of it)

- Backend: put a `Dockerfile` in `api/` so the build does not depend on buildpack detection. Then `gcloud run deploy orgflow-api --source api --region asia-east1 --allow-unauthenticated --max-instances 2` with env vars `GOOGLE_GENAI_USE_VERTEXAI=True`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION=global`, `GEMINI_MODEL`, `ALLOWED_ORIGINS`.
- Frontend: `npm run build` in `web/` → `firebase deploy --only hosting` with `public: web/out`. No rewrites to Cloud Run.
- README (English): what it is, the architecture diagram as text, which Google Cloud services do what, how to run locally, how to deploy, and the test command.

## 13. Tests (`tests/`, run with `uv run pytest`)

The runner tests use the fixture workflow and a fake Gemini client, so they run without network.

| Case | Expected |
|---|---|
| USD 750 | Manager PASSED; Finance SKIPPED; Director SKIPPED; COMPLETED |
| USD 1,000 | Manager + Finance PASSED (boundary); Director SKIPPED; COMPLETED |
| USD 2,400 | Manager + Finance PASSED; Director SKIPPED; Procurement DONE; COMPLETED |
| USD 5,000 | Manager + Finance PASSED (boundary); Director SKIPPED; COMPLETED |
| USD 8,000 | Director required but not in org chart → HUMAN_REVIEW; NEEDS_HUMAN_REVIEW |
| Missing business justification | RETURNED before any approval |
| Justification "N/A" | ai_review → HUMAN_REVIEW (never RETURNED by AI) |
| Gemini raises an error or times out | Guard returns the fixture with `origin: "fixture"` |

Plus the 3 quote-check tests from section 7, and a test that all 3 fixtures validate against the schemas.

## 14. Phases (stop after each one)

| Phase | Target date | Do | Done when (show me the proof) |
|---|---|---|---|
| 0 | 10/5 | Create the repo and public GitHub repo; `.gitignore`; save SPEC.md; install Python 3.12 via uv; install the gcloud and Firebase CLIs (ask Leo to log in); FastAPI `/api/health`; Next.js page that calls it; ask me, then deploy both | The public Firebase URL shows "API OK" from Cloud Run |
| 1 | 10/6 | Schemas, 3 fixtures, runner, Guard checks 1–2 and 4, all tests. **No AI calls in this phase** | All runner and fixture tests pass |
| 2 | 10/7 | Clean demo PDFs; PDF text extraction; quote check; Organization Analyst; `/api/analyze`; log Gemini latency | 3 runs in a row find CEO + 4 departments + 8 roles; latency reported |
| 3 | 10/8 | Opportunity Analyst, Workflow Architect, `ai_review`; `/api/opportunities`, `/api/workflow`, `/api/run` | Purchase ranked first; every quote passes; each call under 25 s |
| 4 | 10/9–10/10 | Frontend 5 steps; trace playback; ask me, then deploy | The public URL completes the 2,400 run end to end |
| 5 | 10/11 | Feature freeze. Run the full demo 3 times on the public URL; fix only bugs | 3 out of 3 succeed; write `docs/DEMO_CHECKLIST.md` |

After phase 5, only bug fixes, prompt tuning, UI polish and the README are allowed.

## 15. Out of scope (do not build)

Slack, Teams, SAP, Salesforce, Google Workspace integrations; login/SSO; workflow editor; multiple companies; analytics dashboard; real email or real approvals; RAG or vector database; a fourth agent. Optional only if I approve after phase 5: Traditional Chinese demo PDFs; a second fictional company in a different industry.

When in doubt, ask yourself one question: does this make the 3-minute path "documents → opportunities → workflow → successful run" more reliable? If the answer is not a clear yes, don't build it.
