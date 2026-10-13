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

## Два запуска фронта

Фронт работает в двух режимах. Выбор — не настройка, а команда запуска.

| | Команда | Адрес | Откуда данные |
|---|---|---|---|
| Моки | `npm run dev:mock` | <http://localhost:5173> | MSW в памяти, контрактные ответы |
| Реальный API | `docker compose up -d --build --wait` | <http://localhost:8080> | бэкенд, nginx проксирует `/api` |

### Моки

```bash
cd frontend && npm run dev:mock   # демо-доступы: analyst@example.com / demo12345
```

MSW перехватывает запросы в браузере, бэкенд не нужен. Ответы берутся из
контракта `docs/API_CONTRACT.md`, поэтому фронт можно дописывать, пока API пишут.

Проверить реакцию на `401` можно вручную: удалите cookie `session` в devtools —
следующий запрос вернёт `401`, фронт покажет тост и вернёт на `/login` с сохранением
адреса.

### Реальный API

```bash
docker compose up -d --build --wait   # ждёт healthcheck API и фронта
```

Поднимает postgres, redis, backend, worker и продакшен-фронт в nginx. Фронт
собран без моков и ходит в бэкенд по `/api` — тот же origin, CORS не нужен.

Демо-пользователей в базе нет: заведите аккаунт формой регистрации на `/login`
или засейте пользователя на стороне backend. Требуется `cp .env.example .env`
перед первым запуском.

```bash
docker compose ps                    # статус и healthcheck каждого сервиса
docker compose logs -f backend
```

## Бэкенд локально

Когда нужен перезапуск без пересборки контейнеров — `--reload` в uv и arq, фронт
при этом поднимается через `npm run dev` и проксирует `/api` на `:8000`.

```bash
cp .env.example .env
docker compose up -d postgres redis

cd backend && uv sync
cd backend && uv run alembic upgrade head

cd backend  && uv run uvicorn app.main:app --reload --port 8000
cd backend  && uv run arq app.worker.WorkerSettings
cd frontend && npm run dev
```

Проверить, что всё живо: <http://localhost:5173> и <http://localhost:8000/health>.

## Оформление

Тема по умолчанию системная (`prefers-color-scheme`). Переключается в шапке или
сегментом на странице «Профиль» (`/profile`), выбор сохраняется в `localStorage`.
Там же — сводка по проектам, версиям требований и прогонам.

Объектное хранилище для артефактов прогонов подключается отдельно:
`docker compose --profile storage up -d`.

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

cd frontend && npm run dev        # запросы идут в настоящий backend
cd frontend && npm run dev:mock   # мок-API в памяти, backend не нужен
cd frontend && npm run lint
cd frontend && npm run typecheck
cd frontend && npx prettier --check .
cd frontend && npx prettier --write .
cd frontend && npm run build

docker compose exec postgres psql -U agent_analyst -d agent_analyst
docker compose logs -f backend
```
