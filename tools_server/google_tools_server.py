"""
Lightweight FastAPI micro-server that wraps Google Docs and Calendar APIs.
MCP Toolbox calls this via HTTP; authenticates using Application Default Credentials.

Run:  uv run uvicorn mcp.google_tools_server:app --port 8001
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import google.auth
import google.oauth2.credentials
import google.oauth2.service_account
from google.auth.transport.requests import Request
import googleapiclient.discovery
import googleapiclient.errors

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Genesis Google Tools Server")

DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
]
CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
]


def _personal_creds():
    """Load personal user credentials from ADC file — uses personal Drive quota."""
    adc_path = os.path.expanduser("~/.config/gcloud/application_default_credentials.json")
    try:
        with open(adc_path) as f:
            info = json.load(f)
        creds = google.oauth2.credentials.Credentials(
            token=None,
            refresh_token=info["refresh_token"],
            client_id=info["client_id"],
            client_secret=info["client_secret"],
            token_uri="https://oauth2.googleapis.com/token",
            scopes=DRIVE_SCOPES,
        )
        creds.refresh(Request())
        return creds
    except Exception as e:
        logger.warning("Personal ADC not found, falling back to default: %s", e)
        creds, _ = google.auth.default(scopes=DRIVE_SCOPES)
        return creds


def _sa_creds():
    """Load SA credentials for Calendar."""
    sa_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if sa_path and os.path.exists(sa_path):
        return google.oauth2.service_account.Credentials.from_service_account_file(
            sa_path, scopes=CALENDAR_SCOPES
        )
    creds, _ = google.auth.default(scopes=CALENDAR_SCOPES)
    return creds


def _docs_service():
    return googleapiclient.discovery.build("docs", "v1", credentials=_personal_creds())


def _drive_service():
    return googleapiclient.discovery.build("drive", "v3", credentials=_personal_creds())


def _calendar_service():
    return googleapiclient.discovery.build("calendar", "v3", credentials=_sa_creds())


# ── Docs ──────────────────────────────────────────────────────────────────────

class CreateDocRequest(BaseModel):
    title: str
    body: str


@app.post("/docs/create")
async def create_doc(request: Request) -> dict:
    try:
        raw = await request.body()
        logger.info("create_doc raw body: %s", raw[:200])
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # MCP Toolbox doesn't JSON-escape template values; re-encode safely
            import re
            text = raw.decode("utf-8", errors="replace")
            title = re.search(r'"title"\s*:\s*"(.*?)",\s*"body"', text, re.DOTALL)
            body = re.search(r'"body"\s*:\s*"(.*?)"\s*\}?\s*$', text, re.DOTALL)
            data = {
                "title": title.group(1) if title else "Untitled",
                "body": body.group(1).replace("\\n", "\n") if body else "",
            }
        req = CreateDocRequest(**data)
        drive = _drive_service()
        folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
        file_meta: dict = {"name": req.title, "mimeType": "application/vnd.google-apps.document"}
        if folder_id:
            file_meta["parents"] = [folder_id]
        doc_file = drive.files().create(body=file_meta, fields="id").execute()
        doc_id = doc_file["id"]
        url = f"https://docs.google.com/document/d/{doc_id}/edit"
        docs = _docs_service()

        docs.documents().batchUpdate(
            documentId=doc_id,
            body={
                "requests": [
                    {"insertText": {"location": {"index": 1}, "text": req.body}}
                ]
            },
        ).execute()
        return {"doc_id": doc_id, "url": url}
    except googleapiclient.errors.HttpError as e:
        logger.error("Google Docs API error: %s", e)
        return {"error": f"Google Docs API error: {e}", "doc_id": None, "url": None}
    except Exception as e:
        logger.exception("Unexpected error in create_doc")
        return {"error": str(e), "doc_id": None, "url": None}


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
    try:
        raw = await request.body()
        logger.info("create_event raw body: %s", raw)
        data = await request.json()
        req = CreateEventRequest(**data)
        svc = _calendar_service()
        body: dict[str, Any] = {
            "summary": req.title,
            "start": {"dateTime": req.start, "timeZone": "UTC"},
            "end": {"dateTime": req.end, "timeZone": "UTC"},
        }
        if req.description:
            body["description"] = req.description
        # Service accounts cannot invite attendees without Domain-Wide Delegation;
        # store them in the description instead.
        attendees = req.attendees_list()
        if attendees:
            attendees_str = ", ".join(attendees)
            body["description"] = (body.get("description") or "") + f"\n\nAttendees: {attendees_str}"

        logger.info("Inserting calendar event: %s", body)
        calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")
        event = svc.events().insert(calendarId=calendar_id, body=body).execute()
        return {"event_id": event["id"], "url": event.get("htmlLink", "")}
    except googleapiclient.errors.HttpError as e:
        logger.error("Google Calendar API error: %s", e)
        return {"error": f"Google Calendar API error: {e}"}
    except Exception as e:
        logger.exception("Unexpected error in create_event")
        return {"error": str(e)}


class DeleteEventRequest(BaseModel):
    event_id: str


@app.post("/calendar/delete")
async def delete_event(request: Request) -> dict:
    req = DeleteEventRequest(**json.loads(await request.body()))
    calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")
    _calendar_service().events().delete(
        calendarId=calendar_id, eventId=req.event_id
    ).execute()
    return {"deleted": req.event_id}
 