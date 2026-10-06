"""Who is calling: anyone who uploads their own documents signs in with Firebase.

The NovaGear sample stays open, so anyone can try OrgFlow without an account. Other
documents need a signed-in user, which also keeps strangers from spending the Gemini
budget. ORGFLOW_REQUIRE_AUTH=1 turns this on (Cloud Run); local development and tests
leave it off.
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
SIGN_IN_MESSAGE = "Sign in to analyze your own documents. The NovaGear sample works without an account."

_transport = google_requests.Request()
_checks_today: dict[tuple[str, date], int] = {}  # per instance; Cloud Run runs at most two


def auth_required() -> bool:
    return os.getenv("ORGFLOW_REQUIRE_AUTH") == "1"


def verify_token(token: str) -> Optional[str]:
    """The user id in a valid Firebase ID token for this project, or None."""
    try:
        claims = id_token.verify_firebase_token(token, _transport, audience=PROJECT_ID)
    except ValueError:
        return None
    except google_auth_exceptions.TransportError as exc:
        raise HTTPException(503, "OrgFlow couldn't check your sign-in just now. Try again in a moment.") from exc
    return (claims or {}).get("sub")


def require_user(request: Request, sample: bool) -> Optional[str]:
    """The signed-in user's id; None for the sample or when sign-in is off."""
    if sample or not auth_required():
        return None
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    uid = verify_token(token) if token else None
    if not uid:
        raise HTTPException(401, SIGN_IN_MESSAGE)
    return uid


def count_health_check(uid: Optional[str]) -> None:
    """Each user may start DAILY_LIMIT analyses a day."""
    if uid is None:
        return
    key = (uid, date.today())
    if _checks_today.get(key, 0) >= DAILY_LIMIT:
        raise HTTPException(429, f"You have started {DAILY_LIMIT} analyses today, the daily limit. Try again tomorrow.")
    _checks_today[key] = _checks_today.get(key, 0) + 1
