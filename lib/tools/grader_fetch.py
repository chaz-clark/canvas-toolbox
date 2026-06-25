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
import csv
import json
import os
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path
from _challenge_dir_guard import resolve_challenge_dir  # issue #44 FERPA guard

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

# Reuse the deterministic SHA-256 key derivation used by every de-id adapter.
# That guarantees the key written to _existing_grades.csv at fetch time
# matches the key the agent sees in _grader<n>.csv / consensus output later.
# Lazy import: grader_fetch is callable for --help / --version without the
# adapter present.
try:
    from grader_deidentify_databricks import key_for as _key_for
except ImportError:  # pragma: no cover — adapter missing is a packaging failure
    _key_for = None  # type: ignore[assignment]

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
                # Issue #94 (FERPA): include dropped + completed students so
                # their names land in .known_names.txt as scrub terms. A
                # student who dropped mid-semester (state: completed/inactive)
                # may still have submissions OR be named in a TA comment;
                # an active-only roster leaks those names past the scrub.
                "enrollment_state[]": ["active", "invited", "inactive", "completed"],
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


def group_context_for_fetch_log(
    group_map: dict[int, dict],
    gcat_id,
    grade_individually: bool,
) -> dict | None:
    """Issue #100: produce a JSON-serializable group_context block to embed
    in .fetch_log.json. Returns None if not a group assignment.

    Consumers (reidentify + push) read this block to look up a user's group
    + co-members so feedback files can be mirrored to group-mates (shared
    grade mode) and push rows can be collapsed appropriately.
    """
    if not group_map:
        return None
    try:
        gcat_int = int(gcat_id) if gcat_id else None
    except (TypeError, ValueError):
        gcat_int = None
    return {
        "group_category_id": gcat_int,
        "grade_group_students_individually": bool(grade_individually),
        "user_to_group": {
            # JSON-serializable: stringify the int user_id key
            str(uid): {
                "group_id": ctx["group_id"],
                "group_name": ctx["group_name"],
                "member_user_ids": list(ctx["member_user_ids"]),
            }
            for uid, ctx in group_map.items()
        },
    }


def fetch_group_category_groups(
    base: str, headers: dict, group_category_id: int, timeout: int = _TIMEOUT
) -> list[dict]:
    """Issue #100: list groups in a Canvas group category.

    Paginates via `?per_page=100&page=N`. Returns the raw group dicts
    (each has id, name, members_count, group_category_id, etc.).
    """
    out: list[dict] = []
    page = 1
    while True:
        r = requests.get(
            f"{base}/api/v1/group_categories/{group_category_id}/groups",
            headers=headers,
            params={"per_page": 100, "page": page},
            timeout=timeout,
        )
        r.raise_for_status()
        batch = r.json() or []
        if not batch:
            break
        out += batch
        page += 1
    return out


def fetch_group_members(
    base: str, headers: dict, group_id: int, timeout: int = _TIMEOUT
) -> list[dict]:
    """Issue #100: list users in a Canvas group.

    Paginates via `?per_page=100&page=N`. Returns user dicts (each has
    id, name, sortable_name, etc. — caller must NOT log these
    name-bearing fields per FERPA).
    """
    out: list[dict] = []
    page = 1
    while True:
        r = requests.get(
            f"{base}/api/v1/groups/{group_id}/users",
            headers=headers,
            params={"per_page": 100, "page": page},
            timeout=timeout,
        )
        r.raise_for_status()
        batch = r.json() or []
        if not batch:
            break
        out += batch
        page += 1
    return out


def write_unique_group_memos_md(challenge_dir: Path, content: str) -> Path:
    """Issue #100: write UNIQUE_GROUP_MEMOS.md to the challenge dir.

    FERPA-safe: contains only user_ids + group names + group ids — no
    student names. Gitignored per the per-challenge-artifact convention.
    """
    out = challenge_dir / "UNIQUE_GROUP_MEMOS.md"
    out.write_text(content, encoding="utf-8")
    return out


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


def needs_refetch(
    local_exists: bool,
    recorded_attempt: object,
    remote_attempt: object,
    recorded_submitted_at: object,
    remote_submitted_at: object,
) -> bool:
    """Issue #103: decide whether a previously-downloaded file should be
    re-downloaded because the remote submission has a newer attempt.

    The bug this fixes: Canvas filenames are stable across attempts. The
    pre-fix logic skipped "if filename exists on disk." That meant a
    student's resubmission (attempt 2, same filename) was silently
    ignored — the operator graded attempt 1 and pushed wrong grades.

    Decision logic (the first that fires wins):
      1. Local file absent → fetch (initial download).
      2. Remote attempt > recorded attempt → fetch (genuine resubmission).
      3. Remote submitted_at > recorded submitted_at → fetch (timestamp-only
         signal — useful when attempt# isn't reliable on a path).
      4. Otherwise → SKIP (local is up-to-date).

    The 'recorded' values come from .fetch_log.json's per-uid entry from
    the prior fetch. If we have no recorded values (first time fetching
    this uid, or migrating from a pre-#103 log), we defer to "local file
    exists" semantics — don't re-download speculatively, but the next
    successful fetch will record the values for next time.

    All comparisons are defensive about None / missing / non-numeric
    values — partial data should never CAUSE a refetch and never PREVENT
    one. Returns True ONLY when there's positive evidence of newer remote.
    """
    if not local_exists:
        return True
    # Compare attempts numerically when both sides have a value
    try:
        if recorded_attempt is not None and remote_attempt is not None:
            if int(remote_attempt) > int(recorded_attempt):
                return True
    except (TypeError, ValueError):
        pass
    # Compare submitted_at as ISO strings (lexicographic comparison works
    # for properly-formatted ISO-8601 timestamps with timezone)
    if recorded_submitted_at and remote_submitted_at:
        if str(remote_submitted_at) > str(recorded_submitted_at):
            return True
    # No positive evidence of newer remote → keep local
    return False


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


# Issue #96 part 3: re-grade detection surface. After the fetch + download
# loop completes, walk submissions_raw/ and emit _existing_grades.csv —
# keyed by the same opaque key the de-id adapters will derive from the same
# filename. The agent reads this BEFORE grading; if a student already has a
# Canvas grade, this is a RE-GRADE (see grader_knowledge.md §10).
#
# FERPA: keys are opaque, grades are objective pedagogical data, no PII.
# The file is gitignored per the established challenge-dir convention.

_RAW_FILENAME_RE = re.compile(r"^(?P<prefix>[A-Za-z0-9-]+)_(?P<uid>\d+)(?:_[A-Za-z0-9]+)?\.[A-Za-z0-9.]+$")


# Issue #100: group-assignment workflow. Canvas's group assignments produce
# multiple per-student submission rows for what is conceptually ONE group
# deliverable. The instructor's grading workflow is "grade one memo per
# submitted group, apply to the group." Naively grading each per-student
# row wastes work AND risks inconsistent grades/comments across members of
# the same group. The helpers below detect group context, build a
# user_id → group map, pick a representative submitter per group, and
# render UNIQUE_GROUP_MEMOS.md so the agent grades only representatives.

def is_group_assignment(asg_meta: dict) -> bool:
    """Issue #100: detect whether this is a Canvas group assignment.
    Returns True if `group_category_id` is set (non-None, non-zero)."""
    gcat = asg_meta.get("group_category_id")
    return bool(gcat)


def grades_individually(asg_meta: dict) -> bool:
    """Issue #100: is this group assignment configured to grade members
    INDIVIDUALLY (each member gets their own grade) vs. as a SHARED grade
    (one grade applies to the whole group)?

    Canvas exposes `grade_group_students_individually` (default false →
    shared grade). True means the workflow should preserve per-student
    rows; False (the default) means the push should collapse mirrored
    rows so Canvas's group-grade distribution kicks in.
    """
    return bool(asg_meta.get("grade_group_students_individually"))


def build_group_map(
    groups: list[dict], members_by_group: dict[int, list[dict]]
) -> dict[int, dict]:
    """Issue #100: build a user_id → group context map.

    Args:
      groups: list of {id, name, members_count, ...} from
              GET /group_categories/:gcat_id/groups
      members_by_group: dict {group_id: [{id, sortable_name?, ...}, ...]}
                        from GET /groups/:gid/users per group

    Returns: {user_id: {
                "group_id": int,
                "group_name": str,
                "member_user_ids": [int, ...],   # all members of THIS group
              }}

    Users who are in NO group end up absent from the returned dict (caller
    can detect "no group context for this user_id" by `.get(uid)` returning
    None — typically means the student isn't enrolled in any group, which
    is a real edge case Canvas allows).
    """
    out: dict[int, dict] = {}
    for g in groups:
        try:
            gid = int(g.get("id"))
        except (TypeError, ValueError):
            continue
        gname = (g.get("name") or "").strip() or f"Group {gid}"
        members = members_by_group.get(gid, []) or []
        member_uids: list[int] = []
        for m in members:
            try:
                member_uids.append(int(m.get("id")))
            except (TypeError, ValueError):
                continue
        for uid in member_uids:
            out[uid] = {
                "group_id": gid,
                "group_name": gname,
                "member_user_ids": sorted(member_uids),
            }
    return out


def pick_group_representatives(
    group_map: dict[int, dict], submitter_uids: set[int]
) -> dict[int, int]:
    """Issue #100: pick ONE representative submitter per group.

    The rep is the SMALLEST user_id among the group's submitting members
    (deterministic + reproducible across re-runs). Groups with no
    submitting members are absent from the result (caller surfaces them
    as 'missing' groups in UNIQUE_GROUP_MEMOS.md).

    Returns: {group_id: rep_user_id}
    """
    # Collect groups present in the map
    by_group: dict[int, list[int]] = {}
    for uid, ctx in group_map.items():
        gid = ctx["group_id"]
        by_group.setdefault(gid, []).append(uid)
    reps: dict[int, int] = {}
    for gid, member_uids in by_group.items():
        submitters_in_group = sorted(u for u in member_uids if u in submitter_uids)
        if submitters_in_group:
            reps[gid] = submitters_in_group[0]
    return reps


def render_unique_group_memos_md(
    group_map: dict[int, dict],
    submitter_uids: set[int],
    representatives: dict[int, int],
    grade_individually: bool,
    prefix: str,
) -> str:
    """Issue #100: render UNIQUE_GROUP_MEMOS.md content (pure function — no
    file I/O). Listed per group:
      - Representative submitter (the one whose key the agent grades)
      - Mirrored member submitters (their keys; same content, same grade
        in shared-grade mode)
      - Non-submitting members (the agent doesn't grade these; they still
        receive the shared grade via Canvas if mode is shared)
      - Missing groups (groups in the category with NO submitters at all)

    `prefix` is the challenge prefix used to construct keyed filenames
    (e.g. 'kc1' → keys live at `kc1_<uid>.<ext>`); not strictly required
    for the rendering, but included in the heading so the agent can
    correlate keys.
    """
    # Group all groups by gid
    by_group: dict[int, dict] = {}
    for uid, ctx in group_map.items():
        gid = ctx["group_id"]
        if gid not in by_group:
            by_group[gid] = {
                "name": ctx["group_name"],
                "members": list(ctx["member_user_ids"]),
            }
    parts: list[str] = [
        f"# UNIQUE_GROUP_MEMOS — {prefix}",
        "",
        f"**Group assignment** ({'individual grades per member' if grade_individually else 'shared grade per group'}).",
        "",
    ]
    if grade_individually:
        parts.append(
            "> Mode: `grade_group_students_individually=true`. Each member gets a "
            "separate grade — grade every row independently. This list is "
            "advisory; no row collapsing happens at push time."
        )
    else:
        parts.append(
            "> Mode: shared grade (Canvas default for group assignments). "
            "Grade ONE representative per group; the push collapses mirrored "
            "rows so Canvas's group-grade distribution applies one grade to "
            "all members."
        )
    parts.extend(["", "## Groups"])
    groups_with_subs: list[int] = []
    groups_without_subs: list[int] = []
    for gid in sorted(by_group):
        members = by_group[gid]["members"]
        if any(u in submitter_uids for u in members):
            groups_with_subs.append(gid)
        else:
            groups_without_subs.append(gid)

    for gid in groups_with_subs:
        meta = by_group[gid]
        rep_uid = representatives.get(gid)
        parts.append("")
        parts.append(f"### {meta['name']} (group_id={gid})")
        parts.append("")
        if rep_uid is not None:
            parts.append(f"- **Representative submitter (grade this one):** user_id={rep_uid}")
        else:
            parts.append("- ⚠️ No submitting members in this group")
        mirrored = [u for u in meta["members"] if u in submitter_uids and u != rep_uid]
        if mirrored:
            parts.append(f"- Mirrored submitters (same group; shared grade): "
                         f"{', '.join(f'user_id={u}' for u in mirrored)}")
        non_submitters = [u for u in meta["members"] if u not in submitter_uids]
        if non_submitters:
            parts.append(f"- Non-submitting members (group inherits the shared grade in "
                         f"Canvas if shared-grade mode): "
                         f"{', '.join(f'user_id={u}' for u in non_submitters)}")

    if groups_without_subs:
        parts.extend(["", "## Groups with no submissions"])
        for gid in groups_without_subs:
            meta = by_group[gid]
            members_str = ", ".join(f"user_id={u}" for u in meta["members"])
            parts.append(f"- **{meta['name']}** (group_id={gid}) — members: {members_str}")

    if not groups_with_subs and not groups_without_subs:
        parts.extend(["", "_(no group context found — this assignment may not be a group "
                          "assignment despite having a group_category_id)_"])

    return "\n".join(parts) + "\n"


# Issue #102: task-page link detection + assignment_spec.md capture.
# The student-facing task definition is the AUTHORITATIVE source of truth
# for what is REQUIRED. Canvas assignment descriptions are often just a
# pointer ("Open Task Page →") to a separate course-site page where the
# real spec lives. The answer key / MASTER_solutions is a reference
# implementation, NOT a requirements source — anything in the answer key
# that isn't named in the task spec is OPTIONAL by default.

# Heuristic: link text strongly suggests "this is the task spec link."
# Matches things like "Open Task Page", "View Task", "Task Page →", etc.
_TASK_LINK_PATTERNS: tuple[str, ...] = (
    "task page", "open task", "view task", "course site task",
    "assignment page", "course-site",
)


def extract_task_page_url(canvas_description_html: str) -> str | None:
    """Issue #102: scan a Canvas assignment description for an outbound link
    to the student-facing task page.

    The pattern (real DS 250 U4T3 example): the Canvas description is just
    `<p>Work through this task on the course site... <a href="...">Open Task
    Page →</a></p>`. The actual spec lives at the linked URL. This function
    extracts that link so the caller can fetch the real spec.

    Returns the first qualifying URL or None if the description has no
    matching outbound link (in which case the Canvas description itself is
    the spec).

    Heuristic — a link qualifies if EITHER:
      - its visible link text contains a task-page indicator phrase
        ('task page' / 'open task' / 'view task' / etc.), OR
      - its href points OUTSIDE any common Canvas instance hostname
        (i.e., it's a course-site URL, not an internal Canvas link)

    The heuristic favors precision over recall — if a description has
    multiple links, the first task-page-keyed one wins. False positives
    on the recall side are caught by the operator reading the produced
    assignment_spec.md.
    """
    if not canvas_description_html:
        return None
    try:
        from bs4 import BeautifulSoup
    except ImportError:  # pragma: no cover — bs4 is a required dep
        return None
    soup = BeautifulSoup(canvas_description_html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        text = (a.get_text() or "").strip().lower()
        if not href:
            continue
        for pattern in _TASK_LINK_PATTERNS:
            if pattern in text:
                return href
    # No keyword match — try the second heuristic (link to a non-Canvas host)
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href or href.startswith("#") or href.startswith("mailto:"):
            continue
        # Skip self-links / Canvas-internal links
        href_low = href.lower()
        if "instructure.com" in href_low or "/courses/" in href_low:
            continue
        # An external link in the description — plausible task-page candidate
        return href
    return None


def fetch_task_page_text(url: str, timeout: int = 30) -> str:
    """Issue #102: fetch a course-site task page URL and convert its body
    HTML to readable Markdown text.

    No auth headers — task pages are typically public course-site pages
    (e.g. GitHub Pages, instructor-hosted course site). If the URL requires
    auth, the fetch will fail and the caller falls back to URL-only capture.
    """
    r = requests.get(url, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    try:
        from markdownify import markdownify
    except ImportError:  # pragma: no cover — markdownify is a required dep
        return r.text
    return markdownify(r.text, heading_style="ATX")


def render_assignment_spec(
    canvas_description_html: str,
    task_page_url: str | None,
    task_page_text: str | None,
) -> str:
    """Issue #102: render the assignment_spec.md content (pure function — no
    file I/O). Caller writes to disk separately so this is unit-testable
    without a tmp_path."""
    try:
        from markdownify import markdownify
    except ImportError:  # pragma: no cover
        markdownify = None  # type: ignore[assignment]
    if markdownify and canvas_description_html:
        desc_md = markdownify(canvas_description_html, heading_style="ATX").strip()
    else:
        desc_md = (canvas_description_html or "").strip()
    parts: list[str] = [
        "# Assignment Spec",
        "",
        "> **Source of truth for what is REQUIRED of students** (issue #102).",
        "> ",
        "> Grade against THIS, not the solution code. The answer key /",
        "> MASTER_solutions is a reference implementation — it can include",
        "> optional niceties. Anything in the answer key that isn't named in",
        "> this spec is OPTIONAL by default; promote to REQUIRED only if this",
        "> spec explicitly says so (e.g. 'you must...', 'required:', 'submit a...').",
        "",
        "## Canvas Assignment Description",
        "",
        desc_md if desc_md else "_(empty Canvas description)_",
    ]
    if task_page_url:
        parts.extend([
            "",
            "## Linked Task Page (the actual spec)",
            "",
            f"**URL:** {task_page_url}",
            "",
        ])
        if task_page_text and task_page_text.strip():
            parts.append(task_page_text.strip())
        else:
            parts.append(
                "_(task page fetch failed — review the URL above manually before grading.)_"
            )
    else:
        parts.extend([
            "",
            "## No Linked Task Page Detected",
            "",
            "The Canvas description above is the complete spec — no outbound",
            "link to a separate course-site task page was detected. If a task",
            "page exists elsewhere, add it to this file manually before grading.",
        ])
    return "\n".join(parts) + "\n"


def write_assignment_spec_md(
    challenge_dir: Path,
    canvas_description_html: str,
    task_page_url: str | None,
    task_page_text: str | None,
) -> Path:
    """Issue #102: write <challenge-dir>/assignment_spec.md.

    FERPA-safe: contains only the assignment description + task page (both
    student-facing, no PII). Gitignored per the convention but tracked in
    the operator's local copy for reference + agent-readable.
    """
    out = challenge_dir / "assignment_spec.md"
    content = render_assignment_spec(
        canvas_description_html, task_page_url, task_page_text
    )
    out.write_text(content, encoding="utf-8")
    return out


def existing_grades_rows(raw_dir: Path, subs: list[dict], prefix: str) -> list[dict]:
    """Issue #96 part 3: build _existing_grades.csv rows by joining the
    files actually written to raw_dir/ to the Canvas submissions list.

    For each `<prefix>_<uid>.<ext>` file in raw_dir/:
      1. Extract the uid from the filename
      2. Look up the matching submission in `subs` by user_id
      3. Skip if workflow_state != 'graded' (only existing GRADES surface
         here — non-graded / pending_review / unsubmitted rows are absent)
      4. Compute the key via key_for(filename, prefix) — same derivation
         the de-id adapter will use when it processes the file later, so
         the keys line up

    Returns rows of dicts ready for csv.DictWriter. Empty list = clean
    cohort with no prior grades (a fresh cohort run).
    """
    if _key_for is None:
        # Defensive: if the key_for import failed at module load, we can't
        # produce keyed output. Return empty rows so the caller writes a
        # header-only file rather than crashing the fetch.
        return []
    subs_by_uid: dict[int, dict] = {}
    for s in subs:
        uid = s.get("user_id")
        if uid is None:
            continue
        try:
            subs_by_uid[int(uid)] = s
        except (TypeError, ValueError):
            continue
    rows: list[dict] = []
    for f in sorted(raw_dir.iterdir()):
        if not f.is_file():
            continue
        m = _RAW_FILENAME_RE.match(f.name)
        if not m:
            continue
        # Filename prefix must match the canonical prefix we're writing. A
        # mismatch means we're picking up a stale file from a prior cohort
        # under a different prefix — skip it (legacy de-id stale-prefix
        # detection handles that surface separately).
        if m.group("prefix").lower() != prefix.lower():
            continue
        try:
            uid = int(m.group("uid"))
        except (TypeError, ValueError):
            continue
        s = subs_by_uid.get(uid)
        if not s:
            continue
        if s.get("workflow_state") != "graded":
            continue
        rows.append({
            "key": _key_for(f.name, prefix),
            "existing_grade": s.get("grade") or "",
            "existing_score": "" if s.get("score") is None else s.get("score"),
            "workflow_state": s.get("workflow_state", ""),
        })
    return rows


def write_existing_grades_csv(challenge_dir: Path, rows: list[dict]) -> Path:
    """Issue #96 part 3: write _existing_grades.csv to <challenge-dir>/.
    Always writes — even with no rows — so the agent + downstream tools
    can rely on the file's presence as a fetch-completion signal."""
    out = challenge_dir / "_existing_grades.csv"
    fieldnames = ["key", "existing_grade", "existing_score", "workflow_state"]
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return out


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
    if exts <= {".txt", ".md", ".qmd"}:  # .qmd = Quarto, structurally markdown + YAML + code chunks
        return "text"

    # HTML — disambiguate databricks vs. text by sniffing each file.
    # Issue #66: a strict "EVERY file has the marker" gate fired
    # `mixed_or_unknown` on cohorts with even one un-marker'd outlier
    # (an undecodable export, a partial download), silently disabling
    # the deid auto-chain. Relax to majority: if MOST files have the
    # marker, pick databricks and let the databricks adapter skip the
    # outlier (it already handles markerless files gracefully).
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
        n = len(html_files)
        if marker_count == 0:
            return "text"
        # Majority rule (more than half). A 50/50 split is genuinely
        # mixed content and warrants the operator picking explicitly.
        if marker_count * 2 > n:
            if marker_count < n:
                print(f"  note: {n - marker_count} of {n} .html file(s) lack the Databricks "
                      f"marker; the databricks adapter will skip those.", file=sys.stderr)
            return "databricks"
        return "mixed_or_unknown"  # genuinely heterogeneous — operator picks

    # Heterogeneous extensions (e.g. .docx + .pdf in one cohort) — operator
    # must split or pick explicitly.
    return "mixed_or_unknown"


def _maybe_follow_share_urls(mode: str, cd: Path) -> int:
    """Issue #51 — run grader_follow_share_url.py if a share URL is present
    (mode='auto') or unconditionally (mode='always'). Returns exit code.

    Detects ChatGPT / Gemini share URL patterns in any non-hidden, non-
    _external.md file in submissions_raw/. If none found in 'auto' mode,
    skips silently (no-op, exit 0). Returns the subprocess exit code on
    actual invocation; non-zero propagates to stop the chain."""
    if mode == "never":
        return 0
    raw_dir = cd / "submissions_raw"
    if not raw_dir.exists():
        return 0

    has_share = (mode == "always")
    if not has_share:
        for f in raw_dir.iterdir():
            if not f.is_file() or f.name.startswith(".") or f.name.endswith("_external.md"):
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
                if ("chatgpt.com/share/" in text
                        or "gemini.google.com/share/" in text
                        or "bard.google.com/share/" in text
                        or "share.google/aimode/" in text):  # issue #52
                    has_share = True
                    break
            except Exception:
                continue
    if not has_share:
        return 0

    cmd = [sys.executable, str(_TOOLS_DIR / "grader_follow_share_url.py"),
           "--challenge-dir", str(cd)]
    return run_chain_step("follow_share_url", cmd)


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
    ap.add_argument("--follow-share-urls",
                    choices=("auto", "never", "always"),
                    default="auto",
                    help="Issue #51 — when submissions_raw/ contains ChatGPT/Gemini "
                         "share URLs (e.g. AI Log assignments where students submit a "
                         "single link), run grader_follow_share_url.py before deid to "
                         "fetch the transcript. 'auto' (default) detects URL-only "
                         "submissions and chains the follow step transparently. "
                         "'never' skips. 'always' runs the follow step regardless.")
    args = ap.parse_args()

    tok, cid, base = _env_canvas(args.course_id)
    missing = [k for k, v in (("CANVAS_API_TOKEN", tok),
                              ("CANVAS_COURSE_ID", cid),
                              ("CANVAS_BASE_URL", base)) if not v]
    if missing:
        print(f"Missing env vars: {missing}. Set them in .env or pass --course-id.",
              file=sys.stderr)
        return 1

    cd = resolve_challenge_dir(args.challenge_dir, verb="fetching to")
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

    # Issue #102: capture the student-facing task definition as the
    # rubric-authoritative spec. The Canvas description is often just a
    # pointer to a course-site page where the real spec lives — follow the
    # link when present so the agent grades against what students were
    # actually asked to do, NOT the solution code.
    canvas_desc_html = asg_meta.get("description") or ""
    task_page_url = extract_task_page_url(canvas_desc_html)
    task_page_text: str | None = None
    if task_page_url:
        try:
            task_page_text = fetch_task_page_text(task_page_url)
            print(f"Task page detected + fetched: {task_page_url} "
                  f"({len(task_page_text)} chars of spec text)")
        except (requests.HTTPError, requests.RequestException) as e:
            print(f"WARN: task page fetch failed ({type(e).__name__}: {e}); "
                  f"assignment_spec.md will reference the URL only — "
                  f"review the link manually before grading.",
                  file=sys.stderr)
    spec_path = write_assignment_spec_md(
        cd, canvas_desc_html, task_page_url, task_page_text
    )
    print(f"Assignment spec captured -> {spec_path.relative_to(cd)} "
          f"(task page = source of truth for what is REQUIRED; "
          f"answer key = reference).")

    # Issue #100: group-assignment context. If group_category_id is set,
    # fetch the groups + their members so the workflow can grade ONE
    # representative per group (shared-grade) instead of N times the work.
    # Group context lands in .fetch_log.json (added later in the path-
    # specific code) and UNIQUE_GROUP_MEMOS.md (written here, agent-readable).
    group_map: dict[int, dict] = {}
    group_representatives: dict[int, int] = {}
    grade_individually_flag = False
    if is_group_assignment(asg_meta):
        gcat_id = asg_meta.get("group_category_id")
        grade_individually_flag = grades_individually(asg_meta)
        try:
            groups = fetch_group_category_groups(base, headers, int(gcat_id))
            members_by_group: dict[int, list[dict]] = {}
            for g in groups:
                try:
                    gid_int = int(g.get("id"))
                except (TypeError, ValueError):
                    continue
                try:
                    members_by_group[gid_int] = fetch_group_members(base, headers, gid_int)
                except (requests.HTTPError, requests.RequestException) as e:
                    print(f"WARN: failed to fetch members for group {gid_int} "
                          f"({type(e).__name__}: {e}); group will appear with no "
                          f"members in UNIQUE_GROUP_MEMOS.md.", file=sys.stderr)
                    members_by_group[gid_int] = []
            group_map = build_group_map(groups, members_by_group)
            mode = "individual grades per member" if grade_individually_flag else "shared grade per group"
            print(f"Group assignment detected (group_category_id={gcat_id}, "
                  f"mode={mode}; {len(groups)} group(s), "
                  f"{sum(len(m) for m in members_by_group.values())} total member(s)).")
        except (requests.HTTPError, requests.RequestException) as e:
            print(f"WARN: group context fetch failed ({type(e).__name__}: {e}); "
                  f"falling back to per-student grading (Canvas group features "
                  f"won't be used).", file=sys.stderr)

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
            # Issue #103: discussions don't have a per-user attempt#; the
            # freshness signal is the max(created_at, updated_at) across
            # this user's entries. Compare to the recorded value from the
            # prior fetch (stored as latest_activity_at).
            remote_activity = ""
            for _e in entries:
                for _k in ("updated_at", "created_at"):
                    _v = _e.get(_k) or ""
                    if _v > remote_activity:
                        remote_activity = _v
            remote_activity = remote_activity or None
            prior_entry = fetch_log_data["entries"].get(uid_s) or {}
            recorded_activity = prior_entry.get("latest_activity_at")
            if (not args.force
                    and not needs_refetch(
                        out_path.exists(),
                        None, None,  # discussions have no attempt# concept
                        recorded_activity, remote_activity,
                    )):
                skipped += 1
            else:
                try:
                    out_path.write_text(render_discussion_html(entries), encoding="utf-8")
                    ok += 1
                    fresh_marker = ""
                    if recorded_activity and remote_activity and recorded_activity != remote_activity:
                        fresh_marker = " (refetched: discussion updated)"
                    print(f"  {uid_s}: {fname} (discussion, {len(entries)} entries){fresh_marker}")
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
                # Issue #103: record freshness signal for the next fetch
                "latest_activity_at": remote_activity,
            }

        added = update_known_names(names_file, new_names) if new_names else 0
        # Issue #100: embed group_context in .fetch_log.json if this is a
        # group assignment. Consumed by reidentify (mirror rep feedback to
        # group-mates) and push (collapse shared-grade rows).
        gctx = group_context_for_fetch_log(
            group_map, asg_meta.get("group_category_id"), grade_individually_flag
        )
        if gctx:
            fetch_log_data["group_context"] = gctx
        fetch_log.write_text(
            json.dumps(fetch_log_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # Issue #96 part 3: write _existing_grades.csv for re-grade detection.
        # Discussion path doesn't already have `subs`; one extra API call to
        # the assignment submissions endpoint surfaces grade + score + state.
        try:
            disc_subs = fetch_submissions(base, cid, headers, args.assignment_id)
        except requests.HTTPError:
            disc_subs = []  # graceful — _existing_grades.csv will be header-only
        existing_rows = existing_grades_rows(raw_dir, disc_subs, prefix)
        egp = write_existing_grades_csv(cd, existing_rows)
        print(f"  {len(existing_rows)} existing grade(s) captured → {egp.name} "
              f"(re-grade detection; agent consults BEFORE grading)")

        # Issue #100: write UNIQUE_GROUP_MEMOS.md if this is a group assignment
        if group_map:
            submitter_uids = {int(s["user_id"]) for s in disc_subs
                              if s.get("user_id") is not None}
            group_representatives = pick_group_representatives(group_map, submitter_uids)
            memos_content = render_unique_group_memos_md(
                group_map, submitter_uids, group_representatives,
                grade_individually_flag, prefix,
            )
            memos_path = write_unique_group_memos_md(cd, memos_content)
            n_groups = len({ctx["group_id"] for ctx in group_map.values()})
            print(f"  Group context: {len(group_representatives)}/{n_groups} groups "
                  f"have a submitting representative → {memos_path.name}")

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
            # Issue #103: freshness signals for the quiz path
            remote_attempt = s.get("attempt")
            remote_submitted_at = s.get("submitted_at")
            prior_entry = fetch_log_data["entries"].get(uid_s) or {}
            recorded_attempt = prior_entry.get("attempt")
            recorded_submitted_at = prior_entry.get("submitted_at")
            if (not args.force
                    and not needs_refetch(
                        out_path.exists(),
                        recorded_attempt, remote_attempt,
                        recorded_submitted_at, remote_submitted_at,
                    )):
                skipped += 1
            else:
                try:
                    out_path.write_text(
                        render_quiz_markdown(sub_data or [], questions, quiz_title),
                        encoding="utf-8",
                    )
                    ok += 1
                    fresh_marker = ""
                    if recorded_attempt is not None:
                        fresh_marker = f" (refetched: attempt {recorded_attempt} → {remote_attempt})"
                    print(f"  {uid_s}: {fname} (quiz, {len(sub_data or [])} answers){fresh_marker}")
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
                # Issue #103: record freshness signals for next-fetch comparison
                "attempt": remote_attempt,
                "submitted_at": remote_submitted_at,
            }

        added = update_known_names(names_file, new_names) if new_names else 0
        # Issue #100: embed group_context in .fetch_log.json if this is a
        # group assignment. Consumed by reidentify (mirror rep feedback to
        # group-mates) and push (collapse shared-grade rows).
        gctx = group_context_for_fetch_log(
            group_map, asg_meta.get("group_category_id"), grade_individually_flag
        )
        if gctx:
            fetch_log_data["group_context"] = gctx
        fetch_log.write_text(
            json.dumps(fetch_log_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # Issue #96 part 3: write _existing_grades.csv for re-grade detection.
        # `subs` is already in scope from the quiz-path fetch above.
        existing_rows = existing_grades_rows(raw_dir, subs, prefix)
        egp = write_existing_grades_csv(cd, existing_rows)
        print(f"  {len(existing_rows)} existing grade(s) captured → {egp.name} "
              f"(re-grade detection; agent consults BEFORE grading)")

        # Issue #100: write UNIQUE_GROUP_MEMOS.md if this is a group assignment
        if group_map:
            submitter_uids = {int(s["user_id"]) for s in subs
                              if s.get("user_id") is not None}
            group_representatives = pick_group_representatives(group_map, submitter_uids)
            memos_content = render_unique_group_memos_md(
                group_map, submitter_uids, group_representatives,
                grade_individually_flag, prefix,
            )
            memos_path = write_unique_group_memos_md(cd, memos_content)
            n_groups = len({ctx["group_id"] for ctx in group_map.values()})
            print(f"  Group context: {len(group_representatives)}/{n_groups} groups "
                  f"have a submitting representative → {memos_path.name}")

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

        # Issue #103: freshness signals for the pull-latest-by-default
        # check. Look up the prior recorded attempt + submitted_at from
        # the EXISTING fetch_log_data["entries"] (loaded earlier from
        # disk). If the remote is newer, re-download; otherwise skip.
        remote_attempt = s.get("attempt")
        remote_submitted_at = s.get("submitted_at")
        prior_entry = fetch_log_data["entries"].get(user_id_s) or {}
        recorded_attempt = prior_entry.get("attempt")
        recorded_submitted_at = prior_entry.get("submitted_at")

        if attachments:
            # Multiple attachments: suffix _a, _b, _c …
            suffixes = ([""] if len(attachments) == 1
                        else [f"_{chr(ord('a') + i)}" for i in range(len(attachments))])
            for att, suf in zip(attachments, suffixes):
                ext = _ext_from_url_or_filename(att.get("url", ""), att.get("filename", ""))
                fname = f"{prefix}_{user_id_s}{suf}.{ext}"
                out_path = raw_dir / fname
                # Issue #103: skip only if local is genuinely up-to-date
                if (not args.force
                        and not needs_refetch(
                            out_path.exists(),
                            recorded_attempt, remote_attempt,
                            recorded_submitted_at, remote_submitted_at,
                        )):
                    skipped += 1
                    files_for_user.append(fname)
                    continue
                try:
                    download_attachment(att, headers, out_path)
                    files_for_user.append(fname)
                    ok += 1
                    # FERPA: print user_id + filename, NEVER the name
                    fresh_marker = ""
                    if out_path.exists() and recorded_attempt is not None:
                        fresh_marker = f" (refetched: attempt {recorded_attempt} → {remote_attempt})"
                    print(f"  {user_id_s}: {fname}{fresh_marker}")
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
            # Issue #103: skip only if local is up-to-date
            if (not args.force
                    and not needs_refetch(
                        out_path.exists(),
                        recorded_attempt, remote_attempt,
                        recorded_submitted_at, remote_submitted_at,
                    )):
                skipped += 1
                files_for_user.append(fname)
            else:
                try:
                    write_body_file(body, out_path)
                    files_for_user.append(fname)
                    ok += 1
                    fresh_marker = ""
                    if recorded_attempt is not None and out_path.exists():
                        fresh_marker = f" (refetched: attempt {recorded_attempt} → {remote_attempt})"
                    print(f"  {user_id_s}: {fname} (text_entry){fresh_marker}")
                except Exception as e:
                    print(f"  {user_id_s}: SKIP — error ({type(e).__name__})")
                    failed += 1

        elif sub_type == "online_url":
            url = s.get("url") or ""
            ext = _NON_ATTACHMENT_EXT["online_url"]
            fname = f"{prefix}_{user_id_s}.{ext}"
            out_path = raw_dir / fname
            # Issue #103: skip only if local is up-to-date
            if (not args.force
                    and not needs_refetch(
                        out_path.exists(),
                        recorded_attempt, remote_attempt,
                        recorded_submitted_at, remote_submitted_at,
                    )):
                skipped += 1
                files_for_user.append(fname)
            else:
                try:
                    out_path.write_text(url + "\n", encoding="utf-8")
                    files_for_user.append(fname)
                    ok += 1
                    fresh_marker = ""
                    if recorded_attempt is not None and out_path.exists():
                        fresh_marker = f" (refetched: attempt {recorded_attempt} → {remote_attempt})"
                    print(f"  {user_id_s}: {fname} (online_url){fresh_marker}")
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
            # Issue #103: record freshness signals so the next fetch can
            # detect a genuine resubmission and re-download (instead of
            # silently keeping a stale attempt-1 file).
            "attempt": s.get("attempt"),
            "submitted_at": s.get("submitted_at"),
        }

    # Update .known_names.txt (peer-mention scrub roster) — dedup case-insensitively
    added = update_known_names(names_file, new_names) if new_names else 0

    # Issue #100: embed group_context in .fetch_log.json if this is a group
    # assignment. Consumed by reidentify (mirror rep feedback to group-mates)
    # and push (collapse shared-grade rows).
    gctx = group_context_for_fetch_log(
        group_map, asg_meta.get("group_category_id"), grade_individually_flag
    )
    if gctx:
        fetch_log_data["group_context"] = gctx

    # Write .fetch_log.json (gitignored, never read by AI; for operator audit only)
    fetch_log.write_text(
        json.dumps(fetch_log_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Issue #96 part 3: write _existing_grades.csv for re-grade detection.
    # `subs` is already in scope from the default-path fetch above.
    existing_rows = existing_grades_rows(raw_dir, subs, prefix)
    egp = write_existing_grades_csv(cd, existing_rows)
    print(f"  {len(existing_rows)} existing grade(s) captured → {egp.name} "
          f"(re-grade detection; agent consults BEFORE grading)")

    # Issue #100: write UNIQUE_GROUP_MEMOS.md if this is a group assignment
    if group_map:
        submitter_uids = {int(s["user_id"]) for s in subs
                          if s.get("user_id") is not None}
        group_representatives = pick_group_representatives(group_map, submitter_uids)
        memos_content = render_unique_group_memos_md(
            group_map, submitter_uids, group_representatives,
            grade_individually_flag, prefix,
        )
        memos_path = write_unique_group_memos_md(cd, memos_content)
        n_groups = len({ctx["group_id"] for ctx in group_map.values()})
        print(f"  Group context: {len(group_representatives)}/{n_groups} groups "
              f"have a submitting representative → {memos_path.name}")

    # Final summary — FERPA: counts only, never a name. Issue #66: also
    # report the TOTAL roster size (not just `added`), since the
    # roster-pre-fetch path can populate `.known_names.txt` to a non-zero
    # size while this run added 0 NEW submitter names — operators were
    # reading "0 appended" as "empty roster".
    roster_total = 0
    if names_file.exists():
        roster_total = sum(
            1 for ln in names_file.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        )
    print(f"\n{ok} downloaded, {skipped} skipped (existing — use --force), "
          f"{failed} failed. {added} new submitter-name(s) appended to "
          f"{names_file.name} (roster total: {roster_total}; gitignored, "
          f"never read by AI).")
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

    # Issue #51 — follow share URLs BEFORE deid. The follow step writes
    # <prefix>_<userid>_external.md files into submissions_raw/, which the
    # downstream text adapter then deids alongside the original files.
    if args.follow_share_urls != "never":
        share_rc = _maybe_follow_share_urls(args.follow_share_urls, cd)
        if share_rc != 0:
            print(f"\nChain stopped — grader_follow_share_url exited {share_rc}.",
                  file=sys.stderr)
            return share_rc

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
