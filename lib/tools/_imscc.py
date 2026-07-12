"""
Shared .imscc (Canvas Common Cartridge) helpers for offline course tooling.

Real-export facts (Genchi Genbutsu, 5 exports 2026-07 — see
lib/agents/knowledge/imscc_format_knowledge.md):
  - ZIP: imsmanifest.xml + course_settings/ (course_settings.xml, module_meta.xml,
    canvas_export.txt, context.xml, ...), per-item `g`+32hex dirs, wiki_content/,
    web_resources/, non_cc_assessments/, external_content/, lti_resource_links/.
  - Resource identifiers are `g` + 32 lowercase hex. PRESERVE them on any
    round-trip so Canvas re-import OVERWRITES in place instead of duplicating.
  - Dates are naive `YYYY-MM-DDThh:mm:ss` (UTC-implied, NO offset); `all_day_date`
    is `YYYY-MM-DD`. Shift by whole days and re-emit the SAME naive format.
  - Universal Canvas markers: course_settings/canvas_export.txt + context.xml.

Design: date-shift edits ONLY the text of known schedule-date tags, in place,
reading/writing the zip entry-by-entry. Non-XML entries and every other byte
(identifiers, structure, formatting) are copied verbatim.
"""
from __future__ import annotations

import re
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

IDENTIFIER_RE = re.compile(r"g[0-9a-f]{32}")
# A valid Canvas resource identifier is a single-letter prefix + 32 hex, with an
# optional `_suffix`. Verified across 1504 real ids (4 courses): prefixes `g`
# (1460) and `i` (44), e.g. `g<hex>`, `g<hex>_syllabus`, `i<hex>`. A
# human-readable id like `assignment_week1` — the silent-failure case — has no
# such shape and is rejected.
VALID_RESOURCE_ID_RE = re.compile(r"^[a-z][0-9a-f]{32}(_.*)?$")

_DT_FMT = "%Y-%m-%dT%H:%M:%S"
_D_FMT = "%Y-%m-%d"
_DT_VAL = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")
_D_VAL = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Course-SCHEDULE dates only. Deliberately excludes created_at / updated_at /
# submitted_at (metadata timestamps that must NOT move with the semester).
SCHEDULE_DATE_TAGS = (
    "due_at", "unlock_at", "lock_at", "all_day_date", "start_at", "conclude_at",
    "show_correct_answers_at", "hide_correct_answers_at", "peer_reviews_due_at",
)
_TRIGGER_FILES = {"course_settings/canvas_export.txt", "course_settings/context.xml"}


def parse_dt(value: str):
    """Parse a naive .imscc datetime or date; None if it isn't one (e.g. it
    carries a timezone offset — we don't touch those)."""
    v = value.strip()
    if _DT_VAL.match(v):
        return datetime.strptime(v, _DT_FMT)
    if _D_VAL.match(v):
        return datetime.strptime(v, _D_FMT)
    return None


def shift_value(value: str, days: int) -> str:
    """Shift a single date/datetime string by `days`, preserving its format.
    Values that aren't the naive Canvas format are returned unchanged."""
    v = value.strip()
    if _DT_VAL.match(v):
        return (datetime.strptime(v, _DT_FMT) + timedelta(days=days)).strftime(_DT_FMT)
    if _D_VAL.match(v):
        return (datetime.strptime(v, _D_FMT) + timedelta(days=days)).strftime(_D_FMT)
    return value


def shift_dates_in_text(text: str, days: int) -> tuple[str, int]:
    """Shift every schedule-date tag value in an XML string. Returns
    (new_text, number_of_dates_shifted)."""
    count = 0

    def repl(m):
        nonlocal count
        inner = m.group(2)
        shifted = shift_value(inner, days)
        if shifted != inner:
            count += 1
        return f"{m.group(1)}{shifted}{m.group(3)}"

    for tag in SCHEDULE_DATE_TAGS:
        text = re.sub(rf"(<{tag}>)([^<]*)(</{tag}>)", repl, text)
    return text, count


def adjust_dates_in_imscc(src_path, out_path, days: int) -> int:
    """Copy `src_path` to `out_path`, shifting every schedule date by `days`.
    Non-XML entries and all non-date bytes are copied verbatim (identifiers and
    structure preserved). Returns the count of dates shifted."""
    src_path, out_path = Path(src_path), Path(out_path)
    total = 0
    with zipfile.ZipFile(src_path) as zin, zipfile.ZipFile(
        out_path, "w", zipfile.ZIP_DEFLATED
    ) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.endswith(".xml"):
                new_text, n = shift_dates_in_text(data.decode("utf-8"), days)
                total += n
                data = new_text.encode("utf-8")
            zout.writestr(item, data)
    return total


def manifest_resource_identifiers(imsmanifest_text: str) -> list[str]:
    """The identifier of every <resource> in the manifest."""
    return re.findall(r"<resource\b[^>]*\bidentifier=\"([^\"]+)\"", imsmanifest_text)


def _date_constraint_issues(text: str, fname: str) -> list[str]:
    def get(tag):
        m = re.search(rf"<{tag}>([^<]+)</{tag}>", text)
        return parse_dt(m.group(1)) if m else None

    unlock, due, lock = get("unlock_at"), get("due_at"), get("lock_at")
    out = []
    if unlock and due and unlock > due:
        out.append(f"{fname}: unlock_at is after due_at")
    if due and lock and lock < due:
        out.append(f"{fname}: lock_at is before due_at")
    return out


def validate_imscc(path) -> list[str]:
    """Return a list of problems that would make Canvas import silently wrong or
    fail. Empty list = clean. Checks: valid ZIP, manifest present, Canvas trigger
    file present, resource identifiers are `g`+32hex, per-item date constraints."""
    path = Path(path)
    if not zipfile.is_zipfile(path):
        return [f"{path}: not a valid ZIP archive"]
    issues: list[str] = []
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        if "imsmanifest.xml" not in names:
            issues.append("missing imsmanifest.xml")
        if not (_TRIGGER_FILES & names):
            issues.append(
                "missing Canvas trigger (course_settings/canvas_export.txt or "
                "context.xml) — Canvas would import this as generic IMS CC"
            )
        if "imsmanifest.xml" in names:
            man = z.read("imsmanifest.xml").decode("utf-8", "ignore")
            bad = [r for r in manifest_resource_identifiers(man) if not VALID_RESOURCE_ID_RE.match(r)]
            if bad:
                issues.append(
                    f"{len(bad)} resource identifier(s) not Canvas `g`+32hex "
                    f"(e.g. {bad[0]!r}) — content may import silently missing"
                )
        for n in names:
            if n.endswith(".xml"):
                issues += _date_constraint_issues(z.read(n).decode("utf-8", "ignore"), n)
    return issues
