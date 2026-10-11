# Agent Analyst

Веб-приложение для проверки постановки на разработку по логической модели.
Пользователь описывает поведение модуля текстом, агент на LLM строит формальную
модель состояний и переходов, детерминированный движок перебирает состояния и
возвращает контрпример, агент объясняет его на языке исходных требований.

## Стек

| Слой | Технология |
|---|---|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS 4, TanStack Query |
| Backend | Python 3.12, FastAPI, Pydantic 2, SQLAlchemy 2 (async), Alembic |
| Фоновые задачи | arq + Redis 7 |
| БД | PostgreSQL 16 |
| Model Checker | TLC из TLA+ Tools 1.7.4, Java 21 (в образе воркера) |
| Артефакты | S3-совместимое хранилище (MinIO, профиль `storage`) |
| Управление зависимостями | uv |

## Быстрый старт

Нужны Docker, Node.js 22 и uv.

```bash
cp .env.example .env
docker compose up -d postgres redis              # PostgreSQL и Redis
cd backend && uv sync                     # зависимости
cd backend && uv run alembic upgrade head  # миграции
```

Дальше в трёх терминалах:

```bash
cd backend  && uv run uvicorn app.main:app --reload --port 8000
cd backend  && uv run arq app.worker.WorkerSettings
cd frontend && npm run dev
```

Проверить, что всё живо: <http://localhost:5173> и <http://localhost:8000/health>.

## Полный стек в контейнерах

```bash
docker compose up -d --build
```

Фронтенд будет на <http://localhost:8080>, API на <http://localhost:8000>.
Объектное хранилище поднимается отдельно: `docker compose --profile storage up -d`.

## Структура

```
backend/     FastAPI, миграции Alembic, Dockerfile с таргетами api и worker
frontend/    React SPA, Dockerfile с таргетами dev, build и prod
```

## Команды

Обёртки над командами нет, всё вызывается напрямую.

```bash
cd backend  && uv sync
cd backend  && uv run alembic upgrade head
cd backend  && uv run alembic revision -m "добавить колонку"
cd backend  && uv run pytest

cd backend  && uv run ruff check .
cd backend  && uv run ruff format --check .
cd backend  && uv run mypy app alembic
cd backend  && uv run ruff format . && uv run ruff check --fix .

cd frontend && npm run lint
cd frontend && npm run typecheck
cd frontend && npx prettier --check .
cd frontend && npx prettier --write .
cd frontend && npm run build

docker compose exec postgres psql -U agent_analyst -d agent_analyst
docker compose logs -f backend
```
