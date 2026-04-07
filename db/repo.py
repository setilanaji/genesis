"""AlloyDB repository — async SQLAlchemy wrapper."""
from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ── Connection ─────────────────────────────────────────────────────────────────

def _build_url() -> str:
    """
    Prefer the AlloyDB Python Connector URL when running on Cloud Run.
    Fall back to a plain asyncpg DSN for local dev (via AlloyDB Auth Proxy).
    """
    instance_uri = os.getenv("ALLOYDB_INSTANCE_URI")  # projects/P/locations/L/clusters/C/instances/I
    if instance_uri:
        # Cloud Run path — uses google-cloud-alloydb-connector
        return "postgresql+asyncpg://unused"            # connector replaces the DSN
    # Local dev path (Auth Proxy listens on 127.0.0.1:5432 by default)
    host = os.getenv("DB_HOST", "127.0.0.1")
    port = os.getenv("DB_PORT", "5432")
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "")
    name = os.getenv("DB_NAME", "genesis")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"


def _make_engine():
    instance_uri = os.getenv("ALLOYDB_INSTANCE_URI")
    if instance_uri:
        from google.cloud.alloydb.connector import AsyncConnector, IPTypes
        import asyncpg

        connector = AsyncConnector()

        async def _getconn():
            return await connector.connect(
                instance_uri,
                "asyncpg",
                user=os.environ["DB_USER"],
                password=os.environ["DB_PASSWORD"],
                db=os.getenv("DB_NAME", "genesis"),
                ip_type=IPTypes.PRIVATE,
            )

        return create_async_engine(
            "postgresql+asyncpg://",
            async_creator=_getconn,
            pool_size=5,
            max_overflow=2,
        )

    return create_async_engine(_build_url(), pool_size=5, max_overflow=2, echo=False)


_engine = None
_session_factory: async_sessionmaker | None = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = _make_engine()
    return _engine


def get_session_factory() -> async_sessionmaker:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


@asynccontextmanager
async def db_session() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        async with session.begin():
            yield session


# ── Projects ───────────────────────────────────────────────────────────────────

async def create_project(name: str, raw_input: str) -> str:
    project_id = str(uuid.uuid4())
    async with db_session() as s:
        await s.execute(
            text(
                "INSERT INTO projects (id, name, raw_input, status) "
                "VALUES (:id, :name, :raw, 'running')"
            ),
            {"id": project_id, "name": name, "raw": raw_input},
        )
    return project_id


async def update_project_status(project_id: str, status: str) -> None:
    async with db_session() as s:
        await s.execute(
            text("UPDATE projects SET status=:s WHERE id=:id"),
            {"s": status, "id": project_id},
        )


async def get_project(project_id: str) -> dict | None:
    async with db_session() as s:
        row = (
            await s.execute(
                text("SELECT id, name, raw_input, status, created_at FROM projects WHERE id=:id"),
                {"id": project_id},
            )
        ).mappings().first()
    return dict(row) if row else None


# ── Artifacts ──────────────────────────────────────────────────────────────────

async def upsert_artifact(project_id: str, tool: str, external_id: str, url: str) -> None:
    async with db_session() as s:
        await s.execute(
            text(
                "INSERT INTO tool_artifacts (id, project_id, tool, external_id, url) "
                "VALUES (uuid_generate_v4(), :pid, :tool, :eid, :url)"
            ),
            {"pid": project_id, "tool": tool, "eid": external_id, "url": url},
        )


async def get_artifacts(project_id: str) -> list[dict]:
    async with db_session() as s:
        rows = (
            await s.execute(
                text("SELECT tool, external_id, url, created_at FROM tool_artifacts WHERE project_id=:pid"),
                {"pid": project_id},
            )
        ).mappings().all()
    return [dict(r) for r in rows]


# ── Workflow steps ─────────────────────────────────────────────────────────────

async def log_step(project_id: str, step: str, status: str, error: str | None = None) -> None:
    async with db_session() as s:
        await s.execute(
            text(
                "INSERT INTO workflow_steps (project_id, step, status, error) "
                "VALUES (:pid, :step, :status, :error)"
            ),
            {"pid": project_id, "step": step, "status": status, "error": error},
        )


async def get_steps(project_id: str) -> list[dict]:
    async with db_session() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT step, status, error, ts FROM workflow_steps "
                    "WHERE project_id=:pid ORDER BY id"
                ),
                {"pid": project_id},
            )
        ).mappings().all()
    return [dict(r) for r in rows]
