"""cb_snapshot — zip layout, Zone-2 exclusion, self-ignoring output dir."""
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import cb_snapshot  # noqa: E402

NOW = datetime(2026, 11, 16, 12, 0, 0, tzinfo=timezone.utc)


def _course(tmp_path):
    (tmp_path / "course" / "pages").mkdir(parents=True)
    (tmp_path / "course" / "pages" / "intro.md").write_text("hi")
    (tmp_path / "course" / "grading").mkdir()
    (tmp_path / "course" / "grading" / ".deid_master.csv").write_text("S-1,900003,Fake Name\n")
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "ferpa_zone2.txt").write_text(r"secret_roster\.csv" + "\n")
    (tmp_path / "course" / "secret_roster.csv").write_text("x")
    imscc = tmp_path / "x.imscc"
    imscc.write_bytes(b"PK-fake")
    return imscc


def test_zip_layout_and_zone2_exclusion(tmp_path):
    imscc = _course(tmp_path)
    out = cb_snapshot.build_snapshot("123", imscc, tmp_path / "course",
                                     tmp_path / "snapshots", tmp_path, NOW)
    assert out.name == "course-123-2026-11-16-120000.zip"
    with zipfile.ZipFile(out) as z:
        names = set(z.namelist())
        meta = json.loads(z.read("SNAPSHOT.json"))
    assert names == {"SNAPSHOT.json", "canvas/course.imscc", "local/course/pages/intro.md"}
    assert meta["local_files"] == 1
    assert meta["local_files_skipped_ferpa_zone2"] == 2  # built-in + course-listed


def test_output_dir_ignores_itself(tmp_path):
    imscc = _course(tmp_path)
    cb_snapshot.build_snapshot("123", imscc, None, tmp_path / "snapshots", tmp_path, NOW)
    assert (tmp_path / "snapshots" / ".gitignore").read_text() == "*\n"


def test_canvas_only(tmp_path):
    imscc = _course(tmp_path)
    out = cb_snapshot.build_snapshot("123", imscc, None, tmp_path / "s", tmp_path, NOW)
    with zipfile.ZipFile(out) as z:
        assert set(z.namelist()) == {"SNAPSHOT.json", "canvas/course.imscc"}
