"""
Genesis Root Agent — orchestrates Planner, Archivist, Dispatcher, Timekeeper.
Loaded by get_fast_api_app via agent.py.
"""
from __future__ import annotations

import os

from . import retry_patch  # apply 503/429 exponential back-off before any Agent is created

from google.adk.agents import Agent
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.mcp_tool import McpToolset, SseConnectionParams, StreamableHTTPConnectionParams

LINEAR_MCP_URL = "https://mcp.linear.app/mcp"
LINEAR_API_KEY = os.getenv("LINEAR_API_KEY", "")

from .archivist_agent import archivist_agent
from .dispatcher_agent import dispatcher_agent
from .timekeeper_agent import timekeeper_agent
MCP_URL = os.getenv("MCP_TOOLBOX_URL", "http://localhost:5000/mcp")

# ── Planner sub-agent ─────────────────────────────────────────────────────────
# output_schema forces structured JSON output.
# ADK constraint: agents with output_schema cannot use tools or sub-agents.

planner_agent = Agent(
    model="gemini-3-flash-preview",
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
- IMPORTANT: Do NOT use double quotes inside any string values. Use single quotes instead (e.g. 'Payments 2.0' not "Payments 2.0").
""",
)

# ── Root agent ────────────────────────────────────────────────────────────────

root_agent = Agent(
    model="gemini-2.5-pro",
    name="genesis_root",
    description="Genesis Project Architect — turns a brain-dump into a live project.",
    instruction="""
You are Genesis, an AI project architect. Your job is to fully set up a project
from a brain-dump by calling EXACTLY FOUR tools in order — no skipping, no stopping early.
Never write Python code or variable assignments. Call tools directly.

--- STEP 1: Call planner_agent ---
Pass the full brain-dump text.
It returns JSON with: project_name, summary, doc_title, doc_body, tasks, meetings.
Then say something like: "Got it! Planned out [project_name] with [N] tasks and [N] meetings. Setting up the workspace now..."

--- STEP 2: Call archivist_agent ---
MUST call this even if step 1 looks complete. Do not skip.
Pass: "Create a Google Doc titled '[doc_title]' with this body: [doc_body]"
It returns doc_url.
Then say: "Doc's live at [doc_url]. Creating the task board next..."

--- STEP 3: Call dispatcher_agent ---
MUST call this even if steps 1-2 look complete. Do not skip.
Pass: "Create Linear issues for project '[project_name]' with these tasks: [tasks JSON]"
It returns team_url.
Then say: "Task board ready at [team_url]. Scheduling meetings..."

--- STEP 4: Call timekeeper_agent ---
MUST call this even if steps 1-3 look complete. Do not skip.
Pass: "Schedule these meetings. doc_url=[doc_url]. Meetings: [meetings JSON]"
It returns event_urls.
Then say: "All meetings scheduled! Wrapping up..."

--- STEP 5: All four tools done — output this JSON and nothing else ---
{
  "project_name": "...",
  "summary": "...",
  "doc_url": "...",
  "linear_url": "...",
  "event_urls": ["..."],
  "status": "done"
}

If any tool errors, DO NOT roll back — keep whatever was already created.
Output: {"status": "partial", "error": "<reason>", "rolled_back": false}
""",
    tools=[
        AgentTool(agent=planner_agent),
        AgentTool(agent=archivist_agent),
        AgentTool(agent=dispatcher_agent),
        AgentTool(agent=timekeeper_agent),
        McpToolset(
            connection_params=StreamableHTTPConnectionParams(url=MCP_URL),
            tool_filter=["delete_google_doc", "delete_calendar_event"],
        ),
        McpToolset(
            connection_params=StreamableHTTPConnectionParams(
                url=LINEAR_MCP_URL,
                headers={"Authorization": f"Bearer {LINEAR_API_KEY}"},
            ),
            tool_filter=["update_issue"],
        ),
    ],
)
