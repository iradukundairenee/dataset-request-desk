"""CSV import of episode metadata.

Two passes over the file, both streaming (the file is never fully loaded):
  1. scan: parse every row and remember, per episode_id, the first valid line and
     its values, so we know which ids are duplicated and which conflict.
  2. insert: parse again and insert the rows we keep, in batches, with
     ON CONFLICT DO NOTHING so re-running the same file inserts nothing.
Two passes are needed because a conflicting duplicate can appear anywhere later
in the file, and then *every* row for that id must be skipped, including the first.
"""
import csv
import hashlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.errors import Invalid
from app.models import Episode, ImportRun, Quality
from app.services.normalise import normalise_task_name

EXPECTED_HEADER = [
    "episode_id",
    "robot_id",
    "task_name",
    "recorded_at",
    "duration_seconds",
    "operator_name",
    "quality",
]
KNOWN_ROBOTS = {"arm-01", "arm-02", "arm-03", "mobile-01", "humanoid-01"}
VALID_QUALITIES = {q.value for q in Quality}
MAX_DURATION_SECONDS = Decimal(3600)
FUTURE_TOLERANCE = timedelta(days=1)  # allow for clock/timezone differences
MAX_LENGTHS = {"episode_id": 50, "task_name": 200, "operator_name": 200}
BATCH_SIZE = 1000
MAX_ISSUES_LISTED = 500


class ImportFileError(Invalid):
    """The whole file is unusable (wrong header, not UTF-8, empty)."""


class RowError(Exception):
    """One row is skipped; `reason` is the code shown in the report."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


# --- pure parsing (no database) -------------------------------------------------


def parse_recorded_at(value):
    """Accepts ISO 8601 (with or without Z/offset, 'T' or space) and DD/MM/YYYY HH:MM.
    Naive timestamps are treated as UTC. Returns None if unparseable."""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        try:
            parsed = datetime.strptime(value, "%d/%m/%Y %H:%M")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_duration(value):
    """Positive number of seconds, at most MAX_DURATION_SECONDS. Returns None if invalid."""
    try:
        duration = Decimal(value)
    except InvalidOperation:
        return None
    if not duration.is_finite() or duration <= 0 or duration > MAX_DURATION_SECONDS:
        return None
    return duration.quantize(Decimal("0.01"))


def is_blank(fields):
    return len(fields) == 0 or (len(fields) == 1 and fields[0].strip() == "")


def parse_row(fields, now):
    """Normalise and validate one CSV row. Returns a dict ready to insert,
    or raises RowError with the reason it must be skipped."""
    if len(fields) != len(EXPECTED_HEADER):
        raise RowError("malformed_row")

    raw = dict(zip(EXPECTED_HEADER, (f.strip() for f in fields)))

    episode_id = raw["episode_id"].upper()
    if not episode_id:
        raise RowError("missing_episode_id")

    robot_id = raw["robot_id"].lower()
    if robot_id not in KNOWN_ROBOTS:
        raise RowError("unknown_robot")

    task_name = normalise_task_name(raw["task_name"])
    if not task_name:
        raise RowError("missing_task_name")

    quality = raw["quality"].lower()
    if quality not in VALID_QUALITIES:
        raise RowError("invalid_quality")

    recorded_at = parse_recorded_at(raw["recorded_at"])
    if recorded_at is None:
        raise RowError("invalid_date")
    if recorded_at > now + FUTURE_TOLERANCE:
        raise RowError("future_date")

    duration = parse_duration(raw["duration_seconds"])
    if duration is None:
        raise RowError("invalid_duration")

    operator_name = raw["operator_name"] or None

    row = {
        "episode_id": episode_id,
        "robot_id": robot_id,
        "task_name": task_name,
        "recorded_at": recorded_at,
        "duration_seconds": duration,
        "operator_name": operator_name,
        "quality": quality,
    }
    for field, max_length in MAX_LENGTHS.items():
        if row[field] is not None and len(row[field]) > max_length:
            raise RowError("value_too_long")
    return row


def fingerprint(row):
    """The values that must match for two rows to count as the same episode."""
    return tuple(row[field] for field in EXPECTED_HEADER)


# --- reading the file -----------------------------------------------------------


def read_rows(path):
    """Yield (line_number, fields) for every data row, after checking the header."""
    try:
        # utf-8-sig drops a byte-order mark if Excel added one.
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if header is None:
                raise ImportFileError("The file is empty")
            if [h.strip().lower() for h in header] != EXPECTED_HEADER:
                raise ImportFileError("Unexpected header; expected: " + ",".join(EXPECTED_HEADER))
            for fields in reader:
                # line_num is the physical line where this record ends (header is line 1).
                yield reader.line_num, fields
    except UnicodeDecodeError:
        raise ImportFileError("The file is not valid UTF-8")


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --- the import -----------------------------------------------------------------


class Report:
    def __init__(self):
        self.inserted = 0
        self.already_imported = 0
        self.blank_lines = 0
        self.skipped_by_reason = {}
        self.warnings = {}
        self.issues = []
        self.issue_count = 0

    def _add_issue(self, line, episode_id, reason):
        self.issue_count += 1
        if len(self.issues) < MAX_ISSUES_LISTED:
            self.issues.append({"line": line, "episode_id": episode_id or None, "reason": reason})

    def skip(self, line, episode_id, reason):
        self.skipped_by_reason[reason] = self.skipped_by_reason.get(reason, 0) + 1
        self._add_issue(line, episode_id, reason)

    def warn(self, line, episode_id, reason):
        self.warnings[reason] = self.warnings.get(reason, 0) + 1
        self._add_issue(line, episode_id, reason)

    def as_dict(self):
        return {
            "inserted": self.inserted,
            "already_imported": self.already_imported,
            "blank_lines": self.blank_lines,
            "skipped": sum(self.skipped_by_reason.values()),
            "skipped_by_reason": self.skipped_by_reason,
            "warnings": self.warnings,
            "issues": self.issues,
            "issues_truncated": self.issue_count > len(self.issues),
        }


def scan(path, now):
    """Pass 1: for each episode_id, the line of its first valid row, and the set
    of ids whose valid rows disagree with each other."""
    first_seen = {}  # episode_id -> (line, fingerprint)
    conflicting = set()
    for line, fields in read_rows(path):
        if is_blank(fields):
            continue
        try:
            row = parse_row(fields, now)
        except RowError:
            continue  # reported in pass 2
        episode_id = row["episode_id"]
        if episode_id not in first_seen:
            first_seen[episode_id] = (line, fingerprint(row))
        elif first_seen[episode_id][1] != fingerprint(row):
            conflicting.add(episode_id)
    first_line = {episode_id: line for episode_id, (line, _) in first_seen.items()}
    return first_line, conflicting


def insert_batch(db, batch, report):
    if not batch:
        return
    statement = (
        pg_insert(Episode.__table__)
        # Existing episodes are never modified: an assigned episode must not
        # silently change quality because a newer export says so.
        .on_conflict_do_nothing(index_elements=["episode_id"])
        .returning(Episode.episode_id)
    )
    # Passing the rows as a list lets SQLAlchemy compile the statement once and
    # send it as multi-row INSERTs; RETURNING tells us which rows were new.
    inserted = len(db.execute(statement, batch).all())
    report.inserted += inserted
    report.already_imported += len(batch) - inserted
    batch.clear()


def import_file(db, path, filename, started_by=None):
    """Import a CSV file and return the report dict. Runs in one transaction:
    either the whole file is imported (and the import_runs row saved) or nothing is."""
    now = datetime.now(timezone.utc)
    first_line, conflicting = scan(path, now)

    import_run = ImportRun(filename=filename, file_sha256=file_sha256(path), started_by=started_by)
    db.add(import_run)
    db.flush()

    report = Report()
    batch = []
    for line, fields in read_rows(path):
        if is_blank(fields):
            report.blank_lines += 1
            continue

        raw_id = fields[0].strip() if fields else None
        try:
            row = parse_row(fields, now)
        except RowError as error:
            report.skip(line, raw_id, error.reason)
            continue

        episode_id = row["episode_id"]
        if episode_id in conflicting:
            report.skip(line, episode_id, "conflicting_duplicate")
            continue
        if first_line[episode_id] != line:
            report.skip(line, episode_id, "duplicate_in_file")
            continue

        if row["operator_name"] is None:
            report.warn(line, episode_id, "missing_operator_name")

        batch.append({**row, "import_run_id": import_run.id})
        if len(batch) >= BATCH_SIZE:
            insert_batch(db, batch, report)
    insert_batch(db, batch, report)

    result = report.as_dict()
    import_run.counts = {k: v for k, v in result.items() if k not in ("issues", "issues_truncated")}
    import_run.issues = result["issues"]
    db.commit()
    result["import_run_id"] = import_run.id
    return result
