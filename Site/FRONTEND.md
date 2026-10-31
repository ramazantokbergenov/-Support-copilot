# Frontend Support Copilot

React + TypeScript frontend находится в `src/` и использует React Router, Lucide и Supabase Auth. Компоненты, раскладка и CSS сохраняют исходный интерфейс; ticket data, статусы, analysis, rules, notes и drafts загружаются из Backend, а не из browser storage.

Для запуска требуются Node.js 20.19+ и npm. Сначала выберите один backend режим и скопируйте `frontend.env.example` в `.env.local`.

Local FastAPI:

```sh
cp frontend.env.example .env.local
npm ci
npm run dev
```

Задайте `VITE_API_BASE_URL=http://127.0.0.1:8000` и запустите FastAPI отдельно из `Site/`. Локальный API не имеет Auth и предназначен для localhost.

Supabase Edge:

```env
VITE_SUPABASE_URL=https://<project-ref>.supabase.co
VITE_SUPABASE_ANON_KEY=<public-anon-key>
```

Удалите или оставьте пустым `VITE_API_BASE_URL`: клиент автоматически использует `/functions/v1/api` и требует operator login. В frontend допускается только публичный anon key. Никогда не задавайте `SUPABASE_SERVICE_ROLE_KEY` или `LLM_API_KEY` в `VITE_*` переменных.

Проверки:

```sh
npm run typecheck
npm run build
npx playwright install chromium
```

Для E2E должны быть запущены Vite/FastAPI на портах `5173`/`8000`. Из `Site/` загрузите operator credentials только в shell процесса теста и запустите:

```sh
set -a
. ./.env.backend
set +a
npm run test:e2e
```

Тесты используют установленный Chromium. В Linux может потребоваться установка системных библиотек командой `npx playwright install-deps chromium` из окружения с разрешённым управлением пакетами.

UI поиска/аналитики вне списка обращений агрегирует последние 100 записей; точный общий count очереди приходит от Backend. Отдельный endpoint управления командой/назначениями не реализован. Автоматической отправки ответа игроку нет.
