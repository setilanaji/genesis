"""
Timekeeper sub-agent — schedules Google Calendar events from the ExtractedPlan.
"""
from __future__ import annotations

import os

from google.adk.agents import Agent
from google.adk.tools.mcp_tool import McpToolset, SseConnectionParams

MCP_URL = os.getenv("MCP_TOOLBOX_URL", "http://localhost:5000/sse")

timekeeper_agent = Agent(
    model="gemini-2.0-flash-001",
    name="timekeeper_agent",
    description=(
        "Schedules Google Calendar events from an ExtractedPlan. "
        "Returns lists of event_ids and event_urls."
    ),
    instruction="""
You are the Timekeeper. Your sole responsibility is to create Google Calendar
events for each meeting in the project plan.

You will receive a JSON object containing:
  - meetings: array of { title, start, end, description?, attendees? }
  - doc_url: link to the Google Doc (include in each event description)

For EACH meeting, call `create_calendar_event` once. Append the doc_url to
the event description so attendees have context.

After all events are created, return ONLY a JSON object:
{
  "event_ids": ["<id1>", "<id2>", ...],
  "event_urls": ["<url1>", "<url2>", ...]
}

Do not add commentary. Do not call any other tool.
""",
    tools=[
        McpToolset(
            connection_params=SseConnectionParams(url=MCP_URL),
            tool_filter=["create_calendar_event"],
        )
    ],
)
