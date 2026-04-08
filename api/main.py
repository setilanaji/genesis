"""
Genesis API — ADK web UI + semantic recall endpoint.
Entry point for Cloud Run: uvicorn api.main:app
"""
from __future__ import annotations

import os
from pathlib import Path

from google.adk.cli.fast_api import get_fast_api_app

from .routes import router

# agent_dir is the directory containing agent.py (genesis root)
_agent_dir = str(Path(__file__).parent.parent)

# Session storage:
#   - Local dev  → SQLite (zero setup)
#   - Cloud Run  → PostgreSQL via AlloyDB (set SESSION_DB_URL in env/secrets)
_session_db_url = os.getenv(
    "SESSION_DB_URL",
    f"sqlite:///{_agent_dir}/sessions.db",
)

app = get_fast_api_app(
    agents_dir=_agent_dir,
    session_service_uri=_session_db_url,
    allow_origins=["*"],
    web=True,  # mounts the ADK web UI at /
)

# Bolt on our semantic recall + health endpoints
app.include_router(router)
