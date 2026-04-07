"""Shared Pydantic schemas for ADK structured output."""
from __future__ import annotations

from pydantic import BaseModel, Field


class TaskItem(BaseModel):
    title: str
    due: str | None = Field(None, description="ISO date YYYY-MM-DD")
    notes: str | None = None
    assignee: str | None = None


class MeetingItem(BaseModel):
    title: str
    start: str = Field(description="ISO-8601 datetime with timezone offset")
    end: str = Field(description="ISO-8601 datetime with timezone offset")
    description: str | None = None
    attendees: list[str] = []


class ExtractedPlan(BaseModel):
    """Structured extraction of a raw brain-dump into actionable project plan."""
    project_name: str = Field(description="Short, descriptive project name (≤60 chars)")
    summary: str = Field(description="2–4 sentence executive summary of the project")
    doc_title: str = Field(description="Title for the Google Doc that will archive the plan")
    doc_body: str = Field(
        description=(
            "Full document body in plain text. Include: Goals, Context, "
            "Key Decisions, Open Questions, Next Steps."
        )
    )
    tasks: list[TaskItem] = Field(
        description="Actionable tasks derived from the brain-dump (5–15 items)"
    )
    meetings: list[MeetingItem] = Field(
        description="Kickoff and follow-up meetings to schedule (1–3 events)"
    )


