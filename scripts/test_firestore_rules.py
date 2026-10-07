"""Test firestore.rules with the Firebase Rules test API: no emulator, no data touched.

    uv run python scripts/test_firestore_rules.py [project]   (default: the project in .firebaserc)

Each case gives the request, the existing document and whether the rules must allow it.
"""

import copy
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECT = sys.argv[1] if len(sys.argv) > 1 else json.loads((ROOT / ".firebaserc").read_text(encoding="utf-8"))["projects"]["default"]
PATH = "/databases/(default)/documents/workspaces/w1"

GOOD = {
    "organization": {"company": "NovaGear Inc.", "departments": [], "roles": []},
    "departmentMap": {"departments": [], "handoffs": []},
    "plan": {"workflows": []},
    "company": "NovaGear Inc.",
    "documents": {"orgChart": "chart.pdf", "policies": ["policy.pdf"]},
    "built": {},
    "analyzedAt": "2026-10-07T10:00:00.000Z",
    "sample": True,
    "owner": "alice",
    "shared": False,
}


def doc(**changes):
    d = copy.deepcopy(GOOD)
    for key, value in changes.items():
        if value is None:
            d.pop(key, None)
        else:
            d[key] = value
    return d


def case(name, expect, method, uid=None, new=None, old=None):
    request = {"path": PATH, "method": method}
    if uid:
        request["auth"] = {"uid": uid}
    if new is not None:
        request["resource"] = {"data": new}
    test = {"expectation": expect, "request": request}
    if old is not None:
        test["resource"] = {"data": old}
    return name, test


BUILT = {"operations_purchase": {"workflow_name": "Purchase", "steps": []}}
SAVED = doc(built=BUILT)
SHARED = doc(built=BUILT, shared=True)
CASES = [
    case("owner creates a workspace", "ALLOW", "create", "alice", doc()),
    case("create for someone else", "DENY", "create", "alice", doc(owner="bob")),
    case("create already shared", "DENY", "create", "alice", doc(shared=True)),
    case("create without signing in", "DENY", "create", None, doc()),
    case("create with 51 decisions", "DENY", "create", "alice", doc(decisions=[{}] * 51)),
    case("create with 31 cases", "DENY", "create", "alice", doc(cases=[{}] * 31)),
    case("create with an extra field", "DENY", "create", "alice", doc(isAdmin=True)),
    case("create with a 201-character name", "DENY", "create", "alice", doc(company="x" * 201)),
    case("create without the plan", "DENY", "create", "alice", doc(plan=None)),
    case("create with built as text", "DENY", "create", "alice", doc(built="oops")),
    case("owner saves built workflows", "ALLOW", "update", "alice", doc(built=BUILT), doc()),
    case("owner saves 30 cases and 50 decisions", "ALLOW", "update", "alice",
         doc(built=BUILT, cases=[{}] * 30, decisions=[{}] * 50), SAVED),
    case("owner turns built into text", "DENY", "update", "alice", doc(built="oops"), SAVED),
    case("owner saves 31 cases", "DENY", "update", "alice", doc(built=BUILT, cases=[{}] * 31), SAVED),
    case("owner saves 51 decisions", "DENY", "update", "alice", doc(built=BUILT, decisions=[{}] * 51), SAVED),
    case("owner hands the workspace to someone else", "DENY", "update", "alice", doc(built=BUILT, owner="bob"), SAVED),
    case("owner renames the company", "DENY", "update", "alice", doc(built=BUILT, company="Other"), SAVED),
    case("owner shares it", "ALLOW", "update", "alice", doc(built=BUILT, shared=True), SAVED),
    case("someone else saves cases", "DENY", "update", "bob", doc(built=BUILT, cases=[{}]), SAVED),
    case("anyone opens a shared link", "ALLOW", "get", None, None, SHARED),
    case("someone else opens an unshared one", "DENY", "get", "bob", None, SAVED),
    case("owner opens their own", "ALLOW", "get", "alice", None, SAVED),
    case("anyone lists shared workspaces", "DENY", "list", None, None, SHARED),
    case("someone else lists them", "DENY", "list", "bob", None, SHARED),
    case("owner lists their own", "ALLOW", "list", "alice", None, SAVED),
    case("someone else deletes it", "DENY", "delete", "bob", None, SAVED),
    case("owner deletes it", "ALLOW", "delete", "alice", None, SAVED),
]

token = subprocess.run("gcloud auth print-access-token", shell=True, capture_output=True, text=True).stdout.strip()
body = {
    "source": {"files": [{"name": "firestore.rules", "content": (ROOT / "firestore.rules").read_text(encoding="utf-8")}]},
    "testSuite": {"testCases": [test for _, test in CASES]},
}
req = urllib.request.Request(
    f"https://firebaserules.googleapis.com/v1/projects/{PROJECT}:test",
    data=json.dumps(body).encode(),
    headers={"Authorization": f"Bearer {token}", "x-goog-user-project": PROJECT, "Content-Type": "application/json"},
)
try:
    reply = json.load(urllib.request.urlopen(req, timeout=60))
except urllib.error.HTTPError as exc:
    sys.exit(f"rules test API error {exc.code}: {exc.read().decode()[:600]}")
if "issues" in reply:
    sys.exit("rules don't compile: " + json.dumps(reply["issues"])[:600])
failed = 0
for (name, test), result in zip(CASES, reply["testResults"]):
    ok = result.get("state") == "SUCCESS"
    failed += not ok
    print(f"{'ok  ' if ok else 'FAIL'} {test['expectation']:5} {name}"
          + ("" if ok else f"  {result.get('debugMessages') or result.get('errorPosition') or ''}"))
print(f"{len(CASES) - failed} of {len(CASES)} passed")
sys.exit(1 if failed else 0)
