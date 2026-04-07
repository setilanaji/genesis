"""
Extra routes mounted on top of the ADK app.
Only semantic recall and health — everything else is handled by the ADK UI.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import semantic_recall, store_embeddings

router = APIRouter(prefix="/api")


class AskRequest(BaseModel):
    brain_dump: str | None = None   # provide on first call to seed embeddings
    question: str
    top_k: int = 5


@router.post("/ask/{session_id}")
async def ask(session_id: str, req: AskRequest) -> dict:
    """
    Semantic recall against the original brain-dump for a given ADK session.

    First call: pass brain_dump to seed the pgvector embeddings.
    Subsequent calls: just pass question — embeddings already stored.
    """
    if req.brain_dump:
        await store_embeddings(session_id, req.brain_dump)

    chunks = await semantic_recall(session_id, req.question, top_k=req.top_k)
    if not chunks:
        raise HTTPException(
            status_code=404,
            detail="No embeddings found for this session. Pass brain_dump on the first call.",
        )
    return {"question": req.question, "context_chunks": chunks}


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/ready")
def ready() -> dict:
    return {"status": "ready"}
