# Dataset Request Desk — Claude Code guide

Technical test for Neotix. Brief: `docs/WORK_TASK.md`. Seed data: `seed/`.
Deadline Sun 04 Oct 2026 23:59 (UTC+2). Budget 6–8h. Small, correct, tested > big.

## Working rules (important)
- Work ONE phase at a time (see Build plan). Stop at the end of each phase and summarise
  what changed and why, so I can review the diff and commit it myself.
- Never run `git commit` or `git push`. I commit.
- Keep code plain and readable. No clever abstractions, no extra libraries unless asked.
  I must be able to explain and modify every line in a live interview.
- Every domain rule is enforced in the service layer AND covered by a test.
- Don't write NOTES.md prose for me beyond a skeleton; I write the reasoning.

## Stack
- Backend: Python 3.12, FastAPI, SQLAlchemy 2.0 (sync), Alembic, PostgreSQL 16, pydantic v2
- Auth: bcrypt (passlib or bcrypt lib) password hashes; JWT bearer token (PyJWT), 8h expiry
- Frontend: React + Vite + TypeScript, plain fetch, minimal CSS. No UI kit.
- Tests: pytest against a real Postgres (docker compose service `db_test` or testcontainers)
- Ops: docker compose (db, api, web), GitHub Actions running pytest

## Layout
```
backend/
  app/
    main.py            # app factory, middleware, routers
    config.py          # env settings
    db.py              # engine/session
    models.py          # SQLAlchemy models
    schemas.py         # pydantic
    auth.py            # hashing, JWT, get_current_user, require_role(...)
    logging_mw.py      # structured JSON request logging
    services/
      requests.py      # status machine + transitions
      assignments.py   # assignment rules
      importer.py      # CSV import (pure parse/validate + DB upsert)
      analytics.py     # SQL queries
    routers/ auth.py users.py requests.py episodes.py analytics.py health.py
  alembic/
  cli.py               # `python -m cli import seed/episodes.csv`, `seed-users`
  tests/
frontend/
seed/
docker-compose.yml
```

## Data model
- users(id, email UNIQUE citext/lowercased, password_hash, name, role enum[client,operator,admin],
  organisation NULL, is_active, created_at)
- episodes(id PK, episode_id TEXT UNIQUE, robot_id, task_name, recorded_at TIMESTAMPTZ,
  duration_seconds NUMERIC(8,2), operator_name NULL, quality enum[good,usable,bad], imported_at, import_run_id)
  - indexes: (recorded_at, robot_id); (task_name, quality); partial on recorded_at WHERE quality='good'
- requests(id, client_id FK users, task_name, episodes_requested INT CHECK > 0, deadline DATE,
  notes, status enum, created_at, updated_at)
- request_status_events(id, request_id FK, from_status NULL, to_status, actor_id FK users, created_at)
  - an event row is written for creation (NULL → submitted) and every transition, in the same transaction
- assignments(id, request_id FK, episode_id FK UNIQUE, assigned_by FK users, assigned_at)
  - UNIQUE(episode_id) enforces "one request at a time" at the DB level
- import_runs(id, filename, file_sha256, started_by, started_at, counts JSONB, issues JSONB)

## Domain rules
Transitions (role that may perform it):
- submitted → in_progress: operator/admin
- in_progress → delivered: operator/admin, only if assigned count >= episodes_requested
- delivered → accepted: client who owns the request
- delivered → rejected: client who owns the request
- rejected → in_progress: operator/admin
Anything else → 409 with a clear message. Wrong role → 403.
- Lock the request row (`SELECT ... FOR UPDATE`) during transition and during assign/unassign
  so the delivered-count check can't race with a concurrent unassign.
- Assign: only good/usable episodes; episode not already assigned (DB unique → 409);
  request must be submitted/in_progress/rejected. No assign/unassign while delivered or accepted.
- Clients: list/get only own requests. Another client's request returns 404 (don't leak existence).
- Deactivated users can't log in and existing tokens are rejected (check is_active on each request).
- Admin can create users, deactivate, change roles. Admin cannot deactivate themselves.

## CSV import decisions (report every skipped/changed row with line number + reason)
Normalisation: strip whitespace on all fields; lowercase robot_id, task_name, quality;
collapse internal whitespace in task_name.
- Wrong column count / blank line → skip `malformed_row` (blank lines just counted)
- Missing episode_id → skip `missing_episode_id`
- Same episode_id twice in the file, identical after normalising → keep first, `duplicate_in_file`
- Same episode_id twice with conflicting values (e.g. EP-00011 bad vs good) → skip ALL rows for
  that id, `conflicting_duplicate` (we can't know which is true; a wrong "good" would make it assignable)
- robot_id empty or not in known list (arm-01, arm-02, arm-03, mobile-01, humanoid-01) → skip `unknown_robot`
- quality empty or not good/usable/bad (e.g. "excellent") → skip `invalid_quality`
- recorded_at: accept ISO 8601 (with or without `Z`/offset), `YYYY-MM-DD HH:MM:SS`, and `DD/MM/YYYY HH:MM`.
  Naive timestamps treated as UTC. Unparseable → skip `invalid_date`
- duration_seconds: must parse as a positive number; 45.5 accepted; empty/"N/A"/<=0 → skip `invalid_duration`
- operator_name empty → import with NULL, report as warning `missing_operator_name`
- Task names with commas are valid (quoted CSV field)
Idempotency: `INSERT ... ON CONFLICT (episode_id) DO NOTHING`; rows that already exist are reported
as `already_imported`, not modified (an assigned episode must never silently change quality).
Batch inserts (e.g. 1000 rows) so 200k-row files work; stream the file, don't load it all.
Response/CLI output: {inserted, already_imported, skipped_by_reason{}, warnings{}, issues:[{line, episode_id, reason}] (cap list at 500)}.

## Analytics (all computed in SQL)
GET /analytics?from=YYYY-MM-DD&to=YYYY-MM-DD (operator/admin)
- per day per robot: `date_trunc('day', recorded_at)`, robot_id, count(*) GROUP BY
- requests by status: count GROUP BY status (requests created in range)
- median submitted→delivered: first submitted event and first delivered event per request,
  `percentile_cont(0.5) WITHIN GROUP (ORDER BY delivered_at - submitted_at)`
- top 5 tasks by good episodes: WHERE quality='good' GROUP BY task_name ORDER BY count DESC LIMIT 5
Validate from <= to and cap range (e.g. 366 days).

## Operability
- GET /health → checks DB with `SELECT 1`, returns 200/503
- One JSON log line per request: method, path, status, duration_ms, user_id (if authenticated), request_id
- Consistent error JSON: {"error": {"code", "message"}}; never leak stack traces
- `docker compose up` from clean clone: db → migrations → seed users → api → web

## Build plan (one phase per session/commit batch)
1. Skeleton: compose, FastAPI app, config, /health, logging middleware, Alembic init
2. Models + first migration; seed-users CLI (hashed passwords from seed/users.json, idempotent)
3. Auth: login, JWT, current user, role deps; tests for 401/403/inactive user
4. Requests: create/list/get + status machine + events; tests for every valid and invalid transition and role
5. Episodes import (parser as pure functions + DB upsert) + CLI + endpoint; tests on seed CSV:
   counts per reason, and running twice inserts 0 the second time
6. Episodes list with filters (task_name, quality, unassigned only, pagination) + assignments; tests for rules
7. Analytics endpoint + tests with small fixture data
8. Frontend: login, client view (create/list/accept/reject), operator view (all requests, transition, assign w/ filters)
9. GitHub Actions CI, README (run, test, seed creds), NOTES.md skeleton
10. Optional stretch: SSE for live request updates (only if time left)

## Commands
- `docker compose up --build`
- `docker compose run --rm api pytest -q`
- `docker compose run --rm api python -m cli import seed/episodes.csv`