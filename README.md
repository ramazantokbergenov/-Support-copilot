# Support Copilot

Демо рабочего места оператора поддержки: приём обращений, предварительная AI-классификация, извлечение утверждений, поиск проверенных правил и подготовка ответа на ручную проверку.

Проект не подключён к реальным игровым аккаунтам или логам Grand Mobile. Ответы игрокам автоматически не отправляются. Используйте только synthetic demo data.

## Быстрый запуск: локальный режим

Нужны Python 3.11+, Node.js 20.19+ и npm. Откройте два терминала из корня репозитория; команды ниже сами переходят в `Site/`.

Backend:

```sh
cd Site
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env.backend
```

`.env.backend` предназначен только для backend. Для детерминированного режима оставьте `LLM_API_KEY` и `LLM_MODEL` пустыми. При желании задайте `LLM_API_BASE_URL`, `LLM_API_KEY` и `LLM_MODEL` для OpenAI-compatible provider. Затем экспортируйте значения и запустите API:

```sh
set -a
. ./.env.backend
set +a
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Локальный API не имеет аутентификации. Не открывайте его на сетевом интерфейсе и не используйте для реальных обращений.

Frontend во втором терминале:

```sh
cd Site
cp frontend.env.example .env.local
npm ci
npm run dev -- --host 127.0.0.1
```

Откройте <http://127.0.0.1:5173>. Для локального backend в `Site/.env.local` оставьте `VITE_API_BASE_URL=http://127.0.0.1:8000`. Файл frontend содержит только публичные `VITE_*` настройки; service-role и LLM keys туда не помещаются.

## Supabase mode

Инструкции по локальному и hosted Supabase, Auth, миграциям, секретам и импорту официальных правил находятся в [Site/AI_RAG.md](Site/AI_RAG.md). Frontend configuration описана в [Site/FRONTEND.md](Site/FRONTEND.md). Для Supabase используйте отдельный `.env.supabase` для Edge Function и frontend `.env.local` только для URL и public anon key.

Подготовка локальных демонстрационных обращений и сценарий показа: [Site/DEMO.md](Site/DEMO.md). Seed создаёт шесть идемпотентных synthetic tickets и не добавляет правила или реальные player IDs.

## Проверки

```sh
cd Site
python -m pip install -r requirements-test.txt
python -m unittest discover -s tests -v
npm run typecheck
npm run build
```

Playwright E2E требует установленный Chromium и отдельно запущенные backend/frontend; подробности в [Site/FRONTEND.md](Site/FRONTEND.md).

## Структура

- `Site/app/` — FastAPI, SQLite repository и AI/RAG services.
- `Site/src/` — React + TypeScript operator UI.
- `Site/supabase/` — PostgreSQL migrations и Auth-protected Edge Function.
- `Site/scripts/` — ingestion официальных правил и synthetic demo seed.
- `Site/tests/` — backend unit/API tests и browser integration tests.

Git history не переписывается; demo setup не удаляет и не заменяет существующие branches.