"""Who is calling: anyone who uploads their own documents signs in with Firebase.

The NovaGear sample stays open, so anyone can try OrgFlow without an account. Other
documents need a signed-in user, which also keeps strangers from spending the Gemini
budget. Sign-in is on unless ORGFLOW_REQUIRE_AUTH=0 (local development and tests).

Every limit here is counted per Cloud Run instance in memory, so it is approximate: an
instance that restarts starts again from zero, and two instances count separately.
"""

import os
import time
from datetime import date
from typing import Any, Optional

from fastapi import HTTPException, Request
from google.auth import exceptions as google_auth_exceptions
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT", "")
DAILY_LIMIT = int(os.getenv("ORGFLOW_DAILY_LIMIT", "30"))  # analyses per user per day
# Units per user per day: one per map, plan, build and case run, and one per Gemini check a case runs
STAGE_LIMIT = int(os.getenv("ORGFLOW_STAGE_LIMIT", "300"))
ANON_RUN_LIMIT = int(os.getenv("ORGFLOW_ANON_RUN_LIMIT", "300"))  # Gemini reviews in anonymous sample cases
SIGN_IN_MESSAGE = "Sign in to analyze your own documents. The NovaGear sample works without an account."
LOCAL = "local"  # the caller when sign-in is turned off
MAX_TOKEN_CHARS = 4096  # a Firebase ID token is about 1,000


class _CachedCertsRequest(google_requests.Request):
    """google-auth fetches Google's signing certificates on every check; keep them for an hour, and wait at
    most 10 s for them, so a sign-in check is a signature check and not a round trip to Google."""

    CERTS_TTL_S = 3600

    def __init__(self):
        super().__init__()
        self._certs: dict[str, tuple[float, Any]] = {}

    def __call__(self, url, method="GET", body=None, headers=None, timeout=None, **kwargs):
        cacheable = method == "GET" and body is None
        if cacheable and (hit := self._certs.get(url)) and hit[0] > time.monotonic():
            return hit[1]
        response = super().__call__(url, method=method, body=body, headers=headers, timeout=timeout or 10, **kwargs)
        if cacheable and response.status == 200:
            self._certs[url] = (time.monotonic() + self.CERTS_TTL_S, response)
        return response


_transport = _CachedCertsRequest()
_checks_today: dict[tuple[str, date], int] = {}  # per instance; Cloud Run runs at most two
_stages_today: dict[tuple[str, date], int] = {}
_anon_runs: dict[date, int] = {}


def auth_required() -> bool:
    return os.getenv("ORGFLOW_REQUIRE_AUTH", "1") != "0"


def verify_token(token: str) -> Optional[str]:
    """The user id in a valid Firebase ID token for this project, or None."""
    if token.count(".") != 2 or len(token) > MAX_TOKEN_CHARS:  # not a JWT: no need to ask Google
        return None
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


def stage_units_left(uid: Optional[str]) -> int:
    """How many of today's STAGE_LIMIT units a user has left."""
    if uid is None or uid == LOCAL:
        return STAGE_LIMIT
    _forget_old_days(_stages_today)
    return max(STAGE_LIMIT - _stages_today.get((uid, date.today()), 0), 0)


def spend_stage_units(uid: Optional[str], units: int) -> None:
    """Count work already done, such as a case's Gemini checks. Never refuses: the work has run."""
    if uid is None or uid == LOCAL or units <= 0:
        return
    key = (uid, date.today())
    _stages_today[key] = _stages_today.get(key, 0) + units


def count_stage(uid: Optional[str]) -> None:
    """Each signed-in user may spend STAGE_LIMIT units a day on the costly stages; this one costs one."""
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
