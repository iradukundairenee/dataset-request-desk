# Notes

<!--
SKELETON. The bullets under each heading are reminders of facts and decisions
from the build, not finished text. Replace them with your own reasoning.
Aim for 1–2 pages in total.
-->

## 1. Design

### Data model

<!-- a paragraph or a small diagram: users, episodes, requests, request_status_events, assignments, import_runs -->

- users → requests (client_id) → request_status_events (one row per change, incl. creation NULL → submitted)
- requests ↔ episodes through assignments; `UNIQUE(assignments.episode_id)` = one request at a time, enforced by the DB
- import_runs: file SHA-256, counts, issues per import
- DB-level guards: `CHECK episodes_requested > 0`, `CHECK duration_seconds > 0`, `CHECK email = lower(email)`, `UNIQUE(episode_id)`

### Where state lives

- Postgres is the only source of truth; the API is stateless (JWT), the web app keeps only the token (sessionStorage)
- Status history is append-only; current status is a column on requests, written in the same transaction as its event

### The 2–3 hardest decisions

<!-- pick 2–3 and explain the options you weighed and why you chose this -->

- Conflicting duplicates in the CSV (EP-00011 bad vs good): skip all rows vs keep first/last → why skipping is safer (a wrong "good" becomes assignable)
- Two-pass import (a conflict can appear anywhere later; single pass would already have inserted the first row); pass 1 stores a hash per id to keep memory small
- Row lock (`SELECT … FOR UPDATE`) on the request for transitions AND assign/unassign → the "enough episodes to deliver" check can't race an unassign
- Check order in transitions: 404 (not your request) → 403 (role for the target status) → 409 (not a valid move / not enough episodes)
- Re-import never updates existing episodes (an assigned episode must not silently change quality)

### Decisions made where the brief was silent

- Admins cannot accept/reject (client's step); nothing can move back to `submitted`; `accepted` is final
- Only clients create requests; deadline in the past → 422
- `episode_id` uppercased on import (so `ep-00003` conflicts with `EP-00003`)
- `future_date` (> 1 day ahead), duration must be ≤ 3600 s, `missing_task_name`, `value_too_long`
- `DD/MM/YYYY` assumed (never `MM/DD`); naive timestamps = UTC
- Invalid rows don't take part in duplicate detection
- Task names normalised the same way for requests and episodes; assigning doesn't require matching task; over-assigning allowed
- Analytics: requests-by-status counts requests *created* in range; median uses the *first* delivery, for requests first delivered in range; days are UTC days
- Deactivation instead of deletion; admin can't deactivate or demote themselves (so there is always an active admin)

## 2. Deliberately left out / simplified, and the next two days

- Left out: <!-- e.g. rejection reason, pagination on request list, token revocation/refresh, frontend tests, rate limiting on login, … -->
- Simplified: <!-- e.g. startup import adds an import_runs row on every restart; client sees operators' names in history -->
- Next two days: <!-- your priorities, e.g. daily summary table for analytics, COPY-based import, httpOnly cookie auth, … -->

## 3. Something that went wrong

<!-- pick one and tell it: symptom → how you diagnosed → fix → what you learned -->

Candidates from the build:

- The concurrency test **hung the whole test suite** when the lock was removed on purpose: the failing assertion skipped closing the session holding the lock, so the table cleanup (`TRUNCATE`) waited forever → fixed with `try/finally`; in CI this would have been a stuck job
- Analytics day boundaries: `date_trunc` on `timestamptz` uses the session time zone; tests passed only because the test DB runs in UTC → added a test that sets `Africa/Kigali`, which fails without `AT TIME ZONE 'UTC'`
- Import took 34 s for 200k rows; profiling showed parsing was 2.4 s → the time was SQLAlchemy recompiling a 7,000-parameter `INSERT … VALUES` per batch → executemany form: 14 s
- Importer pass-1 memory: 143 MB for 200k ids (≈ 3.5 GB at 5M) → store a 64-bit hash per id: 62 MB
- Alembic `ModuleNotFoundError: app` on first startup (`prepend_sys_path`); `fileConfig` disabling the app's JSON logger in tests (`disable_existing_loggers=False`)
- UI: a request for task "pickup kabiri" could never be delivered — no episodes matched; led to task-name suggestions and a clearer empty state

## 4. Security

- Passwords: bcrypt (cost 12); 72-byte limit handled (422 on create, 401 on login instead of a 500)
- Tokens: HS256 JWT, 8 h expiry, secret from env (API refuses to start without it), algorithm pinned (`alg: none` rejected); user reloaded from the DB on every request, so deactivation and role changes apply immediately
- Login: same message and similar timing for unknown email / wrong password / deactivated (dummy hash check)
- Authorization in the service layer, not the UI; another client's request → 404 (doesn't reveal it exists)
- Input validation: pydantic schemas + service rules; CSV strictly validated; upload size limit (100 MB); SQL only through bound parameters
- Logs: path without query string (no tokens in logs); no stack traces in responses
- The 2 vulnerabilities I'd worry about most: <!-- e.g. token theft (sessionStorage + XSS, no revocation) / brute force on login (no rate limit) / … — explain why -->

## 5. Scale

<!-- what breaks first at 10× users and at 100× episodes, and what you'd change -->

- Measured (200k episodes): analytics 4–12 ms for 1 month (index), 27–129 ms for 1 year (full scan); import 200k rows in ~14 s
- 100× episodes: long analytics ranges scan millions of rows (≈ seconds) → daily summary table; import memory ~1.5 GB at 5M ids → COPY into a staging table
- 10× users: <!-- e.g. bcrypt CPU on login, DB connection pool, request list without pagination, polling -->

## 6. AI tooling

<!-- which tools, for what, and how you checked the output -->

- Claude Code, driven by CLAUDE.md (my plan and rules): one phase at a time, I reviewed each diff and committed myself
- Used for: <!-- … -->
- How I verified: <!-- tests per rule; deliberately breaking rules to confirm a test fails; running the app and API by hand -->
