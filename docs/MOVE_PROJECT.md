# Moving OrgFlow to another Google Cloud project

About an hour. The code reads the project from its settings, so a move changes three places: `.firebaserc`, the Cloud Run settings and `web/.env.local`. Saved workspaces stay in the old project.

## 1. In the console (the project owner, about 15 minutes)

1. Create the project and link a billing account. Add a budget with alerts at 50%, 90% and 100%.
2. Firebase console: Add project, pick the new Google Cloud project.
3. Firebase console, Authentication: Get started, Sign-in method, Google, Enable.

## 2. From the repository root

```bash
P=<new-project-id>
export GOOGLE_CLOUD_QUOTA_PROJECT=$P   # the Firebase CLI runs on gcloud credentials

gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  aiplatform.googleapis.com firestore.googleapis.com identitytoolkit.googleapis.com \
  firebasehosting.googleapis.com firebaserules.googleapis.com --project $P
gcloud firestore databases create --location=asia-east1 --project $P

# Web app settings: copy apiKey, authDomain, projectId and appId into web/.env.local (gitignored)
firebase apps:create WEB orgflow-web --project $P
firebase apps:sdkconfig WEB --project $P

# API. --set-env-vars replaces every setting, so nothing from the old project carries over.
# SITE is the website's own name (https://$SITE.web.app): a site name belongs to the project that made it,
# so a new project needs a new one. Leave it out of ALLOWED_ORIGINS and the site can't call the API.
SITE=<new-site-name>
gcloud config set project $P   # nothing below falls back to an old, suspended project
gcloud run deploy orgflow-api --source . --region asia-east1 --project $P --allow-unauthenticated \
  --max-instances 2 --memory 1Gi --quiet \
  --set-env-vars "^@^GOOGLE_GENAI_USE_VERTEXAI=True@GOOGLE_CLOUD_PROJECT=$P@GOOGLE_CLOUD_LOCATION=global@GEMINI_MODEL=gemini-3.8-flash@ORGFLOW_REQUIRE_AUTH=1@FIREBASE_PROJECT_ID=$P@ALLOWED_ORIGINS=https://$SITE.web.app,https://$P.web.app,https://$P.firebaseapp.com"
API=$(gcloud run services describe orgflow-api --region asia-east1 --project $P --format="value(status.url)")

# Website and Firestore rules: first set "default" in .firebaserc to the new project.
# For an address other than $P.web.app, create a site and set "site" under "hosting" in firebase.json;
# then add that site to ALLOWED_ORIGINS above and to Authentication's authorized domains.
firebase hosting:sites:create $SITE --project $P
cd web && NEXT_PUBLIC_API_BASE=$API npm run build && cd ..
uv run python scripts/test_firestore_rules.py
firebase deploy --only hosting,firestore:rules --project $P --non-interactive
```

If Gemini calls fail with 403, the Cloud Run service account (`<project number>-compute@developer.gserviceaccount.com`) needs the Vertex AI User role. The project owner grants it in IAM.

## 3. Check

Follow [DEPLOY_CHECKLIST.md](DEPLOY_CHECKLIST.md) with `API=$API` and `WEB=https://$P.web.app`.

## 4. Update the addresses

- `README.md`, `docs/DEPLOY_CHECKLIST.md`, `docs/RUNBOOK.md`
- The deck's cover and closing slides
- The submission form
- Uptime checks and the budget (RUNBOOK.md, "Monitoring to set up once")

The demo video shows no address and needs no change.
