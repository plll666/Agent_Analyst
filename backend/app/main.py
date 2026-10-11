from fastapi import FastAPI

app = FastAPI(
    title="Agent Analyst API",
    version="0.1.0",
    description="Трек agent analyst: интерпретация требований и объяснение контрпримера.",
)


@app.get("/health", tags=["service"])
async def health() -> dict[str, str]:
    """Проверка живости: отвечает — значит процесс поднялся и uvicorn слушает."""
    return {"status": "ok"}
