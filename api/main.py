import os
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, ValidationError
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

import auth  # noqa: E402
import pipeline  # noqa: E402  (reads environment variables at import)
from schemas import Opportunity, Organization, PurchaseRequestForm, Workflow  # noqa: E402

MAX_PDF_BYTES = 5 * 1024 * 1024

app = FastAPI(title="OrgFlow API", version="1.0.0")

# CORS setup
allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "")
allowed_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
if allowed_origins_env:
    for origin in allowed_origins_env.split(","):
        stripped = origin.strip()
        if stripped and stripped not in allowed_origins:
            allowed_origins.append(stripped)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if allowed_origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health():
    model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    return {"ok": True, "model": model}


async def read_pdf(upload: UploadFile, field: str) -> bytes:
    data = await upload.read(MAX_PDF_BYTES + 1)
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(413, f"{field} is larger than 5 MB. Upload a smaller PDF.")
    if not data.startswith(b"%PDF-"):
        raise HTTPException(415, f"{field} is not a PDF file. Upload a .pdf document.")
    return data


STAGE_NAMES = {"organization": "the organization", "opportunities": "the automation opportunities",
               "workflow": "the workflow"}


def stage_response(result, stage: str, by_alias: bool = False) -> dict:
    """The stage's JSON, or a 422 that says plainly why nothing is shown."""
    if result.value is None:
        raise HTTPException(422, {
            "message": f"OrgFlow couldn't verify Gemini's reading of {STAGE_NAMES[stage]} against your documents, "
                       "so it shows nothing instead of guessing. Check that both PDFs contain selectable text, "
                       "or try the NovaGear sample.",
            "problems": result.problems[:5],
        })
    return {**result.value.model_dump(by_alias=by_alias), **result.extras,
            "origin": result.origin, "latency_ms": result.latency_ms}


async def read_documents(request: Request, org_chart: UploadFile, policy: UploadFile) -> tuple[bytes, bytes, Optional[str]]:
    """Both PDFs and the signed-in user (sign-in is needed for anything but the sample)."""
    org_pdf = await read_pdf(org_chart, "org_chart")
    policy_pdf = await read_pdf(policy, "policy")
    uid = auth.require_user(request, pipeline.is_sample(org_pdf, policy_pdf))
    return org_pdf, policy_pdf, uid


@app.post("/api/analyze")
async def analyze(request: Request, org_chart: UploadFile = File(...), policy: UploadFile = File(...)):
    org_pdf, policy_pdf, uid = await read_documents(request, org_chart, policy)
    auth.count_health_check(uid)  # a health check starts here
    result = await pipeline.analyze_organization(org_pdf, policy_pdf)
    return stage_response(result, "organization", by_alias=True)


def parse_json_field(model, raw: str, field: str):
    try:
        return model.model_validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(422, f"{field} is not valid: {exc.errors()[0]['msg']}") from exc


@app.post("/api/opportunities")
async def opportunities(request: Request, org_chart: UploadFile = File(...), policy: UploadFile = File(...),
                        organization: str = Form(...)):
    org = parse_json_field(Organization, organization, "organization")
    org_pdf, policy_pdf, _ = await read_documents(request, org_chart, policy)
    result = await pipeline.discover_opportunities(org_pdf, policy_pdf, org)
    return stage_response(result, "opportunities")


@app.post("/api/workflow")
async def workflow(request: Request, org_chart: UploadFile = File(...), policy: UploadFile = File(...),
                   organization: str = Form(...), opportunity: str = Form(...)):
    org = parse_json_field(Organization, organization, "organization")
    opp = parse_json_field(Opportunity, opportunity, "opportunity")
    if not opp.executable:
        raise HTTPException(400, f"'{opp.name}' is a blueprint only and cannot be generated yet.")
    org_pdf, policy_pdf, _ = await read_documents(request, org_chart, policy)
    result = await pipeline.design_workflow(org_pdf, policy_pdf, org, opp)
    return stage_response(result, "workflow")


class RunBody(BaseModel):
    workflow: Workflow
    organization: Organization
    request: PurchaseRequestForm
    manual_handoffs_before: Optional[int] = None


@app.post("/api/run")
async def run(body: RunBody):
    handoffs = body.manual_handoffs_before if body.manual_handoffs_before is not None else 4
    trace = await pipeline.run_request(body.workflow, body.organization, body.request, handoffs)
    return trace.model_dump()
