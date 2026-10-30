# ZHS Support Copilot backend

Локальный backend для регистрации обращений, хранения вложений и передачи результата AI-анализа. Интеграции с Grand Mobile, AI-провайдером и отправки ответов игрокам здесь нет.

## Требования и запуск

- Python 3.11+

В PowerShell из папки проекта:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
py -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

По умолчанию SQLite-файл `support_copilot.db` создаётся в текущей папке. Для другого расположения задайте переменную `SUPPORT_COPILOT_DB` до запуска. Сервер привязан к localhost; перед сетевым или production-развёртыванием необходимы аутентификация, авторизация и защищённое хранилище.

- API: <http://127.0.0.1:8000>
- Swagger UI: <http://127.0.0.1:8000/docs>
- OpenAPI JSON: <http://127.0.0.1:8000/openapi.json>

Проверка тестов:

```powershell
py -m pip install -r requirements-test.txt
py -m unittest discover -s tests -v
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

`POST /tickets/{ticket_id}/analyze` запускает локальный детерминированный анализ сохранённого обращения, проверяет результат через Pydantic-схему и сохраняет совместимые поля через тот же репозиторий. Ответ включает `category_reason`, `language`, `summary`, `player_claims`, `attachments`, `verified_system_data`, `unknowns`, `matched_rules`, `draft_reply`, `confidence`, `escalation_required` и `escalation_reason`. Вложение описывается только метаданными, `inspected` всегда `false`; внутренние логи не доступны. Статус обращения не меняется, ответ игроку не отправляется.

Пример локального запуска анализа:

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/tickets/<ticket_id>/analyze"
```

Результат хранится в поле `ai_analysis` при чтении `GET /tickets/{ticket_id}`. Краткие факты также сохраняются с префиксами `PLAYER_CLAIMS`, `ATTACHMENTS`, `VERIFIED_SYSTEM_DATA` и `UNKNOWN` для совместимости с текущей моделью Backend.

Модуль не вызывает внешнюю языковую модель: классификация основана на объяснимых словарных признаках, поиск правил — на лексическом пересечении слов с точным текстом из таблицы `rules`, уверенность является эвристической, а не вероятностью. Если правило не найдено, обращение эскалируется, а черновик сообщает об отсутствии совпадения. Не загружайте фиктивные правила: база должна содержать только проверенные документы.

### База правил

- `GET /rules?query=...&language=...&limit=50` — поиск по ID, заголовку и тексту.
- SQLite-таблица `rules` хранит `document_name`, `rule_id`, `rule_title`, `rule_text`, `source_url`, `language`, `version_or_date`. Ключ правила составной: `(document_name, rule_id)`.

База правил создаётся пустой. Механизм импорта и публичный endpoint для добавления правил в MVP не реализованы; перед запуском AI-модуля нужно отдельно загрузить материалы, предварительно подтверждённые владельцем проекта. Поэтому AI не может сохранить ссылку на правило, которого нет в этой базе.

## Модель данных

`tickets` хранит `ticket_id`, `player_id`, `message`, `category`, `priority`, `status`, `extracted_facts`, `draft_reply`, `confidence`, `escalation_required`, `escalation_reason`, `created_at`. Вложение хранится в таблице `attachments` как BLOB вместе с именем, MIME-типом и размером; связанные правила — в `ticket_matched_rules`. Правила хранятся отдельно в `rules`.

Дата создания хранится в UTC ISO 8601. Анализ не меняет статус автоматически. `Approved` означает ручное изменение статуса, а не автоматическое принятие или отправку ответа.

## Состав и ограничения MVP

- Модули: `app/main.py` (HTTP/API), `app/models.py` (Backend-контракт), `app/database.py` (SQLite и репозиторий), `app/ai_engine/` (схемы результата, классификация, извлечение и поиск правил).
- Реализованы создание/чтение обращений, фильтры, статусы, вложения, хранение результата анализа, локальный baseline-анализ и поиск по загруженным правилам.
- Не реализованы: внешняя языковая модель, OCR/просмотр файлов, семантический векторный поиск, импорт/администрирование проверенных правил, аутентификация/роли операторов, интеграция с Grand Mobile, аудит действий, production-хранилище вложений и автоматическое уведомление о передаче человеку.
- Ответы игрокам автоматически не отправляются; внутренние игровые логи не запрашиваются.

AI-модульные и API-тесты запускаются вместе с Backend-тестами командой `py -m unittest discover -s tests -v`.
