"""
Dispatcher sub-agent — creates a Linear issue board from the ExtractedPlan.
Connects directly to Linear's hosted MCP SSE server (no local process needed).
"""
from __future__ import annotations

import os

from google.adk.agents import Agent
from google.adk.tools.mcp_tool import McpToolset, SseConnectionParams

LINEAR_MCP_URL = "https://mcp.linear.app/sse"
LINEAR_API_KEY = os.getenv("LINEAR_API_KEY", "")
LINEAR_TEAM_ID = os.getenv("LINEAR_TEAM_ID", "")

dispatcher_agent = Agent(
    model="gemini-2.0-flash-001",
    name="dispatcher_agent",
    description=(
        "Creates a Linear project with issues from an ExtractedPlan. "
        "Returns issue_ids and a Linear team URL."
    ),
    instruction="""
You are the Dispatcher. Your sole responsibility is to create Linear issues
that track the project's action items so the whole team can see and action them.

You will receive a JSON object containing:
  - project_name: used as a label prefix for issues
  - tasks: array of { title, due?, notes?, assignee? }

For EACH task, call `create_issue` with:
  - title: task.title
  - teamId: """ + LINEAR_TEAM_ID + """
  - description: task.notes (if present)
  - dueDate: task.due (if present, ISO date YYYY-MM-DD)
  - assigneeId: look up task.assignee email via search if present

After all issues are created, return ONLY a JSON object:
{
  "issue_ids": ["<id1>", "<id2>", ...],
  "team_url": "https://linear.app/team/<team_id>/issues"
}

Do not add commentary. Do not call any other tool.
""",
    tools=[
        McpToolset(
            connection_params=SseConnectionParams(
                url=LINEAR_MCP_URL,
                headers={"Authorization": f"Bearer {LINEAR_API_KEY}"},
            ),
            tool_filter=["create_issue", "search_issues"],
        )
    ],
)
