#!/usr/bin/env python3
"""
grader_fetch.py — the new Step 0. Fetches student submissions from Canvas
keyed by user_id (no name in filename), pre-populates .known_names.txt from
the FULL course roster (peer-mention scrub catches non-submitters too), and
by default CHAINS into deidentify + name_leak_check so a fresh
`grader_fetch.py` invocation lands at a fully-de-identified, leak-verified
`submissions_deid/` ready for grading.

Part of the canvas-toolbox generic grader skill (v1.0). See:
  - grading_readme.md (faculty-facing pipeline + canonical layout)
  - lib/agents/canvas_grader.md (agent-facing pipeline)
  - lib/agents/knowledge/grader_knowledge.md §1 (FERPA two-zone architecture)

WHY THIS EXISTS
  The pipeline's old Step 0 was a manual Canvas bulk-download, which
  arrives named `lastnamefirstname_<userid>_<subid>_<title>.ext`. Two
  costs the round-1 ds460 KC1 beta surfaced:

    1. **Manual work** for the instructor every cohort.
    2. **The editor IS the leak.** Those filenames carry student names;
       a single click on a raw file in the IDE injects a name into the
       AI context. Round-1 leaked a name via the IDE's "open file" notice.
       The de-id pipeline is clean; the *named raw files sitting on disk*
       are the hazard.

  The insight that makes this fixable: Canvas's submissions API returns
  `user_id` (a number, not a name) + the attachment URL. So the download
  can be automated AND the name kept out of the filename, the console,
  and the AI entirely.

WHAT IT DOES (default chain — opt out with --no-chain)
  1. Pre-populates `.known_names.txt` from the FULL course roster
     (GET /courses/:id/users?enrollment_type[]=student). This catches
     peer mentions of students who didn't submit too — round-1 KC1
     surfaced cases where a submitter named a non-submitting peer; the
     submitter-only roster missed them. --no-roster opts out.
  2. Lists the assignment's submissions via
     GET /courses/:id/assignments/:aid/submissions?include[]=user
        &include[]=submission_history
  3. For each actual submission (skips no-shows), downloads attachments
     to `<challenge-dir>/submissions_raw/<prefix>_<userid>.<ext>` — NO
     NAME in the filename, EVER.
  4. Fetches the display name from the included `user` object and uses
     it ONLY to:
       - write the local fetch keymap (`.fetch_log.json` — gitignored,
         never read by the AI)
       - append it to `.known_names.txt` (the peer-mention scrub roster,
         deduplicated, gitignored, never read by the AI)
  5. AUTO-CHAIN (default): detects the submission file type and runs:
       a. grader_deidentify_docx.py    (if .docx submissions)
       b. grader_deidentify_databricks.py  (if .html with Databricks marker)
     followed by grader_name_leak_check.py. Any leak surface beyond the
     known set → non-zero exit; the operator MUST investigate before
     letting the AI read submissions_deid/.
  6. Prints keys + counts ONLY. Never a name to stdout/stderr.

FERPA / SECURITY BOUNDARY — read this before changing anything
  * The student name is fetched from Canvas, used locally, and is NEVER
    printed, logged, written into a filename, or sent to any cloud
    surface. The .known_names.txt and .fetch_log.json files are
    gitignored by the scaffold/grading/.gitignore convention.
  * `print()` calls in this file MUST NOT include a student name. Always
    use the `<prefix>_<userid>` filename or the user_id alone.
  * Test Student validation: when --test-student-only is set, the tool
    only downloads submissions whose display name is exactly
    "Test Student" — the standard Canvas test-user. Use this on every
    new assignment FIRST to validate the path before fetching real
    cohort data.
  * Canvas user_id is an internal database number, not a SIS/student
    ID. Printing it is safe under FERPA (FERPA protects directory info
    + grades, not the LMS's own row IDs).

THE NEW STEP 0
  grader_fetch.py replaces the manual Canvas bulk-download. Everything
  downstream is unchanged: deidentify reads from submissions_raw/, push
  resolves the user_id from the filename via the existing regex.

USAGE
  # First run on a new assignment — validate on Test Student only
  uv run python lib/tools/grader_fetch.py \\
    --challenge-dir grading/kc1 \\
    --assignment-id 16958677 \\
    --prefix kc1 \\
    --test-student-only

  # Full cohort fetch (after Test Student validates clean)
  uv run python lib/tools/grader_fetch.py \\
    --challenge-dir grading/kc1 \\
    --assignment-id 16958677 \\
    --prefix kc1

  # Re-download a cohort (e.g., after late submissions came in)
  uv run python lib/tools/grader_fetch.py \\
    --challenge-dir grading/kc1 \\
    --assignment-id 16958677 \\
    --prefix kc1 \\
    --force

REQUIRES in .env: CANVAS_API_TOKEN, CANVAS_BASE_URL, CANVAS_COURSE_ID
(or pass --course-id).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

import requests

_TOOLS_DIR = Path(__file__).resolve().parent

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
_TEST_STUDENT_NAME = "Test Student"  # Canvas's standard test-user display name

# Map online_text_entry / online_url to deterministic local extensions so the
# downstream de-id tools can dispatch by file extension.
_NON_ATTACHMENT_EXT = {
    "online_text_entry": "html",  # Canvas wraps the body as HTML; deid_databricks handles
    "online_url": "url.txt",
}


def _env_canvas(course_id_override: str | None) -> tuple[str, str, str]:
    tok = os.environ.get("CANVAS_API_TOKEN", "")
    cid = course_id_override or os.environ.get("CANVAS_COURSE_ID", "")
    base = os.environ.get("CANVAS_BASE_URL", "").rstrip("/")
    if base and not base.startswith("http"):
        base = "https://" + base
    return tok, cid, base


def _ext_from_url_or_filename(url: str, fallback_filename: str = "") -> str:
    """Pick a file extension, preferring URL path, falling back to filename."""
    for candidate in (urllib.parse.urlparse(url).path, fallback_filename):
        if not candidate:
            continue
        name = os.path.basename(candidate)
        if "." in name:
            ext = name.rsplit(".", 1)[1].lower()
            # Strip any URL-style trailing junk like "?foo=bar"
            ext = re.sub(r"[^a-z0-9]+$", "", ext)
            if 1 <= len(ext) <= 8:
                return ext
    return "bin"


def fetch_roster(base: str, cid: str, headers: dict) -> list[dict]:
    """Paginate the full student roster for the course. Returns a list of
    {user_id, display_name} — used to pre-populate .known_names.txt so peer
    mentions of non-submitting students get scrubbed too.

    FERPA: this hits a Canvas-internal directory; display_name is returned for
    LOCAL use only. The caller writes names ONLY to the gitignored
    .known_names.txt — never to stdout, console, or any cloud surface."""
    roster: list[dict] = []
    page = 1
    while True:
        r = requests.get(
            f"{base}/api/v1/courses/{cid}/users",
            headers=headers,
            params={
                "per_page": 100,
                "page": page,
                "enrollment_type[]": "student",
                "enrollment_state[]": ["active", "invited"],
                "include[]": ["enrollments"],
            },
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        for u in batch:
            name = (u.get("name") or u.get("display_name") or "").strip()
            if name and name != _TEST_STUDENT_NAME:
                roster.append({"user_id": u.get("id"), "display_name": name})
        page += 1
    return roster


def fetch_assignment_metadata(base: str, cid: str, headers: dict, aid: str) -> dict:
    """One-call lookup of the assignment object so the tool can branch by
    submission_type (online_upload / online_text_entry / discussion_topic /
    online_quiz / etc.). Also surfaces discussion_topic.id and quiz_id for
    the alternate fetch paths."""
    r = requests.get(
        f"{base}/api/v1/courses/{cid}/assignments/{aid}",
        headers=headers, timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def fetch_discussion_view(base: str, cid: str, headers: dict, topic_id: str) -> dict:
    """Pull the threaded view of a discussion topic. Returns the dict with
    `view` (the tree of entries+replies) and `participants` (user list).
    One API call regardless of thread depth — Canvas's /view endpoint flattens
    nested replies into a single response."""
    r = requests.get(
        f"{base}/api/v1/courses/{cid}/discussion_topics/{topic_id}/view",
        headers=headers, timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def fetch_quiz_questions(base: str, cid: str, headers: dict, quiz_id: str) -> dict:
    """Pull the quiz's questions (id → {question_name, question_text,
    question_type, points_possible}) so submission_data can be rendered
    alongside the prompts the student answered. Paginated."""
    out: dict = {}
    page = 1
    while True:
        r = requests.get(
            f"{base}/api/v1/courses/{cid}/quizzes/{quiz_id}/questions",
            headers=headers,
            params={"per_page": 100, "page": page},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        for q in batch:
            out[q["id"]] = {
                "question_name": q.get("question_name", ""),
                "question_text": q.get("question_text", ""),
                "question_type": q.get("question_type", ""),
                "points_possible": q.get("points_possible", 0),
            }
        page += 1
    return out


def fetch_submissions(base: str, cid: str, headers: dict, aid: str) -> list[dict]:
    """Paginate all submissions for the assignment, including the user object."""
    subs: list[dict] = []
    page = 1
    while True:
        r = requests.get(
            f"{base}/api/v1/courses/{cid}/assignments/{aid}/submissions",
            headers=headers,
            params={
                "per_page": 100,
                "page": page,
                "include[]": ["user", "submission_history"],
            },
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        subs += batch
        page += 1
    return subs


def is_actual_submission(s: dict) -> bool:
    """Skip workflow_state=unsubmitted and anything with no real attempt."""
    if s.get("workflow_state") == "unsubmitted":
        return False
    if s.get("submitted_at") is None and s.get("attempt") is None:
        return False
    return True


def download_attachment(att: dict, headers: dict, out_path: Path) -> int:
    """Stream an attachment URL to disk; return bytes written. Canvas URLs are
    pre-signed but sending the bearer header is harmless and works on either."""
    url = att.get("url")
    if not url:
        return 0
    with requests.get(url, headers=headers, stream=True, timeout=_TIMEOUT) as r:
        r.raise_for_status()
        total = 0
        with out_path.open("wb") as f:
            for chunk in r.iter_content(chunk_size=64 * 1024):
                if chunk:
                    f.write(chunk)
                    total += len(chunk)
    return total


def write_body_file(body: str, out_path: Path) -> int:
    """For online_text_entry: write the body HTML to a file. Returns bytes."""
    data = (body or "").encode("utf-8")
    out_path.write_bytes(data)
    return len(data)


def flatten_discussion_view(view_payload: dict) -> dict[int, list[dict]]:
    """Recurse the threaded discussion view and return {user_id: [entries...]}
    aggregating top-level posts and replies per user. Entries are sorted by
    created_at within each user's list so the rendered submission reads
    chronologically. Deleted / empty / system entries are skipped."""
    per_user: dict[int, list[dict]] = {}

    def _walk(entries: list[dict]) -> None:
        for e in entries or []:
            uid = e.get("user_id")
            message = (e.get("message") or "").strip()
            if uid and message and message not in ("[deleted]", "<p>[deleted]</p>"):
                per_user.setdefault(uid, []).append({
                    "id": e.get("id"),
                    "parent_id": e.get("parent_id"),
                    "created_at": e.get("created_at", ""),
                    "message": message,
                })
            # Recurse into nested replies
            _walk(e.get("replies") or [])

    _walk(view_payload.get("view") or [])
    for uid, entries in per_user.items():
        entries.sort(key=lambda x: x.get("created_at") or "")
    return per_user


def render_discussion_html(entries: list[dict]) -> str:
    """Render one student's aggregated discussion entries as a single HTML
    body — preserves their post(s) + replies in chronological order, with
    a thin separator between posts. The text adapter will strip tags
    downstream; this just stitches the bodies."""
    parts = []
    for i, e in enumerate(entries, 1):
        kind = "Reply" if e.get("parent_id") else "Post"
        parts.append(
            f"<h2>{kind} {i}</h2>\n"
            f"<p><em>posted: {e.get('created_at', '')}</em></p>\n"
            f"{e['message']}\n"
        )
    return "<html><body>\n" + "\n<hr/>\n".join(parts) + "\n</body></html>\n"


def render_quiz_markdown(submission_data: list[dict], questions: dict, quiz_title: str) -> str:
    """Render one student's quiz submission_data as Markdown the grader can
    read. Joins each entry's question_id against the questions map to surface
    the prompt alongside the answer."""
    if not submission_data:
        return f"# Quiz: {quiz_title}\n\n_(No submission_data recorded for this student.)_\n"
    parts = [f"# Quiz: {quiz_title}\n"]
    for i, item in enumerate(submission_data, 1):
        qid = item.get("question_id")
        q = questions.get(qid) or {}
        qname = q.get("question_name", f"Question {i}")
        qtext = q.get("question_text", "").strip()
        qtype = q.get("question_type", "")
        parts.append(f"## Q{i}: {qname}")
        if qtype:
            parts.append(f"_(type: {qtype})_")
        if qtext:
            parts.append(qtext)
        # submission_data shapes vary by question_type — text/answer/correct/points
        ans_text = (item.get("text") or "").strip()
        if not ans_text:
            ans_text = str(item.get("answer", "")).strip()
        parts.append("\n**Student answer:**\n")
        parts.append(ans_text if ans_text else "_(blank)_")
        if "points" in item:
            parts.append(f"\n_(auto-points: {item.get('points')})_")
        parts.append("")
    return "\n".join(parts) + "\n"


def detect_adapter(raw_dir: Path) -> str:
    """Sniff submissions_raw/ and pick the right de-id adapter.
    Returns one of: 'docx', 'databricks', 'text', 'pdf', 'xlsx', 'jupyter',
    'mixed_or_unknown'.

    Rules (homogeneous extensions only; mixed types → mixed_or_unknown):
      - all .docx  → 'docx'
      - all .pdf   → 'pdf'
      - all .xlsx  → 'xlsx'
      - all .ipynb → 'jupyter'
      - all .txt or .md (or a mix of these two) → 'text'
      - all .html:
          * if EVERY .html file has __DATABRICKS_NOTEBOOK_MODEL → 'databricks'
          * if NO .html file has the marker → 'text' (online_text_entry bodies)
          * mixed (some have marker, some don't) → 'mixed_or_unknown'
      - any extension mix that doesn't fit above → 'mixed_or_unknown'
    """
    files = [p for p in raw_dir.iterdir() if p.is_file() and not p.name.startswith(".")]
    if not files:
        return "mixed_or_unknown"

    exts = {p.suffix.lower() for p in files}

    # Pure single-extension cases first
    if exts == {".docx"}:
        return "docx"
    if exts == {".pdf"}:
        return "pdf"
    if exts == {".xlsx"}:
        return "xlsx"
    if exts == {".ipynb"}:
        return "jupyter"
    if exts <= {".txt", ".md"}:  # subset — accepts pure .txt, pure .md, or mix
        return "text"

    # HTML — disambiguate databricks vs. text by sniffing each file
    if exts == {".html"} or exts == {".html", ".htm"}:
        html_files = [p for p in files if p.suffix.lower() in (".html", ".htm")]
        marker_count = 0
        for p in html_files:
            try:
                head = p.read_text(encoding="utf-8", errors="replace")[:200_000]
            except Exception:
                continue
            if "__DATABRICKS_NOTEBOOK_MODEL" in head:
                marker_count += 1
        if marker_count == len(html_files):
            return "databricks"
        if marker_count == 0:
            return "text"
        return "mixed_or_unknown"  # some have marker, some don't

    # Heterogeneous extensions (e.g. .docx + .pdf in one cohort) — operator
    # must split or pick explicitly.
    return "mixed_or_unknown"


def _run_chain(adapter: str, cd: Path, prefix: str) -> int:
    """Run deidentify → name_leak_check for the given adapter. Returns the
    subprocess exit code; non-zero on any step failure (caller propagates).
    Used by the discussion + quiz fetch branches where the adapter is known
    in advance (text); the default attachment-based fetch path inlines this
    logic with detect_adapter() instead."""
    tool_for_adapter = {
        "databricks": "grader_deidentify_databricks.py",
        "docx": "grader_deidentify_docx.py",
        "text": "grader_deidentify_text.py",
        "pdf": "grader_deidentify_pdf.py",
        "xlsx": "grader_deidentify_xlsx.py",
        "jupyter": "grader_deidentify_jupyter.py",
    }.get(adapter)
    if not tool_for_adapter:
        print(f"\nChain: unknown adapter {adapter!r}.", file=sys.stderr)
        return 4

    deid_cmd = [
        sys.executable, str(_TOOLS_DIR / tool_for_adapter),
        "--challenge-dir", str(cd),
        "--prefix", prefix.upper(),
    ]
    deid_rc = run_chain_step(f"deidentify ({adapter})", deid_cmd)
    if deid_rc != 0:
        print(f"\nChain stopped — deidentify exited {deid_rc}. submissions_deid/ "
              "may be incomplete. DO NOT let the AI read it until you've "
              "investigated and re-run successfully.", file=sys.stderr)
        return deid_rc

    leak_cmd = [
        sys.executable, str(_TOOLS_DIR / "grader_name_leak_check.py"),
        "--challenge-dir", str(cd),
    ]
    leak_rc = run_chain_step("name_leak_check", leak_cmd)
    if leak_rc != 0:
        print(f"\nChain stopped — name_leak_check exited {leak_rc}. A name "
              "slipped through deidentify. DO NOT let the AI read "
              "submissions_deid/ until you've added the missing name to "
              ".known_names.txt and re-run deidentify until leak_check "
              "exits 0.", file=sys.stderr)
        return leak_rc

    print("\nChain complete: submissions_deid/ ready for the grader.")
    return 0


def run_chain_step(name: str, cmd: list[str]) -> int:
    """Invoke a chained pipeline step as a subprocess and forward its output.
    Returns the subprocess exit code. Each step's own stdout/stderr already
    enforces the no-name-in-console contract — we just propagate."""
    print(f"\n── {name} ──")
    try:
        proc = subprocess.run(cmd, check=False)
    except FileNotFoundError as e:
        print(f"ERROR: could not invoke {name} ({e}). Chain aborted.",
              file=sys.stderr)
        return 127
    return proc.returncode


def update_known_names(path: Path, new_names: list[str]) -> int:
    """Append display names to .known_names.txt, dedup case-insensitively.
    Returns count of names added."""
    existing: set[str] = set()
    if path.exists():
        for ln in path.read_text(encoding="utf-8").splitlines():
            t = ln.strip()
            if t and not t.startswith("#"):
                existing.add(t.lower())
    added = 0
    with path.open("a", encoding="utf-8") as f:
        if not path.exists() or path.stat().st_size == 0:
            f.write("# Local-only — gitignored. Peer-mention scrub roster.\n"
                    "# Populated by grader_fetch.py; never read by the AI.\n")
        for n in new_names:
            t = (n or "").strip()
            if t and t.lower() not in existing:
                f.write(t + "\n")
                existing.add(t.lower())
                added += 1
    return added


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Fetch Canvas submissions for an assignment, keyed by user_id "
                    "(no name in any filename, console line, or AI surface). "
                    "Replaces the manual Canvas bulk-download as the new Step 0.")
    ap.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    ap.add_argument("--challenge-dir", required=True,
                    help="Convention base path (e.g. grading/kc1). Outputs land in "
                         "<challenge-dir>/submissions_raw/, .known_names.txt, "
                         ".fetch_log.json under here.")
    ap.add_argument("--assignment-id", required=True,
                    help="Canvas assignment ID to fetch submissions for.")
    ap.add_argument("--course-id", default=None,
                    help="Canvas course ID (default: env CANVAS_COURSE_ID).")
    ap.add_argument("--prefix", default=None,
                    help="Filename prefix (e.g. kc1, mr). Default: lowercased basename "
                         "of --challenge-dir.")
    ap.add_argument("--force", action="store_true",
                    help="Re-download files that already exist in submissions_raw/. "
                         "Default is idempotent skip.")
    ap.add_argument("--test-student-only", action="store_true",
                    help="FERPA-discipline: only download submissions whose display "
                         "name is 'Test Student'. Run this FIRST on every new "
                         "assignment to validate the path before fetching cohort data.")
    ap.add_argument("--no-roster", action="store_true",
                    help="Skip the default course-roster pre-fetch that populates "
                         ".known_names.txt with ALL enrolled students (peer-mention "
                         "scrub for non-submitters too). Default: roster fetch ON.")
    ap.add_argument("--no-chain", action="store_true",
                    help="Skip the default chain into deidentify + name_leak_check after "
                         "download. Default: chain ON — a single grader_fetch.py call "
                         "lands at a fully-de-identified, leak-verified state.")
    ap.add_argument("--deid-adapter",
                    choices=("auto", "databricks", "docx", "text", "pdf", "xlsx", "jupyter", "none"),
                    default="auto",
                    help="De-id adapter to chain into. Default 'auto' sniffs the file "
                         "types in submissions_raw/ and picks docx / databricks / text / "
                         "pdf / xlsx / jupyter. 'none' skips de-id even when --no-chain is not set.")
    args = ap.parse_args()

    tok, cid, base = _env_canvas(args.course_id)
    missing = [k for k, v in (("CANVAS_API_TOKEN", tok),
                              ("CANVAS_COURSE_ID", cid),
                              ("CANVAS_BASE_URL", base)) if not v]
    if missing:
        print(f"Missing env vars: {missing}. Set them in .env or pass --course-id.",
              file=sys.stderr)
        return 1

    cd = Path(args.challenge_dir)
    raw_dir = cd / "submissions_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    names_file = cd / ".known_names.txt"
    fetch_log = cd / ".fetch_log.json"
    prefix = (args.prefix or cd.name).lower().replace("_", "-")

    headers = {"Authorization": f"Bearer {tok}", "Accept": "application/json+canvas-string-ids"}

    # ── Pre-step: populate .known_names.txt from the full roster (default ON).
    # The submitter loop below adds submitter names too, but a non-submitter
    # whose name is MENTIONED inside another student's submission would miss
    # peer-mention scrubbing if we only had submitters. Fetch the full roster
    # FIRST so the scrub roster is comprehensive before deid runs.
    roster_added = 0
    if not args.no_roster and not args.test_student_only:
        try:
            roster = fetch_roster(base, cid, headers)
            roster_names = [r["display_name"] for r in roster]
            roster_added = update_known_names(names_file, roster_names) if roster_names else 0
            # FERPA: count only — no names in stdout. Roster size is operator-facing
            # but not student-identifying on its own (it's a course enrollment count).
            print(f"Roster pre-fetch: {len(roster)} enrolled students; "
                  f"{roster_added} new name(s) added to {names_file.name} "
                  f"(gitignored, never read by AI).")
        except requests.HTTPError as e:
            print(f"WARNING: roster pre-fetch failed (HTTP {e.response.status_code}); "
                  "peer-mention scrub may be incomplete. "
                  "Continuing with submitter-only roster.", file=sys.stderr)

    # ── Branch by submission_type. One up-front call to the assignment
    # endpoint tells us whether this is a regular attachment-based assignment,
    # a graded discussion (entries live in /discussion_topics/:tid/view),
    # or a quiz (per-item answers live in submission_data on the submission
    # history). The branch picks the right fetch path and writes the right
    # files into submissions_raw/ so the deid auto-chain picks the right
    # adapter.
    try:
        asg_meta = fetch_assignment_metadata(base, cid, headers, args.assignment_id)
    except requests.HTTPError as e:
        print(f"Canvas API error: {e.response.status_code} on assignment "
              f"{args.assignment_id} (metadata lookup). Check CANVAS_COURSE_ID + "
              "token scope.", file=sys.stderr)
        return 2

    sub_types = asg_meta.get("submission_types") or []

    # Discussion path — graded discussions store the gradeable content in the
    # discussion topic's entries (one entry per post; replies nested). We pull
    # the threaded /view, flatten per user_id, and write one .html file per
    # student containing their aggregated entries. Downstream the text adapter
    # picks this up (bare HTML, no Databricks marker).
    if "discussion_topic" in sub_types:
        topic_id = (asg_meta.get("discussion_topic") or {}).get("id")
        if not topic_id:
            print(f"Assignment {args.assignment_id} reports submission_type "
                  "discussion_topic but has no discussion_topic.id in the API "
                  "response. Cannot fetch entries.", file=sys.stderr)
            return 2
        try:
            view = fetch_discussion_view(base, cid, headers, str(topic_id))
        except requests.HTTPError as e:
            print(f"Canvas API error: {e.response.status_code} fetching "
                  f"discussion topic {topic_id} view.", file=sys.stderr)
            return 2

        per_user = flatten_discussion_view(view)
        new_names: list[str] = []
        fetch_log_data: dict = {
            "_warning": "FERPA — do NOT commit, do NOT let an AI read this. "
                        "Local re-identification only.",
            "assignment_id": str(args.assignment_id),
            "discussion_topic_id": str(topic_id),
            "course_id": str(cid),
            "prefix": prefix,
            "submission_type": "discussion_topic",
            "entries": {},
        }
        if fetch_log.exists():
            try:
                existing = json.loads(fetch_log.read_text(encoding="utf-8"))
                fetch_log_data["entries"].update(existing.get("entries", {}))
            except Exception:
                pass

        # Map participant user_id → display_name for known_names update
        participants = {p.get("id"): (p.get("display_name") or "").strip()
                        for p in (view.get("participants") or [])}

        ok = skipped = failed = test_student_count = 0
        for uid, entries in per_user.items():
            uid_s = str(uid)
            display_name = participants.get(uid, "")
            is_test_student = display_name == _TEST_STUDENT_NAME

            if args.test_student_only and not is_test_student:
                continue
            if is_test_student:
                test_student_count += 1

            fname = f"{prefix}_{uid_s}.html"
            out_path = raw_dir / fname
            if out_path.exists() and not args.force:
                skipped += 1
            else:
                try:
                    out_path.write_text(render_discussion_html(entries), encoding="utf-8")
                    ok += 1
                    print(f"  {uid_s}: {fname} (discussion, {len(entries)} entries)")
                except Exception as e:
                    print(f"  {uid_s}: SKIP — error ({type(e).__name__})")
                    failed += 1
                    continue

            if display_name and not is_test_student:
                new_names.append(display_name)
            fetch_log_data["entries"][uid_s] = {
                "name": display_name,
                "files": [fname],
                "entry_count": len(entries),
            }

        added = update_known_names(names_file, new_names) if new_names else 0
        fetch_log.write_text(
            json.dumps(fetch_log_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\nDiscussion fetch: {ok} students written, {skipped} skipped "
              f"(existing — use --force), {failed} failed. {added} new name(s) "
              f"appended to {names_file.name}.")
        if args.test_student_only:
            if test_student_count == 0:
                print("WARNING: --test-student-only set but no Test Student found "
                      "among discussion participants.", file=sys.stderr)
                return 3
            print(f"Test Student validation: {test_student_count} discussion file(s) "
                  "written. Inspect, then re-run without --test-student-only.")
            return 0 if failed == 0 else 2

        # Auto-chain (discussion files are .html bare → text adapter)
        if args.no_chain or args.deid_adapter == "none":
            print("\nChain skipped (--no-chain or --deid-adapter none).")
            return 0 if failed == 0 else 2
        adapter = args.deid_adapter if args.deid_adapter != "auto" else "text"
        # The discussion fetch always produces bare HTML — text is the right
        # adapter unless the operator overrides.
        chain_rc = _run_chain(adapter, cd, prefix)
        return chain_rc if chain_rc else (0 if failed == 0 else 2)

    # Quiz path — Classic quizzes (or NWQ→Classic-mirrored) store per-item
    # answers in submission_data on the submission history. We fetch the
    # quiz questions ONCE, then iterate submissions, rendering each student's
    # Q+A pairs to a single .md file. Downstream the text adapter picks this up.
    if "online_quiz" in sub_types:
        quiz_id = asg_meta.get("quiz_id")
        if not quiz_id:
            print(f"Assignment {args.assignment_id} reports submission_type "
                  "online_quiz but has no quiz_id in the API response.",
                  file=sys.stderr)
            return 2
        try:
            questions = fetch_quiz_questions(base, cid, headers, str(quiz_id))
            subs = fetch_submissions(base, cid, headers, args.assignment_id)
        except requests.HTTPError as e:
            print(f"Canvas API error: {e.response.status_code} fetching quiz "
                  f"{quiz_id} questions or submissions.", file=sys.stderr)
            return 2

        quiz_title = asg_meta.get("name", f"Quiz {quiz_id}")
        new_names: list[str] = []
        fetch_log_data = {
            "_warning": "FERPA — do NOT commit, do NOT let an AI read this. "
                        "Local re-identification only.",
            "assignment_id": str(args.assignment_id),
            "quiz_id": str(quiz_id),
            "course_id": str(cid),
            "prefix": prefix,
            "submission_type": "online_quiz",
            "entries": {},
        }
        if fetch_log.exists():
            try:
                existing = json.loads(fetch_log.read_text(encoding="utf-8"))
                fetch_log_data["entries"].update(existing.get("entries", {}))
            except Exception:
                pass

        ok = skipped = failed = test_student_count = 0
        for s in subs:
            if not is_actual_submission(s):
                continue
            uid = s.get("user_id")
            if not uid:
                continue
            uid_s = str(uid)
            display_name = ((s.get("user") or {}).get("display_name") or "").strip()
            is_test_student = display_name == _TEST_STUDENT_NAME

            if args.test_student_only and not is_test_student:
                continue
            if is_test_student:
                test_student_count += 1

            # submission_data is on the most-recent submission_history attempt
            # (or on the top-level submission for single-attempt quizzes).
            sub_data = s.get("submission_data")
            if not sub_data:
                hist = s.get("submission_history") or []
                if hist:
                    sub_data = hist[-1].get("submission_data")

            fname = f"{prefix}_{uid_s}.md"
            out_path = raw_dir / fname
            if out_path.exists() and not args.force:
                skipped += 1
            else:
                try:
                    out_path.write_text(
                        render_quiz_markdown(sub_data or [], questions, quiz_title),
                        encoding="utf-8",
                    )
                    ok += 1
                    print(f"  {uid_s}: {fname} (quiz, {len(sub_data or [])} answers)")
                except Exception as e:
                    print(f"  {uid_s}: SKIP — error ({type(e).__name__})")
                    failed += 1
                    continue

            if display_name and not is_test_student:
                new_names.append(display_name)
            fetch_log_data["entries"][uid_s] = {
                "name": display_name,
                "files": [fname],
                "answer_count": len(sub_data or []),
                "submission_id": s.get("id"),
            }

        added = update_known_names(names_file, new_names) if new_names else 0
        fetch_log.write_text(
            json.dumps(fetch_log_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\nQuiz fetch: {ok} students written, {skipped} skipped "
              f"(existing — use --force), {failed} failed. {added} new name(s) "
              f"appended to {names_file.name}.")
        if args.test_student_only:
            if test_student_count == 0:
                print("WARNING: --test-student-only set but no Test Student "
                      "submission found.", file=sys.stderr)
                return 3
            print(f"Test Student validation: {test_student_count} quiz file(s) "
                  "written. Inspect, then re-run without --test-student-only.")
            return 0 if failed == 0 else 2

        # Auto-chain (quiz files are .md → text adapter)
        if args.no_chain or args.deid_adapter == "none":
            print("\nChain skipped (--no-chain or --deid-adapter none).")
            return 0 if failed == 0 else 2
        adapter = args.deid_adapter if args.deid_adapter != "auto" else "text"
        chain_rc = _run_chain(adapter, cd, prefix)
        return chain_rc if chain_rc else (0 if failed == 0 else 2)

    # ── Default path: regular attachment-based assignments (online_upload,
    # online_text_entry, online_url) — what grader_fetch shipped with.
    try:
        subs = fetch_submissions(base, cid, headers, args.assignment_id)
    except requests.HTTPError as e:
        print(f"Canvas API error: {e.response.status_code} on assignment "
              f"{args.assignment_id}. Check CANVAS_COURSE_ID + token scope.",
              file=sys.stderr)
        return 2

    new_names: list[str] = []
    fetch_log_data: dict = {
        "_warning": "FERPA — do NOT commit, do NOT let an AI read this. "
                    "Local re-identification only.",
        "assignment_id": str(args.assignment_id),
        "course_id": str(cid),
        "prefix": prefix,
        "entries": {},  # user_id -> {name, files: [filename, ...], submission_id}
    }
    if fetch_log.exists():
        try:
            existing = json.loads(fetch_log.read_text(encoding="utf-8"))
            fetch_log_data["entries"].update(existing.get("entries", {}))
        except Exception:
            pass  # corrupt log — start fresh, don't crash

    ok = skipped = failed = test_student_count = 0

    for s in subs:
        if not is_actual_submission(s):
            continue

        user_id = s.get("user_id")
        if not user_id:
            continue
        user_id_s = str(user_id)

        display_name = ((s.get("user") or {}).get("display_name") or "").strip()
        is_test_student = display_name == _TEST_STUDENT_NAME

        if args.test_student_only and not is_test_student:
            continue

        if is_test_student:
            test_student_count += 1

        # Resolve attachments. The submission_types field tells us what to expect.
        sub_type = s.get("submission_type") or ""
        attachments = s.get("attachments") or []
        files_for_user: list[str] = []

        if attachments:
            # Multiple attachments: suffix _a, _b, _c …
            suffixes = ([""] if len(attachments) == 1
                        else [f"_{chr(ord('a') + i)}" for i in range(len(attachments))])
            for att, suf in zip(attachments, suffixes):
                ext = _ext_from_url_or_filename(att.get("url", ""), att.get("filename", ""))
                fname = f"{prefix}_{user_id_s}{suf}.{ext}"
                out_path = raw_dir / fname
                if out_path.exists() and not args.force:
                    skipped += 1
                    files_for_user.append(fname)
                    continue
                try:
                    download_attachment(att, headers, out_path)
                    files_for_user.append(fname)
                    ok += 1
                    # FERPA: print user_id + filename, NEVER the name
                    print(f"  {user_id_s}: {fname}")
                except requests.HTTPError as e:
                    print(f"  {user_id_s}: SKIP — HTTP {e.response.status_code} on attachment")
                    failed += 1
                except Exception as e:
                    # Never let a traceback print a name — report by user_id only
                    print(f"  {user_id_s}: SKIP — error ({type(e).__name__})")
                    failed += 1

        elif sub_type == "online_text_entry":
            body = s.get("body") or ""
            ext = _NON_ATTACHMENT_EXT["online_text_entry"]
            fname = f"{prefix}_{user_id_s}.{ext}"
            out_path = raw_dir / fname
            if out_path.exists() and not args.force:
                skipped += 1
                files_for_user.append(fname)
            else:
                try:
                    write_body_file(body, out_path)
                    files_for_user.append(fname)
                    ok += 1
                    print(f"  {user_id_s}: {fname} (text_entry)")
                except Exception as e:
                    print(f"  {user_id_s}: SKIP — error ({type(e).__name__})")
                    failed += 1

        elif sub_type == "online_url":
            url = s.get("url") or ""
            ext = _NON_ATTACHMENT_EXT["online_url"]
            fname = f"{prefix}_{user_id_s}.{ext}"
            out_path = raw_dir / fname
            if out_path.exists() and not args.force:
                skipped += 1
                files_for_user.append(fname)
            else:
                try:
                    out_path.write_text(url + "\n", encoding="utf-8")
                    files_for_user.append(fname)
                    ok += 1
                    print(f"  {user_id_s}: {fname} (online_url)")
                except Exception as e:
                    print(f"  {user_id_s}: SKIP — error ({type(e).__name__})")
                    failed += 1

        else:
            # No attachments and no recognized text/url submission type — log + skip.
            # FERPA: still no name in the log line.
            print(f"  {user_id_s}: SKIP — no attachments, type={sub_type or 'none'}")
            failed += 1
            continue

        if display_name and not is_test_student:
            new_names.append(display_name)

        fetch_log_data["entries"][user_id_s] = {
            "name": display_name,
            "files": files_for_user,
            "submission_id": s.get("id"),
        }

    # Update .known_names.txt (peer-mention scrub roster) — dedup case-insensitively
    added = update_known_names(names_file, new_names) if new_names else 0

    # Write .fetch_log.json (gitignored, never read by AI; for operator audit only)
    fetch_log.write_text(
        json.dumps(fetch_log_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Final summary — FERPA: counts only, never a name
    print(f"\n{ok} downloaded, {skipped} skipped (existing — use --force), "
          f"{failed} failed. {added} new submitter-name(s) appended to "
          f"{names_file.name} (gitignored, never read by AI).")
    if args.test_student_only:
        if test_student_count == 0:
            print("WARNING: --test-student-only set but no Test Student submission "
                  "found. Confirm a Test Student exists in the course AND has "
                  "submitted to this assignment.", file=sys.stderr)
            return 3
        print(f"Test Student validation: {test_student_count} submission(s) fetched. "
              "Inspect the file(s) in submissions_raw/, then re-run without "
              "--test-student-only to fetch the cohort.")
        # Skip chain on test-student-only runs — validation pass, not full pipeline.
        return 0 if failed == 0 else 2

    fetch_exit = 0 if failed == 0 else 2

    # ── Default chain: deidentify (auto-detect adapter) → name_leak_check.
    # FERPA: stops on any non-zero exit so the operator MUST investigate before
    # the AI sees anything. The chain's own console output already enforces
    # no-names-in-console — we just forward exit codes.
    if args.no_chain or args.deid_adapter == "none":
        print("\nChain skipped (--no-chain or --deid-adapter none). Run deidentify "
              "and grader_name_leak_check manually before letting any AI read "
              "submissions_deid/.")
        return fetch_exit

    if ok == 0 and skipped == 0:
        # Nothing fetched and nothing pre-existing — no de-id work to do.
        return fetch_exit

    adapter = args.deid_adapter if args.deid_adapter != "auto" else detect_adapter(raw_dir)
    if adapter == "mixed_or_unknown":
        print("\nChain: could not auto-detect a single de-id adapter for "
              f"{raw_dir.name}/. Mixed file types, mixed HTML (some Databricks, "
              "some bare), or an extension we don't handle. "
              "Pass --deid-adapter databricks | docx | text | pdf | xlsx to "
              "choose, or --no-chain to skip and run the right adapter manually.",
              file=sys.stderr)
        return 4

    tool_for_adapter = {
        "databricks": "grader_deidentify_databricks.py",
        "docx": "grader_deidentify_docx.py",
        "text": "grader_deidentify_text.py",
        "pdf": "grader_deidentify_pdf.py",
        "xlsx": "grader_deidentify_xlsx.py",
        "jupyter": "grader_deidentify_jupyter.py",
    }[adapter]
    deid_cmd = [
        sys.executable, str(_TOOLS_DIR / tool_for_adapter),
        "--challenge-dir", str(cd),
        "--prefix", prefix.upper(),
    ]
    deid_rc = run_chain_step(f"deidentify ({adapter})", deid_cmd)
    if deid_rc != 0:
        print(f"\nChain stopped — deidentify exited {deid_rc}. submissions_deid/ "
              "may be incomplete. DO NOT let the AI read it until you've "
              "investigated and re-run successfully.", file=sys.stderr)
        return deid_rc

    leak_cmd = [
        sys.executable, str(_TOOLS_DIR / "grader_name_leak_check.py"),
        "--challenge-dir", str(cd),
    ]
    leak_rc = run_chain_step("name_leak_check", leak_cmd)
    if leak_rc != 0:
        print(f"\nChain stopped — name_leak_check exited {leak_rc}. A name slipped "
              "through deidentify. DO NOT let the AI read submissions_deid/ "
              "until you've added the missing name to .known_names.txt and "
              "re-run deidentify until leak_check exits 0.", file=sys.stderr)
        return leak_rc

    print("\nChain complete: roster pre-fetched → submissions fetched (keyed by "
          "user_id) → deidentified → name leak check PASSED. "
          "submissions_deid/ is ready for the grader.")
    return fetch_exit


if __name__ == "__main__":
    sys.exit(main())
