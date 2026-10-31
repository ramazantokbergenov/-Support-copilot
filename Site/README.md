# ZHS Support Copilot backend

Локальный FastAPI backend поддерживает структурированный AI-анализ, а Supabase foundation предоставляет защищённый Edge API и pgvector retrieval. Ни один режим не отправляет ответы игрокам автоматически и не подключён к игровым логам Grand Mobile.

Подробные инструкции по AI provider, Supabase, strict analysis schema и импорту официальных правил: [AI_RAG.md](AI_RAG.md).

## Требования и запуск

- Python 3.11+

Из папки `Site/` в Linux/macOS shell:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

По умолчанию SQLite-файл `support_copilot.db` создаётся в текущей папке. Для другого расположения задайте переменную `SUPPORT_COPILOT_DB` до запуска. Сервер привязан к localhost; перед сетевым или production-развёртыванием необходимы аутентификация, авторизация и защищённое хранилище.

- API: <http://127.0.0.1:8000>
- Swagger UI: <http://127.0.0.1:8000/docs>
- OpenAPI JSON: <http://127.0.0.1:8000/openapi.json>

Проверка тестов:

```sh
python -m pip install -r requirements-test.txt
python -m unittest discover -s tests -v
```

## API contract

Все ответы API — JSON, кроме скачивания вложений. Ошибки валидации имеют формат `{"error":{"code":"validation_error","message":"Request validation failed","details":[...]}}`; ошибки HTTP для отсутствующего ресурса — 404. При превышении лимита вложений API возвращает 413.

### Создание обращения

`POST /tickets` — `multipart/form-data`:

| Поле | Тип | Обязательное | Ограничения |
|---|---|---:|---|
| `player_id` | string | да | 1–128 символов |
| `message` | string | да | 1–20 000 символов |
| `category` | string | нет | до 100 символов |
| `priority` | string | нет | `Low`, `Normal`, `High`, `Urgent`; default `Normal` |
| `attachments` | file, повторяемое | нет | до 5 файлов, 10 MiB каждый, 25 MiB суммарно |

Успех: `201 Created`, полный объект обращения со статусом `New`. Текст и вложения сохраняются в одной SQLite-транзакции.

### Обращения

- `GET /tickets?status=New&category=Gameplay&priority=High&limit=50&offset=0` — список, фильтры необязательны; `limit` 1–100.
- `GET /tickets/{ticket_id}` — подробности, факты, найденные правила и метаданные вложений.
- `PATCH /tickets/{ticket_id}/status` — ручное изменение статуса, JSON: `{"status":"Needs Review"}`. Допустимые значения: `New`, `Processing`, `Needs Review`, `Approved`, `Escalated`, `Closed`.
- `GET /tickets/{ticket_id}/attachments/{attachment_id}` — скачивание вложения.

### Передача результата AI

`POST /tickets/{ticket_id}/analysis` — JSON от отдельного доверенного AI-модуля:

```json
{
  "category": "Gameplay",
  "priority": "Normal",
  "extracted_facts": ["Текстовое описание извлечённого факта"],
  "matched_rules": [
    {"document_name": "название проверенного документа", "rule_id": "ID пункта"}
  ],
  "draft_reply": "Черновик, который проверит оператор",
  "confidence": 0.82,
  "escalation_required": false,
  "escalation_reason": null
}
```

Пункты в `matched_rules` должны существовать в таблице `rules`; неизвестные ссылки отклоняются с 422. При `escalation_required=true` требуется `escalation_reason`. Анализ сохраняется атомарно; статус обращения автоматически не меняется. Невалидный или неудачный анализ не удаляет исходное обращение. Этот endpoint принимает результат анализа, но сам AI не запускает и не вызывает внешние сервисы.

### Локальный модуль предварительного анализа

`POST /tickets/{ticket_id}/analyze-structured` возвращает и сохраняет строгую structured schema; legacy `/analyze` продолжает отдавать UI-compatible формат.

Локальный `POST /tickets/{ticket_id}/analyze` проверяет structured Pydantic result и возвращает прежний UI-compatible формат. `POST /tickets/{ticket_id}/analyze-structured` возвращает и сохраняет строго типизированную схему Task 3; детали обращения по-прежнему получают legacy-compatible `ai_analysis`. В обоих случаях содержимое вложений не считается просмотренным, внутренние игровые логи недоступны, статус автоматически не меняется.

Пример локального запуска анализа:

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/tickets/<ticket_id>/analyze"
```

Результат хранится в поле `ai_analysis` при чтении `GET /tickets/{ticket_id}`. Краткие факты также сохраняются с префиксами `PLAYER_CLAIMS`, `ATTACHMENTS`, `VERIFIED_SYSTEM_DATA` и `UNKNOWN` для совместимости с текущей моделью Backend.

Локальный `AnalysisProvider` может вызывать настроенный OpenAI-compatible provider; без credentials выполняется осторожный deterministic fallback. Локальный поиск правил остаётся лексическим по SQLite и не является pgvector. Supabase Edge Function использует embeddings/pgvector; качество реального LLM и hosted RAG не подтверждено локальными unit tests. Если нет версионированного HTTPS-источника, citation не возвращается и требуется operator review.

### База правил

- `GET /rules?query=...&language=...&limit=50` — поиск по ID, заголовку и тексту.
- SQLite-таблица `rules` хранит `document_name`, `rule_id`, `rule_title`, `rule_text`, `source_url`, `language`, `version_or_date`. Ключ правила составной: `(document_name, rule_id)`.

SQLite база правил создаётся пустой и локальный импорт для неё не добавлен. Supabase ingestion CLI описан в [AI_RAG.md](AI_RAG.md): он принимает только source с allowlisted HTTPS host, версией и явными номерами правил. В репозитории нет проверенных материалов Grand Mobile, поэтому документы необходимо предоставить и подтвердить до индексации.

## Модель данных

`tickets` хранит `ticket_id`, `player_id`, `message`, `category`, `priority`, `status`, `extracted_facts`, `draft_reply`, `confidence`, `escalation_required`, `escalation_reason`, `created_at`. Вложение хранится в таблице `attachments` как BLOB вместе с именем, MIME-типом и размером; связанные правила — в `ticket_matched_rules`. Правила хранятся отдельно в `rules`.

Дата создания хранится в UTC ISO 8601. Анализ не меняет статус автоматически. `Approved` означает ручное изменение статуса, а не автоматическое принятие или отправку ответа.

## Состав и ограничения

- AI-модули: `app/ai_engine/models.py` (strict schemas), `services.py` (language/classification/facts/rules/escalation/drafts), `providers.py` (provider protocol), `ingestion.py` и `scripts/ingest_official_rules.py` (RAG ingestion).
- Supabase foundation включает PostgreSQL migrations, Auth profiles, RLS, private Storage, pgvector RPC и защищённую Edge Function. Локальная FastAPI/SQLite база остаётся отдельным режимом и не синхронизируется с Supabase.
- OCR/видео, интеграция с игровыми логами/Grand Mobile и автоматическая отправка ответов не реализованы. Официальные правила в проект не включены, а hosted Supabase/Edge и реальный внешний provider требуют проверки на развернутом проекте.
- Ответы игрокам автоматически не отправляются; внутренние игровые логи не запрашиваются.

AI-модульные и API-тесты запускаются вместе с Backend-тестами командой `py -m unittest discover -s tests -v`.
