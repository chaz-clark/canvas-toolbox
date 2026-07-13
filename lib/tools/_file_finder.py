"""
Locate Canvas UI downloads for offline mode (Sprint 1).

Real export filename conventions (observed, 2026-07):
  gradebook CSV : '<ISO-ish timestamp>_Grades-<CourseCode>.csv'
                  e.g. '2026-07-12T1053_Grades-DS_250.csv'   (NO numeric course id)
  course export : '<32 hex>.imscc'
                  e.g. '189dea1f71e04e7a9c2396b4fe4d16a6.imscc' (NO course name)
  submissions   : 'submissions.zip' / '*ubmissions*.zip'
                  (pattern; not yet verified against a real sample — Sprint 3)

Neither the gradebook CSV nor the .imscc encodes the numeric course id, so these
finders return the NEWEST match by modification time and expose list_* helpers
so the calling tool can show the operator exactly which file it picked before a
destructive re-upload (gradebook import is irreversible via the UI). An optional
`name_hint` narrows by case-insensitive substring, e.g. a course code 'DS_250'.
"""
from pathlib import Path
from typing import Optional

DEFAULT_DOWNLOADS = Path.home() / "Downloads"

GRADEBOOK_GLOB = "*_Grades-*.csv"
IMSCC_GLOB = "*.imscc"
SUBMISSIONS_GLOB = "*ubmissions*.zip"  # matches submissions.zip and *_submissions.zip


def _sorted_by_mtime(paths) -> list[Path]:
    """Newest first. Missing files are skipped defensively."""
    existing = [p for p in paths if p.is_file()]
    return sorted(existing, key=lambda p: p.stat().st_mtime, reverse=True)


def _list(glob_pat: str, downloads_dir, name_hint: Optional[str]) -> list[Path]:
    d = Path(downloads_dir) if downloads_dir else DEFAULT_DOWNLOADS
    if not d.is_dir():
        return []
    matches = _sorted_by_mtime(d.glob(glob_pat))
    if name_hint:
        h = name_hint.lower()
        matches = [p for p in matches if h in p.name.lower()]
    return matches


# --- gradebook CSV ---------------------------------------------------------

def list_gradebook_csvs(downloads_dir=None, name_hint=None) -> list[Path]:
    return _list(GRADEBOOK_GLOB, downloads_dir, name_hint)


def find_latest_gradebook_csv(downloads_dir=None, name_hint=None) -> Optional[Path]:
    matches = list_gradebook_csvs(downloads_dir, name_hint)
    return matches[0] if matches else None


# --- .imscc course export --------------------------------------------------

def list_imscc(downloads_dir=None, name_hint=None) -> list[Path]:
    return _list(IMSCC_GLOB, downloads_dir, name_hint)


def find_latest_imscc(downloads_dir=None, name_hint=None) -> Optional[Path]:
    matches = list_imscc(downloads_dir, name_hint)
    return matches[0] if matches else None


# --- submissions ZIP -------------------------------------------------------

def list_submissions_zips(downloads_dir=None, name_hint=None) -> list[Path]:
    return _list(SUBMISSIONS_GLOB, downloads_dir, name_hint)


def find_latest_submissions_zip(downloads_dir=None, name_hint=None) -> Optional[Path]:
    matches = list_submissions_zips(downloads_dir, name_hint)
    return matches[0] if matches else None


# --- hard-stop requires (offline runtime) ----------------------------------
#
# In offline mode a missing download is a HARD STOP, not a soft None: grading /
# content operations cannot proceed until the operator downloads the file. The
# find_* helpers stay soft (return None) for probing; the require_* helpers
# below raise with an actionable, machine-legible message so the driving agent
# knows to PAUSE and prompt for the download rather than continue on empty data.

# Stable prefix so an agent can detect this condition programmatically in stderr.
MISSING_MARKER = "OFFLINE_DOWNLOAD_MISSING"

# kind -> (human label, glob, Canvas UI path to produce it)
_DOWNLOAD_SPECS = {
    "gradebook": (
        "Canvas gradebook CSV",
        GRADEBOOK_GLOB,
        "Grades → Export → Export Entire Gradebook",
    ),
    "imscc": (
        "Canvas course export (.imscc)",
        IMSCC_GLOB,
        "Settings → Export Course Content → Common Cartridge (.imscc)",
    ),
    "submissions": (
        "Canvas submissions ZIP",
        SUBMISSIONS_GLOB,
        "Assignment → Download Submissions",
    ),
}


class OfflineDownloadMissing(FileNotFoundError):
    """A required Canvas UI download is absent in offline mode.

    Hard stop: the caller must halt and prompt the operator to download the
    file — no grading/content work can proceed on missing data.
    """


def _require(kind, finder, downloads_dir, name_hint) -> Path:
    found = finder(downloads_dir, name_hint)
    if found is not None:
        return found
    label, glob_pat, ui_path = _DOWNLOAD_SPECS[kind]
    d = Path(downloads_dir) if downloads_dir else DEFAULT_DOWNLOADS
    hint = f" matching {name_hint!r}" if name_hint else ""
    raise OfflineDownloadMissing(
        f"{MISSING_MARKER}: {label} not found in {d} (pattern '{glob_pat}'{hint}).\n"
        f"  → Download from Canvas: {ui_path}\n"
        f"  → Save it to {d}, then re-run.\n"
        f"  Offline mode is BLOCKED until this file is present."
    )


def require_gradebook_csv(downloads_dir=None, name_hint=None) -> Path:
    return _require("gradebook", find_latest_gradebook_csv, downloads_dir, name_hint)


def require_imscc(downloads_dir=None, name_hint=None) -> Path:
    return _require("imscc", find_latest_imscc, downloads_dir, name_hint)


def require_submissions_zip(downloads_dir=None, name_hint=None) -> Path:
    return _require("submissions", find_latest_submissions_zip, downloads_dir, name_hint)
