"""Database layer for arq worker."""

import os
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models import ModelVersion, Verification


def build_database_url() -> str:
    """Build DATABASE_URL from POSTGRES_* environment variables."""
    user = os.getenv("POSTGRES_USER", "agent_analyst")
    password = os.getenv("POSTGRES_PASSWORD", "agent_analyst")
    db = os.getenv("POSTGRES_DB", "agent_analyst")
    port = os.getenv("POSTGRES_PORT", "5432")
    host = os.getenv("POSTGRES_HOST", "localhost")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"


def create_engine_and_sessionmaker() -> tuple[Any, async_sessionmaker[AsyncSession]]:
    """Create async engine and sessionmaker."""
    url = build_database_url()
    engine = create_async_engine(url, pool_pre_ping=True)
    sessionmaker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, sessionmaker


@asynccontextmanager
async def get_session(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> Any:
    """Get a database session."""
    async with sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_verification_model(
    sessionmaker: async_sessionmaker[AsyncSession], verification_id: str
) -> dict[str, Any] | None:
    """Load ModelVersion.document for a verification."""
    async with get_session(sessionmaker) as session:
        result = await session.execute(
            select(Verification, ModelVersion.document)
            .join(ModelVersion, Verification.model_version_id == ModelVersion.id)
            .where(Verification.id == verification_id)
        )
        row = result.first()
        if not row:
            return None
        verification, document = row
        return {
            "verification_id": str(verification.id),
            "model_version_id": str(verification.model_version_id),
            "document": document,
        }


async def save_verification_result(
    sessionmaker: async_sessionmaker[AsyncSession],
    verification_id: str,
    result: dict[str, Any],
) -> None:
    """Save verification result to database."""
    async with get_session(sessionmaker) as session:
        verification = await session.get(Verification, verification_id)
        if not verification:
            return
        verification.status = result.get("status", "ENGINE_ERROR")
        verification.engine = result.get("engine", "TLC")
        verification.engine_version = result.get("engine_version")
        verification.counterexample = result.get("counterexample")
        verification.statistics = result.get("statistics")
        verification.duration_ms = result.get("duration_ms")
        verification.error_detail = result.get("error_detail")
        verification.business_summary = result.get("business_summary", "")


async def get_tlc_version() -> str:
    """Get TLC version by running java -cp tla2tools.jar tlc2.TLC -version."""
    import asyncio
    import os

    tla_jar = os.getenv("TLA_TOOLS_JAR", "/opt/tla/tla2tools.jar")
    try:
        proc = await asyncio.create_subprocess_exec(
            "java",
            "-cp",
            tla_jar,
            "tlc2.TLC",
            "-version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        output = (stdout or stderr).decode()
        for line in output.splitlines():
            if "version" in line.lower() or "tlc" in line.lower():
                return line.strip()
        return "TLC 1.7.4"
    except Exception:
        return "TLC 1.7.4"
