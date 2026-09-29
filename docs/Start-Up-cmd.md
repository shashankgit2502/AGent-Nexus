# Command

## 1. Database Migration

```bash
cd backend && alembic upgrade head
```

---

## 2. Infrastructure (Postgres + Redis) — once

```bash
cd "E:\Agent Hackathon\nex-agi"
docker compose up -d
```

> already running on your machine (`db:5433`, `redis:6379`)

First time only (schema):

```bash
cd backend && alembic upgrade head
```

> yours is already migrated.

---

## 3. Backend

```bash
cd "E:\Agent Hackathon\nex-agi\backend"
python run.py
```

Wait for Uvicorn running on:

```text
http://127.0.0.1:8000
```

Then it's live at:

```text
http://localhost:8000
```

API docs:

```text
http://localhost:8000/docs
```

---

## 4. Frontend (terminal 2)

```bash
cd "E:\Agent Hackathon\nex-agi\frontend"
npm install
```

> first time only

```bash
npm run dev
```

Next.js + turbopack →

```text
http://localhost:3000
```

Open:

```text
http://localhost:3000
```

If your API isn't on `localhost:8000`, set:

### `frontend/.env.local`

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
```

---

## 5. Startup Order

```text
infra
  → backend (wait for /health)
  → frontend
```

Without provider API keys the agents run the deterministic stub path — the whole UI loop:

```text
teams
  → agents
  → session
  → live stream
  → HITL
  → History
```

works, just with stubbed model text.