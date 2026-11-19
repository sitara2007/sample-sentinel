# Sample Sentinel

Dataset ingestion and quality-audit MVP. FastAPI accepts text samples, stores them with exact-dedupe (`UNIQUE(dataset_id, content_hash)`), and writes audit rows for short text, empty labels, exact duplicates, and optional near-duplicates.

## Local (SQLite)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
pytest -q
```

Default database is `sqlite:///./sample_sentinel.db`. Override with `DATABASE_URL`. Near-duplicate cosine threshold is `THRESHOLD` (default `0.95`).

### API

- `POST /datasets` — `{ "name": "complaints" }`
- `POST /datasets/{id}/samples` — header `Idempotency-Key`, body list of `{text, label, source}` (max 100)
- `GET /datasets/{id}/report` — counts by status, duplicate counts, flagged sample IDs with rule + reason

Same `Idempotency-Key` returns the stored batch result and does not re-insert.

Migrations (PostgreSQL or SQLite):

```bash
alembic upgrade head
```

## Docker (PostgreSQL)

```bash
docker compose up --build
```

## Limitations

- **No auth** — every endpoint is open.
- **Single-node** — idempotency and uniqueness are local to one process/database; there is no distributed lock.
- **In-process model** — `all-MiniLM-L6-v2` loads in the API process when installed; there is no embedding service.
- **No backpressure** — bounded `asyncio.Semaphore(4)` only; overload is not shed or queued.
- **No DLQ** — rejected/invalid records are counted, not parked for replay.
