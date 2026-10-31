# AI and RAG Backend

## Runtime modes

The local FastAPI service uses SQLite and keeps its existing UI-compatible `POST /tickets/{ticket_id}/analyze` response. `POST /tickets/{ticket_id}/analyze-structured` returns the strict `StructuredAnalysisResult` schema and saves a compatibility representation for existing ticket detail consumers. The local service is unauthenticated and must remain bound to localhost.

The Supabase Edge Function is the protected runtime: Supabase Auth validates the bearer token, `operator_profiles` authorizes operators, Postgres stores tickets and analysis history, Storage keeps private evidence, and pgvector retrieves active rule chunks. The Edge Function returns the strict analysis JSON from `/tickets/{id}/analyze`; `GET /tickets/{id}` maps compatibility aliases for the current Frontend. Neither runtime sends player replies or makes final account/sanction decisions.

## AI contract

The structured result is validated with Pydantic locally and strict runtime validation in the Edge Function. It contains:

```json
{
  "ticket_id": "string",
  "language": "ru | kk | uz | other",
  "category": "appeal_ban | player_report | admin_complaint | account_security | payment | bug | other",
  "priority": "low | normal | high | urgent",
  "summary": "string",
  "player_claims": [],
  "provided_evidence": [],
  "verified_data": [],
  "unknowns": [],
  "missing_information_questions": [],
  "rule_references": [],
  "analysis": "string",
  "draft_reply": "string",
  "human_review_required": true,
  "escalation_reasons": [],
  "confidence": 0.0
}
```

Each `rule_references` item has `document_title`, `rule_number`, `exact_excerpt`, `source_url`, and `source_version_date`. The local extractor treats message sentences as player claims and attachment metadata as provided evidence. `verified_data` is empty unless supplied through the trusted server-side integration argument; request JSON and model output cannot populate it. Supabase analysis currently has no trusted Grand Mobile data integration, so it always persists an empty array.

Rule citations are accepted only from active indexed documents with HTTPS source URLs and a recorded version. No matching source means an empty citation list, an explicit unknown, and human review. Confidence is a heuristic/model score and is not calibrated for autonomous decisions. The default local threshold is `0.6`; the Supabase Edge Function also requires human review below `0.6`.

## Configuration

Start from `.env.example` and put local FastAPI values in ignored `.env.backend`, or local Edge Function values in ignored `.env.supabase`. Keep `.env.local` exclusively for Vite frontend values copied from `frontend.env.example`. Use the deployment secret manager for hosted secrets. Never set server keys in `Site/src`, Vite variables, or browser storage.

For local FastAPI, create `.env.backend` from `.env.example` and export those server-side values before starting the API or ingestion CLI. Keep `.env.local` exclusively for Vite values copied from `frontend.env.example`; never load `.env.backend` into frontend tooling. For a local Supabase Edge Function, use `.env.supabase` as the function environment file:

```sh
cp .env.example .env.backend
set -a
. ./.env.backend
set +a
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- `SUPABASE_URL`: Supabase project URL.
- `SUPABASE_ANON_KEY`: used by the Edge Function to validate a user token.
- `SUPABASE_SERVICE_ROLE_KEY`: server-side database and private Storage access only.
- `LLM_API_BASE_URL`: OpenAI-compatible API base URL; defaults to `https://api.openai.com/v1`.
- `LLM_API_KEY`: provider secret, server-side only.
- `LLM_MODEL`: chat model identifier. If absent in local FastAPI, deterministic fallback is used.
- `EMBEDDING_MODEL`: 1536-dimensional embeddings model, defaults to `text-embedding-3-small`.
- `OFFICIAL_RULE_HOSTS`: comma-separated allowlisted hostnames for rule ingestion, without URL paths.
- `ALLOWED_ORIGINS`: comma-separated browser origins allowed by Edge CORS.
- `SUPPORT_COPILOT_DB`: optional local SQLite path.

The Python `AnalysisProvider` protocol is the replacement boundary for local model adapters. Its supplied implementation speaks the OpenAI-compatible chat-completions JSON mode. The Supabase function uses the same compatible HTTP shape and can be pointed to another compatible provider through `LLM_API_BASE_URL`.

## Supabase setup

Run these commands from `Site/` with Supabase CLI installed:

```sh
supabase start
supabase db reset
cp .env.example .env.supabase
supabase functions serve api --env-file .env.supabase
```

For a hosted project, apply migrations and deploy the API function:

```sh
supabase link --project-ref <project-ref>
supabase db push
supabase secrets set SUPABASE_URL="$SUPABASE_URL" SUPABASE_ANON_KEY="$SUPABASE_ANON_KEY" SUPABASE_SERVICE_ROLE_KEY="$SUPABASE_SERVICE_ROLE_KEY" LLM_API_BASE_URL="$LLM_API_BASE_URL" LLM_API_KEY="$LLM_API_KEY" LLM_MODEL="$LLM_MODEL" EMBEDDING_MODEL="$EMBEDDING_MODEL" ALLOWED_ORIGINS="$ALLOWED_ORIGINS"
supabase functions deploy api --no-verify-jwt
```

The function disables gateway JWT verification so `/health` can stay public; it verifies bearer tokens itself for every other route and checks `operator_profiles`. Create/invite users through Supabase Auth, then assign `support_operator` or `admin` to their Auth UUID in `operator_profiles`. Signup is disabled by default. Direct client writes are blocked by RLS; write operations use the Edge Function's service-role client after authorization.

## API

Base URL for hosted Edge Function: `https://<project-ref>.supabase.co/functions/v1/api`. Include `Authorization: Bearer <SUPABASE_ACCESS_TOKEN>` on all routes except `GET /health`. Errors use `{"error":{"code":"...","message":"..."}}`.

| Route | Request | Response |
|---|---|---|
| `GET /health` | None | `{"status":"ok"}` after database check |
| `POST /tickets` | `multipart/form-data`: `player_id`, `message`, optional `category`, `priority`, repeated `attachments` | `201`, ticket detail |
| `GET /tickets` | Optional `status`, `priority`, `category`, `q`, `limit` (1-100), `offset` | `{ "items": [TicketSummary], "count": n, "limit": n, "offset": n }` |
| `GET /tickets/{id}` | Ticket UUID or public ticket code | Ticket detail with latest analysis, draft, rule refs, and attachment metadata |
| `POST /tickets/{id}/analyze` | Empty body | Strict structured analysis JSON shown above |
| `POST /tickets/{id}/generate-reply` | Optional `{"instructions":"..."}` | `201`, versioned draft with `id`, `body`, `version`, `status`, and `created_at` |
| `PATCH /tickets/{id}/status` | `{"status":"Needs Review"}` | Updated `TicketSummary`; an audit record is written |
| `GET /rules/search` | Required `query` (2-200 chars), optional `language`, `limit` (1-50) | `{ "items": [RuleRecord], "count": n }` |

Every generated rule reference is sourced from `match_rule_chunks`; the model cannot add citations. Attachments are limited to five files, 10 MiB each and 25 MiB total. Allowed types are JPEG, PNG, WebP, PDF, and UTF-8 text/plain; MIME declarations and file signatures are checked. Storage is private and downloads are authorized by ticket/attachment association.

Example:

```sh
curl -H "Authorization: Bearer $SUPABASE_ACCESS_TOKEN" \
  -X POST "$SUPABASE_URL/functions/v1/api/tickets/<ticket_id>/analyze"

curl -H "Authorization: Bearer $SUPABASE_ACCESS_TOKEN" \
  "$SUPABASE_URL/functions/v1/api/rules/search?query=appeal&language=ru"
```

The local API's `/tickets/{ticket_id}/analyze-structured` has the same result schema; local `GET /rules?query=...` remains a lexical SQLite search rather than pgvector.

## Official rule ingestion

No Grand Mobile rule documents are shipped or seeded by this repository. Do not treat the category names in this project as official rule content. Obtain current documents from an owner-approved official source and verify the source/version before indexing.

The CLI accepts PDF, HTML, Markdown, and UTF-8 text. It preserves explicit numbered headings and exact section text, rejects unnumbered documents and duplicate numbers, and does not invent rule references. It requires a canonical HTTPS URL on `OFFICIAL_RULE_HOSTS`, a version/date, `verified_by`, Supabase service-role access, and an embedding provider. Each document is inserted inactive; activation runs in a Postgres transaction after all chunks are embedded and stored. Replacing a document deactivates the prior active version with the same title.

```sh
python -m scripts.ingest_official_rules \
  --file /secure/path/official-rules.pdf \
  --title "Official rules" \
  --source-url https://official.example/rules \
  --version "2026-10-01" \
  --verified-by "operator identity" \
  --language ru \
  --activate
```

The migration expects 1536-dimensional vectors. If an embedding model with another dimension is selected, migrate the vector column and matching RPC before ingestion. The service-role key and ingestion host allowlist are privileged; restrict access to the import environment.

## Tests and limitations

Run local tests from `Site/`:

```sh
python -m pip install -r requirements-test.txt
python -m unittest discover -s tests -v
```

Automated coverage includes ban appeals, chat insults, administrator complaints, suspected account compromise, cheating reports, unclear requests, malformed model output, model/provider failure, missing/unsafe rule sources, ingestion cleanup, and strict API shape. It does not validate real LLM quality, hosted Supabase policies, live pgvector behavior, official Grand Mobile sources, or the actual external provider. This environment has no Supabase CLI or Deno runtime, so the Edge Function and SQL migration require deployment/runtime verification before production use.

OCR/image/video analysis, game log integrations, live Grand Mobile API integration, automatic reply delivery, and calibrated confidence thresholds are not implemented. The operator must make all final decisions.