import os
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

import pipeline  # noqa: E402  (reads environment variables at import)

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


@app.post("/api/analyze")
async def analyze(org_chart: UploadFile = File(...), policy: UploadFile = File(...)):
    org_pdf = await read_pdf(org_chart, "org_chart")
    policy_pdf = await read_pdf(policy, "policy")
    result = await pipeline.analyze_organization(org_pdf, policy_pdf)
    return {
        **result.value.model_dump(by_alias=True),
        "origin": result.origin,
        "latency_ms": result.latency_ms,
    }
