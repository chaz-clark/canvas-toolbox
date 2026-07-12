"""Tier 1 unit tests — Canvas download locator (Sprint 1).

Source: lib/tools/_file_finder.py
Uses a tmp Downloads dir with controlled mtimes; asserts newest-first selection,
hint filtering, and that the globs match REAL observed export filenames.
"""
import os
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import _file_finder  # noqa: E402


def _touch(path: Path, mtime: float):
    path.write_text("x", encoding="utf-8")
    os.utime(path, (mtime, mtime))


# --- gradebook CSV ---------------------------------------------------------

def test_matches_real_gradebook_filename(tmp_path):
    # exact real-world name observed from a BYUI export
    _touch(tmp_path / "2026-07-12T1053_Grades-DS_250.csv", 1000)
    found = _file_finder.find_latest_gradebook_csv(downloads_dir=tmp_path)
    assert found is not None and found.name == "2026-07-12T1053_Grades-DS_250.csv"


def test_ignores_unrelated_csv(tmp_path):
    _touch(tmp_path / "budget.csv", 1000)
    assert _file_finder.find_latest_gradebook_csv(downloads_dir=tmp_path) is None


def test_returns_newest_gradebook(tmp_path):
    _touch(tmp_path / "2026-01-01T0900_Grades-DS_250.csv", 1000)
    _touch(tmp_path / "2026-07-12T1053_Grades-DS_250.csv", 2000)  # newer
    found = _file_finder.find_latest_gradebook_csv(downloads_dir=tmp_path)
    assert found.name == "2026-07-12T1053_Grades-DS_250.csv"


def test_name_hint_filters_by_course(tmp_path):
    _touch(tmp_path / "2026-07-12T1000_Grades-DS_250.csv", 1000)
    _touch(tmp_path / "2026-07-12T1100_Grades-CS_142.csv", 2000)  # newer, other course
    # without hint → newest (CS 142); with hint → DS 250
    assert _file_finder.find_latest_gradebook_csv(downloads_dir=tmp_path).name.endswith("CS_142.csv")
    ds = _file_finder.find_latest_gradebook_csv(downloads_dir=tmp_path, name_hint="DS_250")
    assert ds.name.endswith("DS_250.csv")


def test_list_gradebook_csvs_newest_first(tmp_path):
    _touch(tmp_path / "2026-01-01T0900_Grades-A.csv", 1000)
    _touch(tmp_path / "2026-07-01T0900_Grades-B.csv", 3000)
    _touch(tmp_path / "2026-03-01T0900_Grades-C.csv", 2000)
    names = [p.name for p in _file_finder.list_gradebook_csvs(downloads_dir=tmp_path)]
    assert names == [
        "2026-07-01T0900_Grades-B.csv",
        "2026-03-01T0900_Grades-C.csv",
        "2026-01-01T0900_Grades-A.csv",
    ]


# --- .imscc ----------------------------------------------------------------

def test_matches_real_imscc_hashname(tmp_path):
    _touch(tmp_path / "189dea1f71e04e7a9c2396b4fe4d16a6.imscc", 1000)
    found = _file_finder.find_latest_imscc(downloads_dir=tmp_path)
    assert found is not None and found.suffix == ".imscc"


def test_newest_imscc(tmp_path):
    _touch(tmp_path / "old.imscc", 1000)
    _touch(tmp_path / "new.imscc", 2000)
    assert _file_finder.find_latest_imscc(downloads_dir=tmp_path).name == "new.imscc"


# --- submissions ZIP -------------------------------------------------------

def test_matches_submissions_zip_variants(tmp_path):
    _touch(tmp_path / "submissions.zip", 1000)
    _touch(tmp_path / "assignment_123_submissions.zip", 2000)
    found = _file_finder.find_latest_submissions_zip(downloads_dir=tmp_path)
    assert found.name == "assignment_123_submissions.zip"
    assert len(_file_finder.list_submissions_zips(downloads_dir=tmp_path)) == 2


# --- edge cases ------------------------------------------------------------

def test_empty_dir_returns_none(tmp_path):
    assert _file_finder.find_latest_gradebook_csv(downloads_dir=tmp_path) is None
    assert _file_finder.find_latest_imscc(downloads_dir=tmp_path) is None
    assert _file_finder.find_latest_submissions_zip(downloads_dir=tmp_path) is None


def test_nonexistent_dir_returns_empty(tmp_path):
    missing = tmp_path / "does_not_exist"
    assert _file_finder.list_gradebook_csvs(downloads_dir=missing) == []
    assert _file_finder.find_latest_imscc(downloads_dir=missing) is None


# --- hard-stop require_* (offline runtime blocking) ------------------------

def test_require_returns_path_when_present(tmp_path):
    _touch(tmp_path / "2026-07-12T1053_Grades-DS_250.csv", 1000)
    got = _file_finder.require_gradebook_csv(downloads_dir=tmp_path)
    assert got.name.endswith("Grades-DS_250.csv")


def test_require_gradebook_raises_with_marker_and_guidance(tmp_path):
    with pytest.raises(_file_finder.OfflineDownloadMissing) as exc:
        _file_finder.require_gradebook_csv(downloads_dir=tmp_path)
    msg = str(exc.value)
    assert _file_finder.MISSING_MARKER in msg          # agent-legible marker
    assert "Grades → Export" in msg                     # actionable UI step
    assert "BLOCKED" in msg                             # signals hard stop


def test_require_imscc_and_submissions_raise_when_absent(tmp_path):
    with pytest.raises(_file_finder.OfflineDownloadMissing):
        _file_finder.require_imscc(downloads_dir=tmp_path)
    with pytest.raises(_file_finder.OfflineDownloadMissing):
        _file_finder.require_submissions_zip(downloads_dir=tmp_path)


def test_offline_download_missing_is_filenotfound():
    # callers may catch either type
    assert issubclass(_file_finder.OfflineDownloadMissing, FileNotFoundError)
