# syntax=docker/dockerfile:1.7

ARG UV_VERSION=0.13.0
ARG JAVA_IMAGE=eclipse-temurin:21-jre-jammy

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv
FROM ${JAVA_IMAGE} AS jre

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app
COPY --from=uv /uv /uvx /bin/

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
RUN useradd --create-home --uid 10001 aa && chown -R aa:aa /app

USER aa

FROM base AS backend

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health').read()"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS tools

USER root

COPY --from=jre /opt/java/openjdk /opt/java/openjdk

ARG TLA_TOOLS_URL=https://github.com/tlaplus/tlaplus/releases/download/v1.7.4/tla2tools.jar
ARG TLA_TOOLS_SHA256=936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88
RUN mkdir -p /opt/tla \
 && python -c "import sys,urllib.request as u;open('/opt/tla/tla2tools.jar','wb').write(u.urlopen(sys.argv[1]).read())" "$TLA_TOOLS_URL" \
 && echo "${TLA_TOOLS_SHA256}  /opt/tla/tla2tools.jar" | sha256sum -c -

FROM base AS worker

COPY --from=tools /opt/java /opt/java
COPY --from=tools /opt/tla /opt/tla

ENV JAVA_HOME=/opt/java/openjdk
ENV PATH="/opt/java/openjdk/bin:/app/.venv/bin:$PATH"
ENV TLA_TOOLS_JAR=/opt/tla/tla2tools.jar
ENV CHECK_TIMEOUT_SECONDS=120
ENV STATE_LIMIT=1000000

CMD ["arq", "app.worker.main.WorkerSettings"]