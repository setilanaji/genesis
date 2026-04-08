"""
Archivist sub-agent — creates the Google Doc from the ExtractedPlan.
"""
from __future__ import annotations

import os

from google.adk.agents import Agent
from google.adk.tools.mcp_tool import McpToolset, SseConnectionParams

MCP_URL = os.getenv("MCP_TOOLBOX_URL", "http://localhost:5000/mcp/sse")

archivist_agent = Agent(
    model="gemini-2.5-flash",
    name="archivist_agent",
    description=(
        "Creates a structured Google Doc from an ExtractedPlan. "
        "Returns doc_id and doc_url."
    ),
    instruction="""
You are the Archivist. Your sole responsibility is to create a Google Doc that
archives the project plan.

You will receive a JSON object with at minimum these fields:
  - doc_title: the document title
  - doc_body: the full document content

Call the `create_google_doc` tool with those values.

Return ONLY a JSON object:
{
  "doc_id": "<returned doc_id>",
  "doc_url": "<returned url>"
}

Do not add commentary. Do not call any other tool.
""",
    tools=[
        McpToolset(
            connection_params=SseConnectionParams(url=MCP_URL),
            tool_filter=["create_google_doc"],
        )
    ],
)
