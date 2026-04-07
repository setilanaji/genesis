"""
Lightweight FastAPI micro-server that wraps Google Docs and Calendar APIs.
MCP Toolbox calls this via HTTP; authenticates using Application Default Credentials.

Run:  uv run uvicorn mcp.google_tools_server:app --port 8001
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI
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
def create_doc(req: CreateDocRequest) -> dict:
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
def delete_doc(req: DeleteDocRequest) -> dict:
    _drive_service().files().delete(fileId=req.doc_id).execute()
    return {"deleted": req.doc_id}


# ── Calendar ──────────────────────────────────────────────────────────────────

class CreateEventRequest(BaseModel):
    title: str
    start: str
    end: str
    description: str | None = None
    attendees: list[str] = []


@app.post("/calendar/create")
def create_event(req: CreateEventRequest) -> dict:
    svc = _calendar_service()
    body: dict[str, Any] = {
        "summary": req.title,
        "start": {"dateTime": req.start},
        "end": {"dateTime": req.end},
    }
    if req.description:
        body["description"] = req.description
    if req.attendees:
        body["attendees"] = [{"email": e} for e in req.attendees]

    event = svc.events().insert(calendarId="primary", body=body).execute()
    return {"event_id": event["id"], "url": event.get("htmlLink", "")}


class DeleteEventRequest(BaseModel):
    event_id: str


@app.post("/calendar/delete")
def delete_event(req: DeleteEventRequest) -> dict:
    _calendar_service().events().delete(
        calendarId="primary", eventId=req.event_id
    ).execute()
    return {"deleted": req.event_id}
