"""
Lightweight FastAPI micro-server that wraps Google Docs and Calendar APIs.
MCP Toolbox calls this via HTTP; authenticates using Application Default Credentials.

Run:  uv run uvicorn mcp.google_tools_server:app --port 8001
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, Request
from pydantic import BaseModel
import google.auth
import googleapiclient.discovery

app = FastAPI(title="Genesis Google Tools Server")

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive.file",
]


def _creds():
    creds, _ = google.auth.default(scopes=SCOPES)
    return creds


def _docs_service():
    return googleapiclient.discovery.build("docs", "v1", credentials=_creds())


def _drive_service():
    return googleapiclient.discovery.build("drive", "v3", credentials=_creds())


def _calendar_service():
    return googleapiclient.discovery.build("calendar", "v3", credentials=_creds())


# ── Docs ──────────────────────────────────────────────────────────────────────

class CreateDocRequest(BaseModel):
    title: str
    body: str


@app.post("/docs/create")
async def create_doc(request: Request) -> dict:
    req = CreateDocRequest(**json.loads(await request.body()))
    docs = _docs_service()
    doc = docs.documents().create(body={"title": req.title}).execute()
    doc_id = doc["documentId"]
    url = f"https://docs.google.com/document/d/{doc_id}/edit"

    docs.documents().batchUpdate(
        documentId=doc_id,
        body={
            "requests": [
                {"insertText": {"location": {"index": 1}, "text": req.body}}
            ]
        },
    ).execute()
    return {"doc_id": doc_id, "url": url}


class DeleteDocRequest(BaseModel):
    doc_id: str


@app.post("/docs/delete")
async def delete_doc(request: Request) -> dict:
    req = DeleteDocRequest(**json.loads(await request.body()))
    _drive_service().files().delete(fileId=req.doc_id).execute()
    return {"deleted": req.doc_id}


# ── Calendar ──────────────────────────────────────────────────────────────────

class CreateEventRequest(BaseModel):
    title: str
    start: str
    end: str
    description: str | None = None
    attendees: str | list[str] = ""

    def attendees_list(self) -> list[str]:
        if isinstance(self.attendees, list):
            return self.attendees
        return [e.strip() for e in self.attendees.split(",") if e.strip()]


@app.post("/calendar/create")
async def create_event(request: Request) -> dict:
    req = CreateEventRequest(**json.loads(await request.body()))
    svc = _calendar_service()
    body: dict[str, Any] = {
        "summary": req.title,
        "start": {"dateTime": req.start},
        "end": {"dateTime": req.end},
    }
    if req.description:
        body["description"] = req.description
    attendees = req.attendees_list()
    if attendees:
        body["attendees"] = [{"email": e} for e in attendees]

    event = svc.events().insert(calendarId="primary", body=body).execute()
    return {"event_id": event["id"], "url": event.get("htmlLink", "")}


class DeleteEventRequest(BaseModel):
    event_id: str


@app.post("/calendar/delete")
async def delete_event(request: Request) -> dict:
    req = DeleteEventRequest(**json.loads(await request.body()))
    _calendar_service().events().delete(
        calendarId="primary", eventId=req.event_id
    ).execute()
    return {"deleted": req.event_id}
 