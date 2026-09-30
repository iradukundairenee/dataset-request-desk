import subprocess
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models import Episode, ImportRun
from app.services import importer
from app.services.importer import ImportFileError, RowError, import_file, parse_recorded_at, parse_row
from tests.conftest import auth_header

SEED_CSV = "/seed/episodes.csv"
HEADER = "episode_id,robot_id,task_name,recorded_at,duration_seconds,operator_name,quality\n"
NOW = datetime(2026, 9, 30, tzinfo=timezone.utc)
GOOD_ROW = ["EP-1", "arm-01", "pick cup", "2026-08-01T10:00:00", "30", "Aline", "good"]


def row_with(**changes):
    fields = dict(zip(importer.EXPECTED_HEADER, GOOD_ROW))
    fields.update(changes)
    return list(fields.values())


def reason_for(fields):
    with pytest.raises(RowError) as error:
        parse_row(fields, NOW)
    return error.value.reason


def write_csv(tmp_path, body, name="episodes.csv"):
    path = tmp_path / name
    path.write_text(HEADER + body, encoding="utf-8")
    return str(path)


# --- parsing one row (pure functions, no database) -----------------------------


def test_good_row_is_normalised():
    row = parse_row(["  ep-7 ", " ARM-01", "  Pick   CUP ", "2026-08-01T10:00:00", "45.5", " Aline ", "GOOD"], NOW)
    assert row == {
        "episode_id": "EP-7",
        "robot_id": "arm-01",
        "task_name": "pick cup",
        "recorded_at": datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc),
        "duration_seconds": Decimal("45.50"),
        "operator_name": "Aline",
        "quality": "good",
    }


@pytest.mark.parametrize(
    "fields, reason",
    [
        (GOOD_ROW[:6], "malformed_row"),
        (GOOD_ROW + ["extra"], "malformed_row"),
        (row_with(episode_id="  "), "missing_episode_id"),
        (row_with(robot_id="arm-99"), "unknown_robot"),
        (row_with(robot_id=""), "unknown_robot"),
        (row_with(task_name="   "), "missing_task_name"),
        (row_with(quality="excellent"), "invalid_quality"),
        (row_with(quality=""), "invalid_quality"),
        (row_with(recorded_at="not a date"), "invalid_date"),
        (row_with(recorded_at="31/02/2026 10:00"), "invalid_date"),
        (row_with(recorded_at="2031-01-01T00:00:00"), "future_date"),
        (row_with(duration_seconds=""), "invalid_duration"),
        (row_with(duration_seconds="N/A"), "invalid_duration"),
        (row_with(duration_seconds="-5"), "invalid_duration"),
        (row_with(duration_seconds="0"), "invalid_duration"),
        (row_with(duration_seconds="NaN"), "invalid_duration"),
        (row_with(duration_seconds="999999"), "invalid_duration"),
        (row_with(task_name="x" * 201), "value_too_long"),
    ],
)
def test_invalid_rows_are_skipped_with_reason(fields, reason):
    assert reason_for(fields) == reason


def test_missing_operator_name_is_allowed_as_null():
    assert parse_row(row_with(operator_name=" "), NOW)["operator_name"] is None


@pytest.mark.parametrize(
    "value, expected",
    [
        ("2026-08-14T09:20:00", datetime(2026, 8, 14, 9, 20, tzinfo=timezone.utc)),
        ("2026-08-14T09:20:00Z", datetime(2026, 8, 14, 9, 20, tzinfo=timezone.utc)),
        ("2026-08-14T11:20:00+02:00", datetime(2026, 8, 14, 9, 20, tzinfo=timezone.utc)),
        ("2026-08-14 09:20:00", datetime(2026, 8, 14, 9, 20, tzinfo=timezone.utc)),
        ("14/08/2026 09:20", datetime(2026, 8, 14, 9, 20, tzinfo=timezone.utc)),  # DD/MM, never MM/DD
    ],
)
def test_accepted_date_formats(value, expected):
    assert parse_recorded_at(value) == expected


# --- the seed file --------------------------------------------------------------


def test_seed_file_counts_per_reason(db):
    report = import_file(db, SEED_CSV, "episodes.csv")

    assert report["inserted"] == 171
    assert report["already_imported"] == 0
    assert report["blank_lines"] == 2
    assert report["skipped_by_reason"] == {
        "conflicting_duplicate": 4,  # EP-00011 (bad vs good) and EP-00003 vs ep-00003
        "duplicate_in_file": 2,  # EP-00074, EP-00030 repeated identically
        "missing_episode_id": 1,
        "invalid_quality": 2,  # "excellent" and empty
        "invalid_duration": 4,  # empty, -5, N/A, 999999
        "future_date": 1,  # 2031
        "invalid_date": 1,  # "not a date"
        "unknown_robot": 2,  # arm-99 and empty
        "malformed_row": 1,  # 6 columns
    }
    assert report["warnings"] == {"missing_operator_name": 1}
    assert db.scalar(select(func.count()).select_from(Episode)) == 171


def test_seed_file_issues_have_line_numbers(db):
    issues = import_file(db, SEED_CSV, "episodes.csv")["issues"]
    assert {"line": 185, "episode_id": "EP-90001", "reason": "malformed_row"} in issues
    assert {"line": 3, "episode_id": "EP-00011", "reason": "conflicting_duplicate"} in issues
    assert {"line": 168, "episode_id": "EP-00011", "reason": "conflicting_duplicate"} in issues
    assert {"line": 50, "episode_id": "EP-00074", "reason": "duplicate_in_file"} in issues


def test_seed_file_values_are_normalised_in_db(db):
    import_file(db, SEED_CSV, "episodes.csv")

    def episode(episode_id):
        return db.scalar(select(Episode).where(Episode.episode_id == episode_id))

    assert episode("EP-00006").task_name == "pick cup"  # "  Pick Cup "
    assert episode("EP-00007").task_name == "pick cup"  # "PICK CUP"
    assert episode("EP-00008").robot_id == "arm-01"  # " arm-01"
    assert episode("EP-00009").quality.value == "good"  # "Good"
    assert episode("EP-00014").recorded_at == datetime(2026, 8, 14, 9, 15, tzinfo=timezone.utc)  # 14/08/2026
    assert episode("EP-00018").duration_seconds == Decimal("45.50")
    assert episode("EP-90002").task_name == "pick cup, then place"  # quoted comma
    assert episode("EP-90005").operator_name is None


def test_conflicting_duplicates_are_never_imported(db):
    import_file(db, SEED_CSV, "episodes.csv")
    for episode_id in ("EP-00011", "EP-00003"):
        assert db.scalar(select(Episode).where(Episode.episode_id == episode_id)) is None


# --- idempotency ----------------------------------------------------------------


def test_running_twice_inserts_nothing_the_second_time(db):
    import_file(db, SEED_CSV, "episodes.csv")
    second = import_file(db, SEED_CSV, "episodes.csv")

    assert second["inserted"] == 0
    assert second["already_imported"] == 171
    assert db.scalar(select(func.count()).select_from(Episode)) == 171
    assert db.scalar(select(func.count()).select_from(ImportRun)) == 2  # both runs are recorded


def test_reimport_never_changes_an_existing_episode(db, tmp_path):
    import_file(db, write_csv(tmp_path, "EP-1,arm-01,pick cup,2026-08-01T10:00:00,30,Aline,bad\n"), "a.csv")
    changed = write_csv(tmp_path, "EP-1,arm-01,pick cup,2026-08-01T10:00:00,30,Aline,good\n", "b.csv")

    report = import_file(db, changed, "b.csv")

    assert report["already_imported"] == 1
    db.expire_all()
    assert db.scalar(select(Episode.quality)).value == "bad"


def test_conflict_is_detected_even_when_rows_are_far_apart(db, tmp_path):
    # More than one batch between the two rows: the first must not have been inserted already.
    filler = "".join(f"EP-F{i},arm-01,pick cup,2026-08-01T10:00:00,30,Aline,good\n" for i in range(1500))
    body = "EP-X,arm-01,pick cup,2026-08-01T10:00:00,30,Aline,bad\n" + filler
    body += "EP-X,arm-01,pick cup,2026-08-01T10:00:00,30,Aline,good\n"

    report = import_file(db, write_csv(tmp_path, body), "far.csv")

    assert report["inserted"] == 1500
    assert report["skipped_by_reason"] == {"conflicting_duplicate": 2}
    assert db.scalar(select(Episode).where(Episode.episode_id == "EP-X")) is None


# --- whole-file problems --------------------------------------------------------


def test_wrong_header_rejects_whole_file(db, tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("id,robot,task\nEP-1,arm-01,pick cup\n")
    with pytest.raises(ImportFileError):
        import_file(db, str(path), "bad.csv")
    assert db.scalar(select(func.count()).select_from(ImportRun)) == 0


def test_byte_order_mark_is_accepted(db, tmp_path):
    path = tmp_path / "bom.csv"
    path.write_bytes(("﻿" + HEADER + ",".join(GOOD_ROW) + "\n").encode("utf-8"))
    assert import_file(db, str(path), "bom.csv")["inserted"] == 1


def test_issue_list_is_capped(db, tmp_path):
    body = "".join(f"EP-{i},arm-99,pick cup,2026-08-01T10:00:00,30,Aline,good\n" for i in range(600))
    report = import_file(db, write_csv(tmp_path, body), "many.csv")
    assert report["skipped_by_reason"] == {"unknown_robot": 600}
    assert len(report["issues"]) == 500
    assert report["issues_truncated"] is True


# --- volume ---------------------------------------------------------------------


def test_large_generated_file_imports_in_batches(db, tmp_path):
    path = tmp_path / "large.csv"
    with open(path, "w") as f:
        subprocess.run(["python", "/seed/generate_episodes.py", "20000"], stdout=f, check=True)

    report = import_file(db, str(path), "large.csv")

    assert report["inserted"] == 20000
    assert report["skipped"] == 0
    assert db.scalar(select(func.count()).select_from(Episode)) == 20000


# --- API endpoint ---------------------------------------------------------------


def post_csv(client, user, content):
    return client.post(
        "/episodes/import?filename=episodes.csv",
        content=content,
        headers={**auth_header(user), "Content-Type": "text/csv"},
    )


def test_operator_imports_through_api(client, db, operator):
    with open(SEED_CSV, "rb") as f:
        response = post_csv(client, operator, f.read())

    assert response.status_code == 200
    assert response.json()["inserted"] == 171
    run = db.scalar(select(ImportRun))
    assert (run.filename, run.started_by, len(run.file_sha256)) == ("episodes.csv", operator.id, 64)


def test_client_cannot_import(client, client_a):
    assert post_csv(client, client_a, HEADER).status_code == 403


def test_api_rejects_bad_header_with_422(client, operator):
    response = post_csv(client, operator, "not,a,valid,header\n")
    assert response.status_code == 422
    assert "Unexpected header" in response.json()["error"]["message"]


def test_api_rejects_oversized_upload_with_413(client, operator, monkeypatch):
    monkeypatch.setattr("app.routers.episodes.MAX_UPLOAD_BYTES", 10)
    response = post_csv(client, operator, HEADER)
    assert response.status_code == 413
