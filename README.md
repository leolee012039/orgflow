# OrgFlow

> Transform company organization charts and operational policies into executable, verified workflows in minutes using Gemini. Built for the Google Cloud AI Builder Cup 2026.

## Overview

OrgFlow solves organizational friction and manual compliance bottlenecks. By analyzing two standard enterprise documents (an Organization Chart PDF and a Purchasing Policy PDF), OrgFlow's multi-agent system:
1. **Understands the Organization:** Extracts departments, hierarchy, and roles.
2. **Discovers Automation Opportunities:** Identifies multi-department, rule-heavy workflows with document citations.
3. **Architects Executable Workflows:** Compiles policies into structured rules and sequential steps with strict Guard validation.
4. **Executes Deterministically:** Runs real business requests through a deterministic runner with verifiable audit traces and metrics.

## Architecture

```
Browser (Next.js static site on Firebase Hosting)
   │  loads page from Firebase Hosting
   │  calls API DIRECTLY on Cloud Run (avoiding 60s rewrite timeouts)
   ▼
Cloud Run (asia-east1) · Python 3.12 · FastAPI
   ┌── AI Pipeline (Google GenAI / ADK 2 Workflow)
   │     • Organization Analyst  -> organization.json
   │     • Opportunity Analyst   -> opportunities.json
   │     • Workflow Architect    -> workflow.json
   │     Every agent output validated by Guard (pure code, quote verification)
   ├── Workflow Runner (pure code, deterministic)
   │     Only ai_review step calls Gemini
   └── Cloud Logging: structured JSON telemetry per step
Gemini 3.8 Flash
   Local dev: Google AI Studio API key
   Cloud Run: Vertex AI (asia-east1 / global)
```

## Google Cloud Services Used

- **Google Cloud Run:** Serverless container hosting for the FastAPI backend with autoscaling and zero cold-start optimization.
- **Firebase Hosting:** Global CDN hosting for the exported Next.js static frontend.
- **Vertex AI & Gemini 3.8 Flash:** Advanced multimodal reasoning for document comprehension, rule extraction, and compliance checks.
- **Google Cloud Logging:** Structured observability and execution traces.

## Quick Start (Local Development)

### Prerequisites
- Node.js 20+ (Node 24 tested)
- Python 3.12 (managed via `uv`)
- Google AI Studio API key (`GOOGLE_API_KEY`)

### Backend (`api/`)
```bash
cd api
uv sync
uv run uvicorn main:app --reload --port 8000
```

### Frontend (`web/`)
```bash
cd web
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) to view the application.

## Testing

Run backend tests using `uv`:
```bash
uv run pytest
```

## Deployment

Deploying backend to Cloud Run:
```bash
gcloud run deploy orgflow-api --source api --region asia-east1 --allow-unauthenticated --max-instances 2
```

Deploying frontend to Firebase Hosting:
```bash
cd web
npm run build
firebase deploy --only hosting
```
