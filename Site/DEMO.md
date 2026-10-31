# Decentrathon 6.0 Demo

## Data and prerequisites

The seed creates six synthetic tickets for scenarios T1-T6. Both ticket IDs and player IDs contain `SYNTHETIC`; no real player information, attachments, or rule records are added. Seeding is idempotent and does not delete existing tickets.

Use the local FastAPI + SQLite mode on localhost only. Python 3.11+, Node.js 20.19+, and npm are required. Follow the environment separation in the repository root README: server values belong in `.env.backend`, frontend values in `.env.local`.

From `Site/`, in the backend terminal:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env.backend
set -a
. ./.env.backend
set +a
python -m scripts.seed_demo_tickets
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Leave `LLM_API_KEY` and `LLM_MODEL` empty for the deterministic offline analysis. In another terminal:

```sh
cd Site
cp frontend.env.example .env.local
npm ci
npm run dev -- --host 127.0.0.1
```

Open <http://127.0.0.1:5173>.

## Operator walkthrough

1. Open **Tickets** and search for `SYNTHETIC-DEMO-T1`.
2. Open `DEMO-SYNTHETIC-T1`, the synthetic ban appeal.
3. Select **Анализировать**. Review the classification, player claims, unknowns, missing-information questions, verified-data section, and escalation reasons.
4. Open **Правила Grand Mobile** in the analysis panel. The repository currently ships no verified official rule documents, so the expected safe result is no citation and a reason for operator review. Do not present a test fixture or invented rule as official.
5. Open **Response Drafts**, select the same synthetic ticket, and choose **Перегенерировать**. Inspect the language, unknowns, rule references, escalation warning, and draft text.
6. Edit the draft if needed, choose **Сохранить изменения**, then **Отметить проверенным**.
7. Return to the ticket and change its status using the status selector. The draft remains an operator-reviewed draft; no message is sent to a player.

## Official citation gate

The requested demo step of showing an official rule reference is blocked until an owner-approved, current rules document and canonical HTTPS source are supplied. Import and verify that document using the procedure in [AI_RAG.md](AI_RAG.md), then repeat analysis and confirm the exact rule number, excerpt, version, and URL against the source before the event. Without that source, show the empty citation state rather than a fabricated reference.