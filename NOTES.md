# Notes

## 1. Design

### Data model

```
users ──< requests ──< request_status_events      (one row per status change, who + when)
             │
             └──< assignments >── episodes ──> import_runs
                  UNIQUE(episode_id)
```

- **users**: email (always lowercase, unique), bcrypt hash, role (`client` / `operator` / `admin`), `is_active`.
- **requests**: belong to one client; task, count, deadline, notes and the *current* status.
- **request_status_events**: an append-only history. Creating a request writes `NULL → submitted`,
  and every transition writes one row in the **same transaction** as the status change, so the
  history can never disagree with the status.
- **assignments**: link an episode to a request. `UNIQUE(episode_id)` means the database itself
  guarantees "one request at a time", even if the application had a bug.
- **episodes**: imported metadata; `UNIQUE(episode_id)`. **import_runs** records each import
  (file SHA-256, counts, issues).

The database also refuses bad data on its own: `episodes_requested > 0`, `duration_seconds > 0`,
`email = lower(email)`.

### Where state lives

Only in PostgreSQL. The API is stateless (a JWT per request, and the user is reloaded from the
database each time). The web app keeps only the token in `sessionStorage`. Schema changes go through
Alembic migrations; the tests build their database by running the real migrations.

### The hardest decisions

**1. Conflicting duplicates in the CSV.** EP-00011 appears twice, once `bad` and once `good`.
I could keep the first row, keep the last row, or skip both. Keeping either one is a guess, and a
wrong guess is dangerous: a `bad` episode wrongly imported as `good` becomes assignable and could be
delivered to a client. So I skip **every** row for that id and report it as `conflicting_duplicate`.
An operator can fix the source and re-import. Identical duplicates are harmless, so the first one is
kept and the rest are reported as `duplicate_in_file`.

**2. Two passes over the file.** Skipping *all* rows of a conflict means I cannot insert while
reading: the conflicting copy can appear thousands of lines later, after the first copy was already
inserted. So pass 1 only reads and remembers, per `episode_id`, the line of its first valid row and a
64-bit hash of its values. Pass 2 reads the file again and inserts in batches of 1,000 with
`ON CONFLICT (episode_id) DO NOTHING`. The file is streamed both times, never fully loaded. Existing
episodes are **never updated** on re-import: an episode that is already assigned must not silently
change quality because a newer export says so.

**3. Locking the request row.** "Deliver only if enough episodes are assigned" is a check followed by
a write. If an operator unassigns an episode between the check and the write, a request could be
delivered short. Every status change **and** every assign/unassign therefore starts with
`SELECT … FOR UPDATE` on the request row, so they queue behind each other. I proved it with a test that
holds the lock in one transaction and shows an unassign in another thread waiting, then being refused
because the request is now delivered.

### Decisions where the brief was silent

- The order of checks in a transition is fixed: **404** if a client asks about another client's
  request (it doesn't reveal that the request exists), then **403** for the wrong role, then **409**
  for an invalid move or too few episodes.
- Only clients create requests. Admins can do everything operators can, but **cannot accept or reject**
  for a client: reviewing the delivery belongs to the client. Nothing can move back to `submitted`, and
  `accepted` is final.
- `episode_id` is uppercased, so `ep-00003` conflicts with `EP-00003`. `DD/MM/YYYY` is assumed (never
  `MM/DD`). Timestamps without a timezone are UTC.
- Extra import rules: a date more than one day in the future (`future_date`, e.g. the year 2031) and a
  duration over 3,600 s (`999999`) are skipped. Rows that are invalid don't take part in duplicate
  detection.
- Task names are normalised the same way for requests and episodes (`"  Pick Cup "` → `pick cup`), so
  they match. Assigning more than requested is allowed; delivery needs *at least* the requested count.
- Analytics: "requests by status" counts requests **created** in the range; the median uses the
  **first** delivery (a rework doesn't reset the clock); days are UTC days, both dates included.
- Users are deactivated, never deleted. An admin cannot deactivate or demote themselves, so there is
  always at least one active admin.
- The UI uses Ant Design (I first planned plain CSS, then chose a component library for a cleaner,
  more usable interface). Every rule is still enforced by the API; the UI only hides buttons.

## 2. Left out or simplified, and the next two days

**Left out:** a reason when a client rejects a delivery; admin user management in the web UI (it
exists in the API, at `/docs`); refresh tokens and logout that revokes a token; rate limiting on login;
automated frontend tests; the stretch item.

**Simplified:**
- The request list is loaded in one call and filtered in the browser, with no server pagination.
  Fine for hundreds of requests, not for tens of thousands.
- On every start the API re-imports `seed/episodes.csv` so reviewers have data immediately. It's
  idempotent, but it adds an `import_runs` row per restart.
- The CI workflow is written (build, tests, full stack started and smoke-tested), but GitHub Actions is
  blocked on my account by an unrelated billing lock, so it has only been run locally.

**With two more days**, in this order:
1. Rate limiting on login and an httpOnly cookie instead of `sessionStorage` (see Security).
2. A rejection reason stored on the status event, shown to the operator.
3. A daily summary table for analytics, and `COPY` into a staging table for large imports (see Scale).
4. Server-side pagination for the request list, and a few end-to-end browser tests.

## 3. Something that went wrong

While building with Claude Code, we checked that the concurrency test really protects the lock by
removing `FOR UPDATE` on purpose and running the tests. We expected one failure. Instead the whole
test run **hung** and never finished.

The failed test gave us the clue: the assertion "unassign should be blocked" failed as expected, but
after that nothing happened. The test opens one session that holds the row lock. When the assertion
failed, the test stopped before it closed that session, so the lock was never released. After every
test, a fixture empties the tables with `TRUNCATE`, and `TRUNCATE` waited for that lock forever.

The fix was a `try/finally` that always closes the locking session, even when the test fails. Now
removing the lock gives a clean failure message instead of a hang.

What I learned: a test is only useful if it **fails cleanly**. In CI, this bug would have looked like
a stuck job with no error at all. From then on we tested the tests by breaking the rule they protect
and checking that the right test fails. That is also how we found that the analytics query grouped
days in the database's timezone: the tests passed only because the test database runs in UTC. A new test sets
the session to `Africa/Kigali`, and it fails without `AT TIME ZONE 'UTC'`.

## 4. Security

- **Passwords:** bcrypt with a per-password salt, never stored in plain text. bcrypt only uses 72
  bytes, so longer passwords are refused on creation (422) and rejected on login (401, not a crash).
- **Tokens:** signed JWT (HS256), 8-hour expiry. The secret comes from the environment and the API
  refuses to start without one. The algorithm is fixed, so an unsigned `alg: none` token is rejected.
  The user is loaded from the database on every request, so a deactivated user or a changed role takes
  effect immediately, even with an old token.
- **Login:** the same message ("Invalid email or password") and similar timing for an unknown email,
  a wrong password and a deactivated account, so it doesn't reveal which emails exist.
- **Authorization** is checked in the service layer on the server, never trusted from the UI.
  Another client's request returns 404.
- **Input:** pydantic validates every body and query parameter; the CSV importer validates every
  field; uploads are limited to 100 MB; all SQL uses bound parameters. Errors never include stack
  traces, and logs record the path without the query string.

**The two vulnerabilities I would worry about most:**
1. **Stolen tokens.** The token is in `sessionStorage`, so any XSS bug could read it, and a JWT cannot
   be revoked before it expires (only deactivating the user stops it). Fix: an httpOnly, SameSite
   cookie, shorter expiry with refresh, and a Content Security Policy.
2. **Password guessing on `/auth/login`.** There is no rate limit or lockout, and the seed passwords are
   weak. Fix: rate limiting per IP and per account, and a stronger password policy.

## 5. Scale

Measured on my laptop with 200,000 generated episodes:

| | 1-month range | 1-year range |
|---|---|---|
| Episodes per day per robot | 12 ms (index) | 129 ms (full scan) |
| Top 5 tasks by good episodes | 4 ms (index) | 27 ms (full scan) |

Importing 200,000 rows takes about 14 s. The first version took 34 s; profiling showed parsing was
only 2.4 s, so we changed the insert to SQLAlchemy's executemany form.

**100× episodes (millions):** short analytics ranges stay fast because they use the `recorded_at`
indexes. Long ranges grow with the rows scanned, about 3 s for a year at 5 million. I would add a daily
summary table (day, robot, task, quality, count) updated by each import; episodes are append-only, so
it is easy to keep correct. The importer's first pass keeps one entry per id: we cut it from 143 MB to
62 MB per 200k ids by storing a hash instead of the values, but at 5 million that is still about 1.5 GB.
The next step is `COPY` into a staging table and doing the duplicate detection in SQL.

**10× users:** the first limits are the unpaginated request list, bcrypt CPU on login (deliberately
slow, about 0.2 s per attempt, on a single API process), and the database connection pool. I would
paginate the list on the server, run several API workers behind a load balancer (the API is stateless,
so this is easy), and put PgBouncer in front of Postgres.

## 6. AI tooling

I used **Claude Code** (in VS Code) for most of the implementation and **Amazon Q** for one styling pass
on the frontend.

How I worked: I wrote `CLAUDE.md` first, with my plan, the domain rules, the import decisions and
working rules (one phase at a time, every rule in the service layer and covered by a test, no commits
by the AI). For each phase, Claude Code proposed a short plan, I approved it, it built the phase, and I
reviewed the result, tested it myself (tests, `/docs`, the web app) and committed it. The Git history
follows those phases.

What it did: it wrote most of the code and tests, found problems in my first plan (for example, that
a single-pass import can't skip all rows of a conflict), ran the app in a headless browser to check
the UI, and drafted this NOTES.md from our work, which I then reviewed.

How I checked the output: every domain rule has tests (178 in total, against a real Postgres), the
important ones were "mutation-tested" by breaking the rule and confirming the right test fails, and I
walked through the full flow in the browser with every role. Many decisions started as suggestions
from Claude Code; I approved each one and can explain it, and I can explain each part of the code.
