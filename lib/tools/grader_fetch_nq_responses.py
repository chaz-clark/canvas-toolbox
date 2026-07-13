"""grader_fetch_nq_responses.py — pull per-student responses from a New
Quiz via the Reporting API.

Closes the "New Quizzes responses are API-walled" gap for the one path
that ISN'T walled — `student_analysis` reports. Returns per-student
structured data including file-upload filenames + submission timestamps
+ per-item answers + per-item scores.

This is a FETCH PRIMITIVE — it doesn't decide grades. Consuming tools
(e.g. `grade_standups.py` in itm327-master, which originated this
pattern) apply assignment-specific bucket logic on top.

PIPELINE
  1. POST /api/quiz/v1/courses/{cid}/quizzes/{qid}/reports
     {"quiz_report": {"report_type": "student_analysis",
                      "includes_all_versions": true}}
     → 201 + progress object
  2. Poll /api/v1/progress/{pid} until workflow_state="completed"
  3. Fetch `results.url` (signed inst-fs URL; TTL ~24h)
  4. Parse the student_analysis CSV
  5. Return per-uid dict — never prints a name to stdout

FERPA NOTE
  The student_analysis CSV carries student NAMES (the `Name` column) and
  the per-question answers (which can themselves carry PII — essay text,
  uploaded filenames with personal naming conventions). The CSV is
  written to disk ONLY when `--csv-out` is set; the structured output
  defaults to uid-keyed with no `name` field (pass `--include-names`
  for review-surface generation that legitimately needs them).

USAGE
  uv run python lib/tools/grader_fetch_nq_responses.py \\
      --course-id 12345 --quiz-id 67890 --out responses.json

  # with filename-date extraction (for stand-up / weekly-screenshot quizzes)
  uv run python lib/tools/grader_fetch_nq_responses.py \\
      --course-id 12345 --quiz-id 67890 --out responses.json \\
      --extract-filename-dates

  # save the raw CSV too (inst-fs token expires ~24h — save it locally
  # for grading-workflow continuity)
  uv run python lib/tools/grader_fetch_nq_responses.py \\
      --course-id 12345 --quiz-id 67890 --out responses.json \\
      --csv-out responses.csv

  # force a fresh report (default reuses a cached CSV <24h old)
  uv run python lib/tools/grader_fetch_nq_responses.py \\
      --course-id 12345 --quiz-id 67890 --out responses.json \\
      --force-refresh

EXIT CODES
  0  fetched + parsed successfully
  1  setup / API error / report didn't complete in 80s
  2  parse error (CSV shape unexpected)

ORIGIN
  Pattern from chaz-clark/itm327-master tools/grade_standups.py (validated
  end-to-end 2026-06-16: 10/10 stand-up push success, no false positives).
  Issue #87.
"""
from __future__ import annotations

import argparse

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass  # No-op if _env_loader not available
import csv
import io
import json
import os
import re
import sys
import time
from datetime import datetime, date, timezone
from pathlib import Path

import requests

try:
    from __toolbox_version__ import __version__
except ImportError:
    __version__ = "0.0.0+unknown"

try:
    from _env_loader import load_env
    load_env()
except ImportError:
    pass

_TIMEOUT = 30
_POLL_INTERVAL_S = 2
_POLL_MAX_TRIES = 40  # 40 × 2s = 80s ceiling — matches itm327 reference

# Cache CSVs under XDG_CACHE_HOME / ~/.cache. inst-fs URLs expire ~24h
# so a per-course-quiz cache file gives us cheap reruns within a grading
# session without re-queueing reports.
_CACHE_DIR = Path(
    os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache")
) / "canvas-toolbox" / "nq-reports"
_CACHE_TTL_HOURS = 23  # one less than Canvas's ~24h to stay safely inside


# ---------------------------------------------------------------------------
# Filename-date patterns (inlined per #87 plan — fold into tool until a
# second consumer asks for the extractor as standalone)
# ---------------------------------------------------------------------------
# Priority order: first match wins.
#   Mac default:     "Screenshot 2026-06-05 at 11.36.00 AM.png"
#   Windows default: "Screenshot 2026-06-06 164807.png"
#   Generic:         any \bYYYY-MM-DD\b
#   Snipping-tool:   "Screenshot_select-area_20260606233450.png"
_FILENAME_DATE_PATTERNS = [
    re.compile(r"Screenshot\s+(\d{4})-(\d{1,2})-(\d{1,2})\s+at\s+\d", re.I),
    re.compile(r"Screenshot\s+(\d{4})-(\d{1,2})-(\d{1,2})\s+\d{6}", re.I),
    re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"),
    re.compile(r"_(\d{4})(\d{2})(\d{2})\d{4,6}"),
]


def parse_filename_date(filename: str) -> date | None:
    """Return a date if any pattern matches, else None.

    Coverage in the ITM 327 reference cohort (10 students, 2 OSes):
    ~70% caught via Mac + Windows patterns. Remainder were user-renamed
    files (e.g., 'Check_weather_DAG_3.png') — those fall back to the
    submitted_at timestamp in the consuming tool's grade decision."""
    if not filename:
        return None
    for rx in _FILENAME_DATE_PATTERNS:
        m = rx.search(filename)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                continue
    return None


def parse_canvas_ts(s: str) -> datetime | None:
    """Parse '2026-06-05 15:45:21 UTC' (the student_analysis CSV format)
    or ISO-8601 variants. Return aware UTC datetime."""
    if not s:
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S UTC", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# CSV cache (issue #87 plan: default-on cache; --no-cache opts out;
# --force-refresh ignores the cache)
# ---------------------------------------------------------------------------

def _cache_path(course_id: int, quiz_id: int) -> Path:
    return _CACHE_DIR / f"course-{course_id}-quiz-{quiz_id}.csv"


def _cache_fresh(p: Path) -> bool:
    if not p.exists():
        return False
    age_h = (time.time() - p.stat().st_mtime) / 3600
    return age_h < _CACHE_TTL_HOURS


# ---------------------------------------------------------------------------
# Canvas API
# ---------------------------------------------------------------------------

def _env_canvas() -> tuple[str, str]:
    tok = os.environ.get("CANVAS_API_TOKEN", "")
    base = os.environ.get("CANVAS_BASE_URL", "").rstrip("/")
    if base and not base.startswith("http"):
        base = "https://" + base
    return tok, base


def fetch_nq_report_csv(
    base: str, headers: dict, course_id: int, quiz_id: int,
) -> str:
    """Generate + poll + download the student_analysis report. Returns
    the CSV body as a string. Raises RuntimeError on failure."""
    r = requests.post(
        f"{base}/api/quiz/v1/courses/{course_id}/quizzes/{quiz_id}/reports",
        headers=headers,
        json={"quiz_report": {"report_type": "student_analysis",
                              "includes_all_versions": True}},
        timeout=_TIMEOUT,
    )
    if r.status_code >= 400:
        raise RuntimeError(
            f"NQ report POST returned {r.status_code}: {r.text[:200]}")
    body = r.json()
    if "progress" not in body:
        raise RuntimeError(f"NQ report POST: unexpected body {body!r}")
    pid = body["progress"]["id"]

    for _ in range(_POLL_MAX_TRIES):
        p = requests.get(
            f"{base}/api/v1/progress/{pid}",
            headers=headers, timeout=_TIMEOUT,
        ).json()
        state = p.get("workflow_state")
        if state == "completed":
            url = (p.get("results") or {}).get("url")
            if not url:
                raise RuntimeError(f"Progress {pid} completed but no results.url")
            csv_text = requests.get(url, timeout=_TIMEOUT).text
            return csv_text
        if state == "failed":
            raise RuntimeError(f"NQ report {pid} failed: {p.get('message')}")
        time.sleep(_POLL_INTERVAL_S)
    raise RuntimeError(
        f"NQ report {pid} did not complete in "
        f"{_POLL_MAX_TRIES * _POLL_INTERVAL_S}s")


# ---------------------------------------------------------------------------
# CSV parse — student_analysis shape
# ---------------------------------------------------------------------------

def _locate_static_columns(header: list[str]) -> dict[str, int]:
    """Locate the canonical per-student columns. The student_analysis CSV
    is laid out as: per-student metadata columns (Name, ID, Submitted,
    Attempt, ...) followed by per-question triples (ItemID, ItemType,
    <answer>, EarnedPoints, Status)."""
    found: dict[str, int] = {}
    for i, col in enumerate(header):
        c = (col or "").strip().lower()
        if c == "name" and "name" not in found:
            found["name"] = i
        elif c == "id" and "id" not in found:
            found["id"] = i
        elif c == "submitted" and "submitted" not in found:
            found["submitted"] = i
        elif c == "attempt" and "attempt" not in found:
            found["attempt"] = i
    return found


def _walk_question_columns(header: list[str]) -> list[dict]:
    """Walk the header and return one dict per question encountered.

    Each question's contribution to the header is the column quintuple
    (ItemID, ItemType, <question-text>, <answer-cells-or-similar>,
    EarnedPoints) — Canvas's actual layout varies a little so we anchor
    by ItemID markers and walk forward to the next ItemID / EOL."""
    questions: list[dict] = []
    n = len(header)
    i = 0
    while i < n:
        cell = (header[i] or "").strip()
        cl = cell.lower()
        # New question block starts at an "ItemID" header cell
        if cl == "item id" or cl == "itemid":
            block_start = i
            # Find the next ItemID / EarnedPoints terminator
            j = i + 1
            while j < n:
                nxt = (header[j] or "").strip().lower()
                if nxt in ("item id", "itemid"):
                    break
                j += 1
            block = list(range(block_start, j))
            # Inside the block, find ItemType + answer-column index
            item_type_idx = None
            earned_idx = None
            status_idx = None
            for k in block[1:]:
                c = (header[k] or "").strip().lower()
                if c in ("item type", "itemtype"):
                    item_type_idx = k
                elif c in ("earned points", "earnedpoints", "score"):
                    earned_idx = k
                elif c == "status":
                    status_idx = k
            # The "answer" column is conventionally the column just AFTER
            # ItemType (carries the student's response — filename / value /
            # essay text). If not found, fall back to the next non-meta cell.
            answer_idx = None
            if item_type_idx is not None and item_type_idx + 1 < n:
                answer_idx = item_type_idx + 1
                if answer_idx in (earned_idx, status_idx):
                    answer_idx = None
            questions.append({
                "header_text": (header[item_type_idx + 1] if item_type_idx and item_type_idx + 1 < n
                                else f"q{len(questions)+1}"),
                "item_id_col": block_start,
                "item_type_col": item_type_idx,
                "answer_col": answer_idx,
                "earned_col": earned_idx,
                "status_col": status_idx,
            })
            i = j
            continue
        i += 1
    return questions


def parse_student_analysis_csv(
    csv_text: str, *, extract_filename_dates: bool = False,
) -> dict[int, dict]:
    """Parse the student_analysis CSV into uid-keyed per-student dicts.

    Returns: {uid: {
        "name": str,               # raw; caller decides whether to retain
        "submitted_at": datetime,
        "attempt": int,
        "answers": {item_id: {"type": str, "value": str, "score": float}},
        "filenames": [str, ...],
        "filename_dates": [str, ...],   # ISO date strings (when extract_filename_dates)
    }}"""
    rows = list(csv.reader(io.StringIO(csv_text)))
    if not rows:
        return {}
    header = rows[0]
    static = _locate_static_columns(header)
    if "id" not in static:
        raise ValueError("student_analysis CSV missing required 'ID' column")
    questions = _walk_question_columns(header)

    out: dict[int, dict] = {}
    for row in rows[1:]:
        try:
            uid = int((row[static["id"]] or "").strip())
        except (ValueError, IndexError):
            continue
        name = row[static.get("name", -1)].strip() if "name" in static else ""
        submitted_raw = row[static.get("submitted", -1)] if "submitted" in static else ""
        submitted_at = parse_canvas_ts(submitted_raw)
        attempt_raw = row[static.get("attempt", -1)] if "attempt" in static else "1"
        try:
            attempt = int(attempt_raw)
        except (TypeError, ValueError):
            attempt = 1

        answers: dict[str, dict] = {}
        filenames: list[str] = []
        for q in questions:
            iid_col = q["item_id_col"]
            item_id = row[iid_col].strip() if iid_col < len(row) else ""
            if not item_id:
                continue
            qtype = (row[q["item_type_col"]].strip()
                     if q["item_type_col"] is not None and q["item_type_col"] < len(row)
                     else "")
            value = (row[q["answer_col"]] if q["answer_col"] is not None
                     and q["answer_col"] < len(row) else "") or ""
            value = value.strip()
            try:
                score = float(row[q["earned_col"]]) if (
                    q["earned_col"] is not None and q["earned_col"] < len(row)
                    and (row[q["earned_col"]] or "").strip()
                ) else None
            except (TypeError, ValueError):
                score = None
            answers[item_id] = {"type": qtype, "value": value, "score": score}
            if "file-upload" in qtype.lower():
                # File-upload cells are comma-separated filenames when
                # multiple files were uploaded for one question.
                for fn in (v.strip() for v in value.split(",")):
                    if fn:
                        filenames.append(fn)

        rec: dict = {
            "name": name,
            "submitted_at": submitted_at.isoformat() if submitted_at else None,
            "attempt": attempt,
            "answers": answers,
            "filenames": filenames,
        }
        if extract_filename_dates:
            dates = [parse_filename_date(fn) for fn in filenames]
            rec["filename_dates"] = [d.isoformat() for d in dates if d is not None]
        out[uid] = rec
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    force_utf8_console()  # Fix issue #123 — Windows cp1252 console crash

    ap = argparse.ArgumentParser(
        description=(
            "Pull per-student responses from a Canvas New Quiz via the "
            "Reporting API. Returns uid-keyed structured data including "
            "file-upload filenames, submitted_at, and per-item answers + "
            "scores. FERPA-safe by default (names omitted from output)."
        ),
    )
    ap.add_argument("--version", action="version",
                    version=f"canvas-toolbox {__version__}")
    ap.add_argument("--course-id", type=int, required=True,
                    help="Canvas course ID (the quiz lives here).")
    ap.add_argument("--quiz-id", type=int, required=True,
                    help="New Quiz ID (Quizzes.Next).")
    ap.add_argument("--out", required=True,
                    help="JSON output path (uid-keyed per-student dict).")
    ap.add_argument("--csv-out", default=None,
                    help="Also save the raw student_analysis CSV here "
                         "(inst-fs token expires ~24h; save locally for "
                         "grading-workflow continuity).")
    ap.add_argument("--extract-filename-dates", action="store_true",
                    help="Parse YYYY-MM-DD-style dates out of uploaded "
                         "filenames; add filename_dates[] per student.")
    ap.add_argument("--include-names", action="store_true",
                    help="Include student names in the JSON output. "
                         "OMITTED by default for FERPA discipline (uid is "
                         "the canonical Canvas identifier). Enable when "
                         "generating a review surface that needs names.")
    ap.add_argument("--no-cache", action="store_true",
                    help="Don't read or write the local CSV cache.")
    ap.add_argument("--force-refresh", action="store_true",
                    help="Ignore any cached CSV; request a fresh report.")
    args = ap.parse_args()

    tok, base = _env_canvas()
    if not tok or not base:
        print("Missing CANVAS_API_TOKEN or CANVAS_BASE_URL in .env",
              file=sys.stderr)
        return 1
    headers = {"Authorization": f"Bearer {tok}"}

    cache_p = _cache_path(args.course_id, args.quiz_id)
    use_cache = not args.no_cache
    csv_text: str | None = None

    if use_cache and not args.force_refresh and _cache_fresh(cache_p):
        csv_text = cache_p.read_text(encoding="utf-8")
        print(f"  using cached CSV: {cache_p}  "
              f"(age {(time.time() - cache_p.stat().st_mtime)/60:.0f} min)")
    else:
        print(f"  requesting fresh student_analysis report for "
              f"course={args.course_id} quiz={args.quiz_id}...")
        try:
            csv_text = fetch_nq_report_csv(base, headers,
                                           args.course_id, args.quiz_id)
        except RuntimeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        if use_cache:
            cache_p.parent.mkdir(parents=True, exist_ok=True)
            cache_p.write_text(csv_text, encoding="utf-8")

    if args.csv_out:
        Path(args.csv_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.csv_out).write_text(csv_text, encoding="utf-8")

    try:
        parsed = parse_student_analysis_csv(
            csv_text, extract_filename_dates=args.extract_filename_dates,
        )
    except ValueError as e:
        print(f"ERROR: parse failed: {e}", file=sys.stderr)
        return 2

    if not args.include_names:
        for rec in parsed.values():
            rec.pop("name", None)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(
        json.dumps(parsed, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"  parsed {len(parsed)} student rows -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
