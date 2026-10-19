from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import analysis, auth, profile, projects
from app.db import dispose_engine, open_database
from app.errors import install_exception_handlers
from app.queue import close_queue, open_queue

API_PREFIX = "/api"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    """Поднять пул БД и брокер, оба закрыть при остановке процесса."""
    open_database()
    await open_queue()
    yield
    await close_queue()
    await dispose_engine()


app = FastAPI(
    title="Agent Analyst API",
    version="0.1.0",
    description="Трек agent analyst: интерпретация требований и объяснение контрпримера.",
    docs_url=f"{API_PREFIX}/docs",
    openapi_url=f"{API_PREFIX}/openapi.json",
    lifespan=lifespan,
)

install_exception_handlers(app)

for router in (auth.router, projects.router, analysis.router, profile.router):
    app.include_router(router, prefix=API_PREFIX)


@app.get("/health", tags=["service"])
async def health() -> dict[str, str]:
    """Проверка живости: отвечает — значит процесс поднялся и uvicorn слушает."""
    return {"status": "ok"}
