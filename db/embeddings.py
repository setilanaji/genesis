"""Embedding write-path and semantic search via AlloyDB pgvector."""
from __future__ import annotations

import asyncio
import os

from sqlalchemy import text

from .repo import db_session


# ── Chunking ───────────────────────────────────────────────────────────────────

def _chunk_text(text_: str, chunk_size: int = 400, overlap: int = 50) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(text_):
        chunks.append(text_[start : start + chunk_size])
        start += chunk_size - overlap
    return chunks


# ── Embedding via Vertex AI (sync — run in thread pool) ───────────────────────

def _embed_chunks_sync(chunks: list[str]) -> list[list[float]]:
    import vertexai
    from vertexai.language_models import TextEmbeddingModel

    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    vertexai.init(project=project, location=location)

    model = TextEmbeddingModel.from_pretrained("text-embedding-004")
    all_embeddings: list[list[float]] = []
    for i in range(0, len(chunks), 250):  # API batch limit
        results = model.get_embeddings(chunks[i : i + 250])
        all_embeddings.extend([r.values for r in results])
    return all_embeddings


async def _embed_chunks(chunks: list[str]) -> list[list[float]]:
    """Run the blocking Vertex AI call in a thread pool to avoid blocking the event loop."""
    return await asyncio.to_thread(_embed_chunks_sync, chunks)


# ── Vector formatting for pgvector ────────────────────────────────────────────

def _to_pgvector(vec: list[float]) -> str:
    """Format a float list as pgvector literal: '[0.1,0.2,...]'"""
    return "[" + ",".join(str(v) for v in vec) + "]"


# ── Public API ─────────────────────────────────────────────────────────────────

async def store_embeddings(project_id: str, raw_text: str) -> None:
    """Chunk raw brain-dump, embed, and store in AlloyDB."""
    chunks = _chunk_text(raw_text)
    vectors = await _embed_chunks(chunks)

    async with db_session() as s:
        for chunk, vec in zip(chunks, vectors):
            await s.execute(
                text(
                    "INSERT INTO brain_dump_embeddings (project_id, chunk, embedding) "
                    "VALUES (:pid, :chunk, :vec::vector)"
                ),
                {"pid": project_id, "chunk": chunk, "vec": _to_pgvector(vec)},
            )


async def semantic_recall(project_id: str, query: str, top_k: int = 5) -> list[str]:
    """Return the top-k most relevant chunks from the original brain-dump."""
    [query_vec] = await _embed_chunks([query])

    async with db_session() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT chunk "
                    "FROM brain_dump_embeddings "
                    "WHERE project_id = :pid "
                    "ORDER BY embedding <=> :vec::vector "
                    "LIMIT :k"
                ),
                {"pid": project_id, "vec": _to_pgvector(query_vec), "k": top_k},
            )
        ).fetchall()
    return [r[0] for r in rows]
