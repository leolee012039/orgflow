# OrgFlow runbook

For the judging period (Oct 19 - Nov 6, 2026, and to Dec 4 if shortlisted).

- Project: `ai-builder-510613` (moved from `aibul-510701` on 2026-10-08). API: Cloud Run `orgflow-api` (asia-east1). Web: Firebase Hosting `orgflowai.web.app`.
- Owner: Leo (GCP admin). Backup: [name].
- Every command below names the project. If you run others, first `gcloud config set project ai-builder-510613`:
  the old project (`aibul-510701`) is suspended, and a default left pointing at it fails or changes the wrong project.
- Last known good revision: `orgflow-api-00007-lc8` (2026-10-14, commit 978e180, eight sample companies; the one before, `orgflow-api-00006-2kj`). Git tag: `last-good`.
- Adding a sample company: `uv run python scripts/save_sample.py ID "Company" "Market" "Industry" "Language" ORG.pdf POLICY.pdf ...` reads it live once and saves it; check what it prints against what the documents plant, add the planted problems to `tests/test_samples.py`, write example answers into `web/src/lib/samples.json`, then deploy the API and the site.

## 1. The API or the website is down (uptime alert)

1. Open the website and `/api/health` in a private window to confirm.
2. Cloud Run, `orgflow-api`, Logs: look for startup errors. "Cloud Run settings are incomplete" means a deploy missed a setting; the previous revision keeps serving.
3. If the latest deploy caused it, send all traffic back to the last good revision:
   `gcloud run services update-traffic orgflow-api --region asia-east1 --project ai-builder-510613 --to-revisions <LAST_GOOD>=100`
4. Run DEPLOY_CHECKLIST.md steps 2-6.
5. After a fixed revision passes the checklist, give traffic back to the latest revision:
   `gcloud run services update-traffic orgflow-api --region asia-east1 --project ai-builder-510613 --to-latest`
   While traffic is pinned to one revision, new deploys and setting changes get no traffic.

## 2. A budget alert, or unusual Gemini spend

1. Check where traffic goes:
   `gcloud run services describe orgflow-api --region asia-east1 --project ai-builder-510613 --format="yaml(status.traffic)"`
2. If the latest revision has 100%, pause Gemini at once. The sample keeps working: it opens from saved answers and its cases use the plain-code check. Uploaded documents get "couldn't verify".
   `gcloud run services update orgflow-api --region asia-east1 --project ai-builder-510613 --update-env-vars ORGFLOW_GEMINI_OFF=1`
3. If traffic is pinned to an older revision, redeploy that revision's image with the switch on, then move traffic to it:
   `gcloud run revisions describe <SERVING_REVISION> --region asia-east1 --project ai-builder-510613 --format="value(spec.containers[0].image)"`
   `gcloud run deploy orgflow-api --region asia-east1 --project ai-builder-510613 --image <IMAGE> --update-env-vars ORGFLOW_GEMINI_OFF=1`
   `gcloud run services update-traffic orgflow-api --region asia-east1 --project ai-builder-510613 --to-latest`
4. Cloud Logging: count `jsonPayload.event="gemini_call"` by hour to find the source.
5. When it is fixed, resume:
   `gcloud run services update orgflow-api --region asia-east1 --project ai-builder-510613 --remove-env-vars ORGFLOW_GEMINI_OFF`

Budget alerts only notify; they never stop spending, and billing data can lag by hours. The switch is what stops it.

## 3. Gemini errors (429 RESOURCE_EXHAUSTED)

The API retries twice and falls back; the sample is not affected. If it lasts more than an hour, check the project's Vertex AI quotas.

## 4. Saving or sharing broke after a Firestore rules change

Firebase console, Firestore, Rules: restore the previous version from the history. Or redeploy the last good rules:
`git checkout last-good -- firestore.rules && firebase deploy --only firestore:rules --project ai-builder-510613`

## 5. The website broke after a deploy

Firebase console, Hosting, Release history: roll back to the previous release.

## Monitoring to set up once

Set up on 12 October 2026 in `ai-builder-510613`: the email channel "OrgFlow alerts (Leo)", the uptime checks "OrgFlow API health" and "OrgFlow website", the alert policies "OrgFlow API is down" and "OrgFlow website is down", and the budget "OrgFlow (ai-builder-510613)" (NT$320) sending to the same channel. Moving to another project means setting them up again there. On Windows, run the gcloud commands in PowerShell (or with `MSYS_NO_PATHCONV=1` in Git Bash): Git Bash rewrites `--path=/api/health` into a Windows path, and the checks then fail with 404.

- Uptime checks (Cloud Monitoring): HTTPS `orgflow-api-492748170140.asia-east1.run.app/api/health`, every 5 minutes, timeout 30 s (a cold start takes about 10 s), response contains `"ok":true`; a second one for `orgflowai.web.app/`. Alert by email.
- Budget (Cloud Billing): alerts at 50%, 90% and 100%, linked to the same email channel.
