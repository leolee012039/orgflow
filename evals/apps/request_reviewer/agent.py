"""OrgFlow's Request Reviewer, exactly as the app runs it, served on its own so agents-cli can evaluate it.

Start it with `adk api_server evals/apps` (see evals/README.md). Nothing here changes the agent.
"""

import sys
from pathlib import Path

API = Path(__file__).resolve().parents[3] / "api"
sys.path.insert(0, str(API))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(API / ".env")

from google.adk.apps import App  # noqa: E402

from agents import request_reviewer  # noqa: E402

root_agent = request_reviewer.build_agent()
app = App(root_agent=root_agent, name="request_reviewer")  # must match this directory's name
