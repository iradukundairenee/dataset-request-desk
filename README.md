# Dataset Request Desk

An internal platform that replaces the spreadsheet used to track dataset requests.
Clients request robot episodes, operators fulfil the requests by assigning
recorded episodes, and clients accept or reject the delivery.

Backend: Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16.
Frontend: React + Vite + TypeScript. Everything runs with Docker Compose.

Design decisions, trade-offs and what I left out are in [NOTES.md](NOTES.md).

---

## Run it

Requirements: Docker with Compose v2. Nothing else.

```bash
docker compose up --build
```

That single command, from a clean clone:

1. starts PostgreSQL,
2. applies the database migrations (Alembic),
3. creates the seed users (safe to repeat),
4. imports `seed/episodes.csv` (safe to repeat),
5. starts the API, then the web app.

| What | URL |
|---|---|
| Web app | http://localhost:8080 |
| API | http://localhost:8000 |
| Interactive API docs | http://localhost:8000/docs |

Ports can be changed with `WEB_PORT` / `API_PORT` in a `.env` file (see `.env.example`).
To start again from an empty database: `docker compose down -v`.

### Seed accounts

| Role | Email | Password |
|---|---|---|
| admin | `admin@example.com` | `admin123` |
| operator | `ops1@example.com` | `ops123` |
| operator | `ops2@example.com` | `ops123` |
| client | `client-a@example.com` | `client123` |
| client | `client-b@example.com` | `client123` |

Passwords are stored as bcrypt hashes, never in plain text.

---

## Run the tests

```bash
docker compose run --rm api pytest -q
```

The tests run against a real, separate PostgreSQL (`db_test` service). The test
schema is built by running the real migrations (down to empty, then up), and
every test starts with empty tables.

What they cover, by priority:

| Area | Examples |
|---|---|
| Authorization | 401 for missing/expired/forged/`alg:none` tokens; a deactivated user's existing token stops working; role changes apply immediately; 403 for every wrong role; a client gets 404 (not 403) for another client's request |
| Status transitions | every valid transition by the right role writes an event; **all 20 invalid from→to pairs** return 409 and change nothing; delivery needs enough assigned episodes |
| Assignments | only `good`/`usable`; one request per episode (also enforced by a DB constraint); all-or-nothing; no changes while delivered/accepted; **a concurrency test** proving an unassign waits for the row lock held by a delivery |
| Import | exact counts per skip reason on `seed/episodes.csv`; running twice inserts nothing the second time; re-import never changes an existing episode; conflicting duplicates far apart in the file; a generated 20k-row file |
| Analytics | hand-made data with known answers; inclusive date range; UTC day boundaries even when the DB session is in Kigali time; median with odd/even counts and rework |

CI (GitHub Actions, `.github/workflows/ci.yml`) builds both images, runs the
tests, starts the whole stack with `docker compose up --wait` and smoke-tests
it through the web app's proxy.

> **CI note:** the workflow is ready, but GitHub Actions can't start on my
> account because of an unrelated billing lock (the run shows "The job was not
> started because your account is locked due to a billing issue"). The same
> steps pass locally:
>
> ```bash
> docker compose build && docker compose run --rm api pytest -q && docker compose up -d --wait
> ```

---

## What each role can do

| | client | operator | admin |
|---|---|---|---|
| Create a request | ✅ | | |
| See requests | own only | all | all |
| Move to `in_progress` / `delivered` | | ✅ | ✅ |
| Accept / reject a delivery | ✅ (own) | | |
| Browse episodes, assign / unassign | | ✅ | ✅ |
| Import episodes (CSV) | | ✅ | ✅ |
| Analytics | | ✅ | ✅ |
| Create users, change roles, deactivate | | | ✅ |

All of this is enforced by the API; the web app only hides buttons the user
cannot use.

Request workflow:

```
submitted → in_progress → delivered → accepted
                                    ↘ rejected → in_progress (rework)
```

Every change (including creation) is stored in `request_status_events` with who
and when, in the same transaction as the status change.

---

## Importing episodes

```bash
# CLI
docker compose run --rm api python -m cli import /seed/episodes.csv

# API (operator or admin token; the CSV is the raw request body)
curl -X POST "http://localhost:8000/episodes/import?filename=episodes.csv" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: text/csv" \
  --data-binary @seed/episodes.csv
```

The import is **idempotent**: episodes are inserted with
`ON CONFLICT (episode_id) DO NOTHING`, so running the same file again inserts
nothing, and an episode that already exists is never modified.

It returns a report, and saves it in `import_runs` with the file's SHA-256:

```json
{
  "inserted": 171, "already_imported": 0, "blank_lines": 2, "skipped": 18,
  "skipped_by_reason": {"conflicting_duplicate": 4, "duplicate_in_file": 2, "invalid_duration": 4, "...": 1},
  "warnings": {"missing_operator_name": 1},
  "issues": [{"line": 3, "episode_id": "EP-00011", "reason": "conflicting_duplicate"}, "..."]
}
```

How each messy case in the seed file is handled (full reasoning in NOTES.md):

| Case | Result |
|---|---|
| Extra spaces, `ARM-01`, `Good`, `  Pick Cup ` | normalised (trimmed, lowercased, spaces collapsed) and imported |
| `YYYY-MM-DD HH:MM:SS`, `…Z`, `DD/MM/YYYY HH:MM` | accepted; timestamps without a timezone are treated as UTC |
| Same row twice (EP-00074, EP-00030) | first kept, repeat reported as `duplicate_in_file` |
| Same id with different values (EP-00011 `bad` vs `good`; `EP-00003` vs `ep-00003`) | **all rows skipped** as `conflicting_duplicate`: we can't tell which is true, and a wrong `good` would make it assignable |
| Unknown or empty robot (`arm-99`) | `unknown_robot` |
| Quality `excellent` or empty | `invalid_quality` |
| `not a date` / year 2031 | `invalid_date` / `future_date` |
| Duration empty, `N/A`, `-5`, `999999` | `invalid_duration` (must be > 0 and ≤ 3600 s) |
| Missing episode id / wrong column count | `missing_episode_id` / `malformed_row` |
| Empty operator name | imported with no operator, reported as a warning |
| Task with a comma (quoted) | imported as is |

A wrong header, a non-UTF-8 file or an empty file rejects the whole file (422).

---

## API overview

Full, interactive reference at http://localhost:8000/docs. Errors always have
the shape `{"error": {"code": "...", "message": "..."}}`.

| Method & path | Who | Purpose |
|---|---|---|
| `POST /auth/login` | anyone | email + password → bearer token (8 h) |
| `GET /auth/me` | logged in | current user |
| `GET/POST /users`, `PATCH /users/{id}` | admin | list, create, change role / deactivate |
| `GET /requests?status=` | logged in | list (clients: own only) |
| `POST /requests` | client | create |
| `GET /requests/{id}` | logged in | detail with status history |
| `POST /requests/{id}/transition` | depends on target status | `{"to_status": "..."}` |
| `GET /requests/{id}/assignments` | staff, or the owning client | assigned episodes |
| `POST /requests/{id}/assignments` | operator, admin | `{"episode_ids": [...]}` |
| `DELETE /requests/{id}/assignments/{episode_id}` | operator, admin | unassign |
| `GET /episodes?task_name=&quality=&robot_id=&unassigned_only=&limit=&offset=` | operator, admin | browse with filters and pagination |
| `GET /episodes/tasks` | logged in | known task names |
| `POST /episodes/import` | operator, admin | CSV import |
| `GET /analytics?from=YYYY-MM-DD&to=YYYY-MM-DD` | operator, admin | see below |
| `GET /health` | anyone | 200 if the database answers, else 503 |

Every request writes one JSON log line (`docker compose logs api`):

```json
{"ts": "...", "event": "request", "request_id": "…", "method": "GET", "path": "/requests", "status": 200, "duration_ms": 5.97, "user_id": 4}
```

---

## Analytics, and how it behaves at scale

`GET /analytics?from=&to=` (both dates inclusive, UTC, at most 366 days) returns:

- episodes recorded **per day, per robot**;
- **requests by status** (requests created in the range);
- **median time from `submitted` to `delivered`** (first delivery, so rework doesn't reset the clock), for requests first delivered in the range;
- **top 5 task names by `good` episodes** recorded in the range.

All four are single SQL queries (`GROUP BY`, `percentile_cont`, `count(*) FILTER`)
in `backend/app/services/analytics.py`; Python never loads the episodes.

Measured with 200,000 generated episodes (`seed/generate_episodes.py`) on a laptop:

| Query | 1-month range | 1-year range |
|---|---|---|
| Episodes per day per robot | 12 ms (index on `recorded_at, robot_id`) | 129 ms (full scan) |
| Top 5 tasks by good episodes | 4 ms (index) | 27 ms (full scan) |

**With 5 million episodes:**

- Short ranges stay fast: they read only the matching slice through the
  `recorded_at` indexes, whatever the table size.
- Long ranges grow with the number of rows in the range. A full year would be
  roughly 25× the numbers above (~3 s for the per-day query): acceptable for an
  internal dashboard, not for something refreshed constantly.
- The fix at that point is a small **daily summary table** (day, robot, task,
  quality, count), updated by each import. Analytics would then read a few
  thousand rows instead of millions. Episodes are append-only, which makes that
  easy to keep correct.
- The median query reads all status events. That's tiny today (a few events per
  request); at large volume it would first select only requests delivered in
  the range.

**Import at scale:** 200,000 rows import in about 14 s (and 12 s for a no-op
re-run). The file is streamed twice and never fully loaded; pass 1 keeps one
small entry per episode id (~62 MB for 200k ids, so ~1.5 GB for 5 million).
Beyond that, the next step is `COPY` into a staging table and doing the
duplicate detection and insert in SQL.

---

## Project layout

```
backend/
  app/
    main.py            app factory, error handlers, routers
    auth.py            bcrypt, JWT, current user, role checks
    models.py          SQLAlchemy models
    schemas.py         request/response bodies
    services/          all business rules (requests, assignments, importer, analytics, users)
    routers/           thin HTTP layer over the services
    logging_mw.py      one JSON log line per request
  alembic/             migrations
  cli.py               seed-users, import
  tests/
frontend/              React app, served by nginx (which proxies /api to the API)
seed/                  provided seed data
docs/WORK_TASK.md      the brief
```

## Configuration

| Variable | Default (compose) | Notes |
|---|---|---|
| `JWT_SECRET` | a dev-only value | **required** by the API; set a long random value for any shared deployment (`openssl rand -hex 32`) |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `desk` | dev database |
| `API_PORT` / `WEB_PORT` | `8000` / `8080` | host ports |
| `LOG_LEVEL` | `INFO` | |

## Stretch item

None yet. <!-- update if you add one: real-time / background work / deployment -->
