"""Who is calling: anyone who uploads their own documents signs in with Firebase.

The NovaGear sample stays open, so anyone can try OrgFlow without an account. Other
documents need a signed-in user, which also keeps strangers from spending the Gemini
budget. Sign-in is on unless ORGFLOW_REQUIRE_AUTH=0 (local development and tests).

Every limit here is counted per Cloud Run instance in memory, so it is approximate: an
instance that restarts starts again from zero, and two instances count separately.
"""

import os
from datetime import date
from typing import Optional

from fastapi import HTTPException, Request
from google.auth import exceptions as google_auth_exceptions
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "aibul-510701")
DAILY_LIMIT = int(os.getenv("ORGFLOW_DAILY_LIMIT", "30"))  # analyses per user per day
STAGE_LIMIT = int(os.getenv("ORGFLOW_STAGE_LIMIT", "300"))  # map, plan, build and case runs per user per day
ANON_RUN_LIMIT = int(os.getenv("ORGFLOW_ANON_RUN_LIMIT", "300"))  # Gemini reviews in anonymous sample cases
SIGN_IN_MESSAGE = "Sign in to analyze your own documents. The NovaGear sample works without an account."
LOCAL = "local"  # the caller when sign-in is turned off

_transport = google_requests.Request()
_checks_today: dict[tuple[str, date], int] = {}  # per instance; Cloud Run runs at most two
_stages_today: dict[tuple[str, date], int] = {}
_anon_runs: dict[date, int] = {}


def auth_required() -> bool:
    return os.getenv("ORGFLOW_REQUIRE_AUTH", "1") != "0"


def verify_token(token: str) -> Optional[str]:
    """The user id in a valid Firebase ID token for this project, or None."""
    try:
        claims = id_token.verify_firebase_token(token, _transport, audience=PROJECT_ID)
    except ValueError:
        return None
    except google_auth_exceptions.TransportError as exc:
        raise HTTPException(503, "OrgFlow couldn't check your sign-in just now. Try again in a moment.") from exc
    return (claims or {}).get("sub")


def _bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    return header[7:].strip() if header.lower().startswith("bearer ") else ""


def optional_user(request: Request) -> Optional[str]:
    """The signed-in user's id, LOCAL when sign-in is off, or None for an anonymous caller."""
    if not auth_required():
        return LOCAL
    token = _bearer(request)
    return verify_token(token) if token else None


def require_user(request: Request, sample: bool) -> Optional[str]:
    """The signed-in user's id; None for the sample or when sign-in is off."""
    if sample or not auth_required():
        return None
    token = _bearer(request)
    uid = verify_token(token) if token else None
    if not uid:
        raise HTTPException(401, SIGN_IN_MESSAGE)
    return uid


def _forget_old_days(counts: dict) -> None:
    today = date.today()
    for key in [k for k in counts if (k[1] if isinstance(k, tuple) else k) != today]:
        del counts[key]


def count_stage(uid: Optional[str]) -> None:
    """Each signed-in user may call the costly stages STAGE_LIMIT times a day."""
    if uid is None or uid == LOCAL:
        return
    _forget_old_days(_stages_today)
    key = (uid, date.today())
    if _stages_today.get(key, 0) >= STAGE_LIMIT:
        raise HTTPException(429, "You have reached today's limit. Try again tomorrow.")
    _stages_today[key] = _stages_today.get(key, 0) + 1


def anonymous_review_allowed() -> bool:
    """While True, anonymous sample cases get Gemini's review; after the day's limit, the plain-code check."""
    _forget_old_days(_anon_runs)
    today = date.today()
    if _anon_runs.get(today, 0) >= ANON_RUN_LIMIT:
        return False
    _anon_runs[today] = _anon_runs.get(today, 0) + 1
    return True


def count_analysis(uid: Optional[str]) -> None:
    """Each user may start DAILY_LIMIT analyses a day."""
    if uid is None or uid == LOCAL:
        return
    _forget_old_days(_checks_today)
    key = (uid, date.today())
    if _checks_today.get(key, 0) >= DAILY_LIMIT:
        raise HTTPException(429, f"You have started {DAILY_LIMIT} analyses today, the daily limit. Try again tomorrow.")
    _checks_today[key] = _checks_today.get(key, 0) + 1
