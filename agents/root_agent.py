"""
Genesis Root Agent — orchestrates Planner, Archivist, Dispatcher, Timekeeper.
Loaded by get_fast_api_app via agent.py.
"""
from __future__ import annotations

import os

from google.adk.agents import Agent
from google.adk.tools.mcp_tool import McpToolset, SseConnectionParams

LINEAR_MCP_URL = "https://mcp.linear.app/sse"
LINEAR_API_KEY = os.getenv("LINEAR_API_KEY", "")

from .archivist_agent import archivist_agent
from .dispatcher_agent import dispatcher_agent
from .timekeeper_agent import timekeeper_agent
from .schemas import ExtractedPlan

MCP_URL = os.getenv("MCP_TOOLBOX_URL", "http://localhost:5000/mcp/sse")

# ── Planner sub-agent ─────────────────────────────────────────────────────────
# Separate agent with output_schema so structured extraction works.
# ADK constraint: agents with output_schema cannot use tools or sub-agents.

planner_agent = Agent(
    model="gemini-2.5-flash",
    name="planner_agent",
    description="Extracts a structured ExtractedPlan from a raw brain-dump.",
    instruction="""
You are a project planning expert. Given a raw brain-dump, extract a structured
project plan and return it as a single JSON object — no markdown, no code fences,
no commentary, just raw JSON.

Required JSON shape:
{
  "project_name": "Short descriptive name (≤60 chars)",
  "summary": "2–4 sentence executive summary",
  "doc_title": "Title for the archive Google Doc",
  "doc_body": "Full document body with sections: Goals, Context, Key Decisions, Open Questions, Next Steps",
  "tasks": [
    {"title": "...", "due": "YYYY-MM-DD or null", "notes": "... or null", "assignee": "... or null"}
  ],
  "meetings": [
    {"title": "...", "start": "ISO-8601+08:00", "end": "ISO-8601+08:00", "description": "... or null", "attendees": ["email@..."]}
  ]
}

Rules:
- Produce 5–15 tasks and 1–3 meetings.
- Meeting datetimes must be within the next 2 weeks, timezone offset +08:00 (APAC).
- Output ONLY the JSON object.
""",
)

# ── Root agent ────────────────────────────────────────────────────────────────

root_agent = Agent(
    model="gemini-2.5-flash",
    name="genesis_root",
    description="Genesis Project Architect — turns a brain-dump into a live project.",
    instruction="""
You are the Genesis Project Architect. Transform a raw brain-dump into a
fully set-up project workspace by orchestrating your sub-agents in order.

## Workflow — execute IN ORDER, no skipping:

### Step 1 — Plan
Delegate to `planner_agent` with the full brain-dump text.
It returns a structured ExtractedPlan JSON. Store all fields for the next steps.

### Step 2 — Archive
Delegate to `archivist_agent`:
  "Create a Google Doc titled '<doc_title>' with this body: <doc_body>"
Capture doc_id and doc_url from its JSON response.

### Step 3 — Dispatch
Delegate to `dispatcher_agent`:
  "Create Linear issues for project '<project_name>' with these tasks: <tasks JSON>"
Capture issue_ids and team_url.

### Step 4 — Schedule
Delegate to `timekeeper_agent`:
  "Schedule these meetings. Add doc_url=<doc_url> to each event description: <meetings JSON>"
Capture event_ids and event_urls.

### Step 5 — Return dashboard
Respond with ONLY this JSON (no markdown fences, no preamble):
{
  "project_name": "...",
  "summary": "...",
  "doc_url": "...",
  "linear_url": "...",
  "event_urls": ["..."],
  "status": "done"
}

## Saga rollback on any failure
If any step errors, compensate in REVERSE order:
  - Delete each created event via `delete_calendar_event`
  - Cancel each created Linear issue via `update_issue` setting status to "Cancelled" (using issue_ids)
  - Delete doc via `delete_google_doc`
  (skip steps that never succeeded)
Then respond:
  {"status": "failed", "error": "<reason>", "rolled_back": true}

Never leave partial artifacts in the user's workspace.
""",
    sub_agents=[planner_agent, archivist_agent, dispatcher_agent, timekeeper_agent],
    tools=[
        McpToolset(
            connection_params=SseConnectionParams(url=MCP_URL),
            tool_filter=["delete_google_doc", "delete_calendar_event"],
        ),
        McpToolset(
            connection_params=SseConnectionParams(
                url=LINEAR_MCP_URL,
                headers={"Authorization": f"Bearer {LINEAR_API_KEY}"},
            ),
            tool_filter=["update_issue"],
        ),
    ],
)
