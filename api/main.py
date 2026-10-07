import os
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field, ValidationError
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()


def check_cloud_run_settings(env=os.environ) -> list[str]:
    """Settings Cloud Run must have; always empty anywhere else (K_SERVICE is set by Cloud Run)."""
    if not env.get("K_SERVICE"):
        return []
    problems = []
    if env.get("ORGFLOW_REQUIRE_AUTH", "1") == "0":
        problems.append("ORGFLOW_REQUIRE_AUTH must not be 0 on Cloud Run")
    if not env.get("ALLOWED_ORIGINS"):
        problems.append("ALLOWED_ORIGINS is not set")
    if not (env.get("FIREBASE_PROJECT_ID") or env.get("GOOGLE_CLOUD_PROJECT")):
        problems.append("FIREBASE_PROJECT_ID is not set")  # without it every sign-in fails
    return problems


# A revision with incomplete settings fails to start, so Cloud Run keeps serving the previous one
_problems = check_cloud_run_settings()
if _problems:
    raise RuntimeError("Cloud Run settings are incomplete: " + "; ".join(_problems))

import auth  # noqa: E402
import pipeline  # noqa: E402  (reads environment variables at import)
from schemas import (  # noqa: E402
    MAX_CHAIN_WORKFLOWS,
    MAX_DECISIONS,
    Decision,
    DepartmentMap,
    Organization,
    RequestForm,
    Workflow,
    WorkflowCandidate,
)

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


MAX_POLICIES = 5

STAGE_NAMES = {"organization": "the organization", "department_map": "the departments and their handoffs",
               "workflow_plan": "the department workflow plans", "workflow": "the workflow"}


NO_WORK_MESSAGE = ("This org chart shows who is in each department, but nothing in the documents says what "
                   "the departments do or where their work goes, so OrgFlow can't map them. Add a policy or "
                   "job descriptions, such as purchasing, refund or leave rules, and analyze again.")


def stage_response(result, stage: str, by_alias: bool = False) -> dict:
    """The stage's JSON, or a 422 that says plainly why nothing is shown."""
    if result.value is None and result.origin == pipeline.NO_WORK:
        raise HTTPException(422, {"message": NO_WORK_MESSAGE, "problems": []})
    if result.value is None:
        raise HTTPException(422, {
            "message": f"OrgFlow couldn't verify Gemini's reading of {STAGE_NAMES[stage]} against your documents, "
                       "so it shows nothing instead of guessing. Check that the PDFs contain selectable text, "
                       "or try the NovaGear sample.",
            "problems": result.problems[:5],
        })
    return {**result.value.model_dump(by_alias=by_alias), **result.extras,
            "origin": result.origin, "latency_ms": result.latency_ms}


async def read_documents(request: Request, org_chart: UploadFile,
                         policies: list[UploadFile]) -> tuple[pipeline.Docs, Optional[str]]:
    """The org chart, the policies, and the caller: a signed-in user (needed for anything but
    the sample), auth.LOCAL when sign-in is off, or None for an anonymous sample."""
    if len(policies) > MAX_POLICIES:
        raise HTTPException(413, f"Upload at most {MAX_POLICIES} policies at a time.")
    docs = pipeline.Docs(
        org_chart=await read_pdf(org_chart, "org_chart"),
        policies=[await read_pdf(p, f"policy {i}") for i, p in enumerate(policies, 1)],
    )
    if pipeline.is_sample(docs):
        return docs, auth.optional_user(request)
    return docs, auth.require_user(request, False) or auth.LOCAL


def parse_json_field(model, raw: str, field: str):
    try:
        return model.model_validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(422, f"{field} is not valid: {exc.errors()[0]['msg']}") from exc


@app.post("/api/analyze")
async def analyze(request: Request, org_chart: UploadFile = File(...), policies: list[UploadFile] = File(default=[])):
    docs, uid = await read_documents(request, org_chart, policies)
    if not pipeline.is_sample(docs):
        auth.count_analysis(uid)  # an analysis starts here; the sample opens from saved answers
    result = await pipeline.analyze_organization(docs)
    return stage_response(result, "organization", by_alias=True)


@app.post("/api/map")
async def department_map(request: Request, org_chart: UploadFile = File(...),
                         policies: list[UploadFile] = File(default=[]), organization: str = Form(...)):
    org = parse_json_field(Organization, organization, "organization")
    docs, uid = await read_documents(request, org_chart, policies)
    auth.count_stage(uid)
    result = await pipeline.map_departments(docs, org)
    return stage_response(result, "department_map", by_alias=True)


@app.post("/api/plan")
async def plan(request: Request, org_chart: UploadFile = File(...), policies: list[UploadFile] = File(default=[]),
               organization: str = Form(...), department_map: str = Form(...)):
    org = parse_json_field(Organization, organization, "organization")
    dmap = parse_json_field(DepartmentMap, department_map, "department_map")
    docs, uid = await read_documents(request, org_chart, policies)
    auth.count_stage(uid)
    result = await pipeline.plan_workflows(docs, org, dmap)
    return stage_response(result, "workflow_plan")


@app.post("/api/build")
async def build(request: Request, org_chart: UploadFile = File(...), policies: list[UploadFile] = File(default=[]),
                organization: str = Form(...), planned: str = Form(...), upstream: str = Form(default="null")):
    org = parse_json_field(Organization, organization, "organization")
    candidate = parse_json_field(WorkflowCandidate, planned, "planned")
    upstream_wf = None if upstream.strip() in ("", "null") else parse_json_field(Workflow, upstream, "upstream")
    docs, uid = await read_documents(request, org_chart, policies)
    auth.count_stage(uid)
    # Without an account, the sample builds only from its saved answers: no Gemini call
    result = await pipeline.build_workflow(docs, org, candidate, upstream_wf, allow_live=uid is not None)
    if result.origin == "sign_in_required":
        raise HTTPException(401, auth.SIGN_IN_MESSAGE)
    return stage_response(result, "workflow")


class ChainBody(BaseModel):
    workflows: list[Workflow] = Field(..., max_length=MAX_CHAIN_WORKFLOWS)
    organization: Organization
    start_id: str
    request: RequestForm
    handoffs_before: dict[str, int] = {}
    # What a person settled: who approves in place of a missing approver, which level owns an exact amount
    decisions: list[Decision] = Field(default_factory=list, max_length=MAX_DECISIONS)


@app.post("/api/run_chain")
async def run_chain(request: Request, body: ChainBody):
    if not any(w.opportunity_id == body.start_id for w in body.workflows):
        raise HTTPException(422, f"No built workflow '{body.start_id}' to start from.")
    uid = auth.optional_user(request)
    if uid is not None:
        auth.count_stage(uid)
        live = True
    else:
        # Without an account, Gemini reviews only the sample's own checks, a few hundred times a
        # day; anything else gets the plain-code check, so the case still runs
        live = all(pipeline.is_sample_workflow(w) for w in body.workflows) and auth.anonymous_review_allowed()
    trace = await pipeline.run_chain_request(body.workflows, body.organization, body.start_id, body.request,
                                             body.handoffs_before, live_review=live, decisions=body.decisions)
    return trace.model_dump()
