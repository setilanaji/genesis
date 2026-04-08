"""
Dispatcher sub-agent — creates a Linear issue board from the ExtractedPlan.
Connects directly to Linear's hosted MCP SSE server (no local process needed).
"""
from __future__ import annotations

import os

from google.adk.agents import Agent
from google.adk.tools.mcp_tool import McpToolset, StreamableHTTPConnectionParams

LINEAR_MCP_URL = "https://mcp.linear.app/mcp"
LINEAR_API_KEY = os.getenv("LINEAR_API_KEY", "")
LINEAR_TEAM_ID = os.getenv("LINEAR_TEAM_ID", "")

dispatcher_agent = Agent(
    model="gemini-3-flash-preview",
    name="dispatcher_agent",
    description=(
        "Creates Linear issues from an ExtractedPlan. "
        "Returns issue_ids and a Linear team URL."
    ),
    instruction="""
You are the Dispatcher. Create Linear issues for each task in the project plan.

You will receive:
  - project_name: name of the project
  - tasks: array of { title, due?, notes?, assignee? }

For EACH task, call `create_issue` with:
  - title: task.title
  - teamId: """ + LINEAR_TEAM_ID + """
  - description: task.notes (if present)
  - dueDate: task.due (if present, format YYYY-MM-DD)

After all issues are created, return ONLY this JSON:
{
  "issue_ids": ["<id1>", "<id2>", ...],
  "team_url": "https://linear.app/team/""" + LINEAR_TEAM_ID + """/issues"
}

Do not add commentary. Do not call any other tool.
""",
    tools=[
        McpToolset(
            connection_params=StreamableHTTPConnectionParams(
                url=LINEAR_MCP_URL,
                headers={"Authorization": f"Bearer {LINEAR_API_KEY}"},
            ),
            tool_filter=["create_issue", "search_issues"],
        )
    ],
)
