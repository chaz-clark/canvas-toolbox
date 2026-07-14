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

import html
import json
import re
import zipfile
from datetime import datetime, timedelta, timezone
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


def shift_value(value: str, days: int, tz=None) -> str:
    """Shift a single date/datetime string by `days`, preserving its format.

    `tz` (a tzinfo, e.g. ZoneInfo("America/Denver")) shifts the LOCAL wall-clock
    time so displayed due times AND weekday survive a DST boundary: the value is
    read as UTC, converted to `tz`, moved N days on the naive local clock, then
    re-localized (picking the target date's MST/MDT offset) and written back as
    UTC. `tz=None` does a raw whole-day UTC shift (local time may drift 1h across
    DST). Values that aren't the naive Canvas format are returned unchanged."""
    v = value.strip()
    if _DT_VAL.match(v):
        dt = datetime.strptime(v, _DT_FMT)  # naive, represents UTC
        if tz is None:
            shifted = dt + timedelta(days=days)
        else:
            local = dt.replace(tzinfo=timezone.utc).astimezone(tz)
            moved = (local.replace(tzinfo=None) + timedelta(days=days)).replace(tzinfo=tz)
            shifted = moved.astimezone(timezone.utc).replace(tzinfo=None)
        return shifted.strftime(_DT_FMT)
    if _D_VAL.match(v):
        # date-only (all_day_date) has no time component — tz is irrelevant
        return (datetime.strptime(v, _D_FMT) + timedelta(days=days)).strftime(_D_FMT)
    return value


def shift_dates_in_text(text: str, days: int, tz=None) -> tuple[str, int]:
    """Shift every schedule-date tag value in an XML string. Returns
    (new_text, number_of_dates_shifted). See shift_value for `tz`."""
    count = 0

    def repl(m):
        nonlocal count
        inner = m.group(2)
        shifted = shift_value(inner, days, tz=tz)
        if shifted != inner:
            count += 1
        return f"{m.group(1)}{shifted}{m.group(3)}"

    for tag in SCHEDULE_DATE_TAGS:
        text = re.sub(rf"(<{tag}>)([^<]*)(</{tag}>)", repl, text)
    return text, count


def adjust_dates_in_imscc(src_path, out_path, days: int, tz=None) -> int:
    """Copy `src_path` to `out_path`, shifting every schedule date by `days`.
    Non-XML entries and all non-date bytes are copied verbatim (identifiers and
    structure preserved). `tz` enables DST-correct local-time shifting (see
    shift_value). Returns the count of dates shifted."""
    src_path, out_path = Path(src_path), Path(out_path)
    total = 0
    with zipfile.ZipFile(src_path) as zin, zipfile.ZipFile(
        out_path, "w", zipfile.ZIP_DEFLATED
    ) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.endswith(".xml"):
                new_text, n = shift_dates_in_text(data.decode("utf-8"), days, tz=tz)
                total += n
                data = new_text.encode("utf-8")
            zout.writestr(item, data)
    return total


def manifest_resource_identifiers(imsmanifest_text: str) -> list[str]:
    """The identifier of every <resource> in the manifest."""
    return re.findall(r"<resource\b[^>]*\bidentifier=\"([^\"]+)\"", imsmanifest_text)


def manifest_hrefs(imsmanifest_text: str) -> dict:
    """resource identifier -> its first <file href>. Resolves a WikiPage
    resource to the wiki_content/*.html entry (same mapping offline_import uses)."""
    return dict(re.findall(
        r'<resource\b[^>]*\bidentifier="([^"]+)"[^>]*>\s*<file\s+href="([^"]+)"',
        imsmanifest_text,
    ))


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


# ===========================================================================
# MIRROR: record course/ edits back INTO the source .imscc (the WRITE path).
#
# The inverse of offline_import. course/ is the lossy working folder; the .imscc
# is the source of truth. When course/ reaches a final state we RECORD it by
# PATCHING ONLY the tags course/ tracks in each matching resource IN PLACE —
# same entry-by-entry mechanic as adjust_dates_in_imscc. Everything course/ does
# not track (quiz questions/QTI, web_resources, LTI, rubric long-descriptions,
# formatting) is copied VERBATIM. Each course/ item joins to its source resource
# by the identifier offline_import preserved (identifierref).
# ===========================================================================

_CC_NS = (
    'xmlns="http://canvas.instructure.com/xsd/cccv1p0" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
    'xsi:schemaLocation="http://canvas.instructure.com/xsd/cccv1p0 '
    'https://canvas.instructure.com/xsd/cccv1p0.xsd"'
)


def _esc(value) -> str:
    """XML element-content escape (&, <, >). None -> ''."""
    return html.escape("" if value is None else str(value), quote=False)


def _fmt_points(v) -> str:
    """Points as Canvas writes them: a float string (0.0 / 1.0 / 8.5)."""
    return str(float(v))


def _set_tag(text: str, tag: str, value: str, *, first_only: bool = True) -> tuple[str, int]:
    """SET <tag>'s inner text to `value` (raw; XML-escaped on write), but ONLY
    where the current value (unescaped) DIFFERS — so an unchanged field stays
    byte-identical to the source (idempotence + exact parity). Matches both
    `<tag>...</tag>` and the self-closing empty `<tag/>`. Absent tags are left
    alone (never fabricated). Returns (new_text, n_changed)."""
    esc = html.escape(value, quote=False)
    changed = 0

    def repl(m):
        nonlocal changed
        inner = m.group(1)
        current = "" if inner is None else html.unescape(inner)
        if current == value:
            return m.group(0)  # already equal -> preserve source bytes exactly
        changed += 1
        return f"<{tag}>{esc}</{tag}>"

    pat = rf"<{tag}>([^<]*)</{tag}>|<{tag}\s*/>"
    if first_only:
        text = re.sub(pat, repl, text, count=1)
    else:
        text = re.sub(pat, repl, text)
    return text, changed


# --- per-resource patchers -------------------------------------------------

def _patch_assignment(text: str, data: dict) -> tuple[str, int]:
    """Patch <ref>/assignment_settings.xml from a course/ assignment dict."""
    n = 0

    def setf(tag, val, *, fmt=str):
        nonlocal text, n
        if val is None:
            return
        text, c = _set_tag(text, tag, fmt(val))
        n += c

    setf("title", data.get("name"))
    for tag in ("due_at", "unlock_at", "lock_at"):
        if data.get(tag):  # course/ can't distinguish "cleared" from "absent" -> only SET
            setf(tag, data[tag])
    if data.get("points_possible") is not None:
        setf("points_possible", data["points_possible"], fmt=_fmt_points)
    ws = data.get("workflow_state") or ("published" if data.get("published") else "unpublished")
    setf("workflow_state", ws)
    st = data.get("submission_types")
    if st:
        setf("submission_types", ",".join(st))
    setf("grading_type", data.get("grading_type"))
    setf("assignment_group_identifierref", data.get("assignment_group_identifierref"))
    return text, n


def _patch_quiz(text: str, data: dict) -> tuple[str, int]:
    """Patch <ref>/assessment_meta.xml from a course/ quiz dict. Touches ONLY
    name/dates/published/group — NEVER the question set or QTI (course/ has no
    questions; they must survive untouched)."""
    n = 0
    text, c = _set_tag(text, "title", data.get("name") or "")  # first = quiz-level title
    n += c
    for tag in ("due_at", "unlock_at", "lock_at"):  # live only in the nested <assignment>
        if data.get(tag):
            text, c = _set_tag(text, tag, data[tag])
            n += c
    published = data.get("published")
    if published is None:
        published = (data.get("workflow_state") == "published")
    text, c = _set_tag(text, "workflow_state", "published" if published else "unpublished")
    n += c
    text, c = _set_tag(text, "available", "true" if published else "false")
    n += c
    grp = data.get("assignment_group_identifierref")
    if grp:  # appears twice (nested + quiz-level) with the same value -> set both
        text, c = _set_tag(text, "assignment_group_identifierref", grp, first_only=False)
        n += c
    return text, n


def _patch_assignment_groups(text: str, groups: list) -> tuple[str, int]:
    """Patch course_settings/assignment_groups.xml names/weights/positions,
    joining each group by its preserved identifier."""
    by_id = {g["identifier"]: g for g in groups if g.get("identifier")}
    stats = [0, 0]  # [fields_changed, groups_changed]

    def repl(m):
        block, gid = m.group(0), m.group(1)
        g = by_id.get(gid)
        if not g:
            return block
        before = stats[0]
        for tag, val in (
            ("title", g.get("name") or ""),
            ("group_weight", _fmt_points(g.get("group_weight") or 0)),
            ("position", str(int(g.get("position") or 0))),
        ):
            block, c = _set_tag(block, tag, val)
            stats[0] += c
        if stats[0] > before:
            stats[1] += 1
        return block

    text = re.sub(r'<assignmentGroup\s+identifier="([^"]+)">.*?</assignmentGroup>',
                  repl, text, flags=re.S)
    return text, stats[0], stats[1]


def _patch_module_meta(text: str, course_modules: list) -> tuple[str, int, int]:
    """Patch course_settings/module_meta.xml module names / published / order and
    per-item titles / order. A source <module> block is matched to a course/
    module by its ordered list of item identifierrefs (robust to rename/reorder),
    falling back to an exact title match; unmatched blocks are preserved as-is.
    Returns (new_text, fields_changed, modules_changed)."""
    cmods = [
        (cm, [it.get("identifierref") for it in cm.get("items", []) if it.get("identifierref")])
        for cm in course_modules
    ]
    stats = [0, 0]  # [fields_changed, modules_changed]

    def repl(m):
        block = m.group(0)
        block_refs = re.findall(r"<identifierref>([^<]+)</identifierref>", block)
        cand = [c for c, r in cmods if r and r == block_refs]
        cm = cand[0] if len(cand) == 1 else None
        if cm is None:  # fall back to a unique title match
            tm = re.search(r"<title>([^<]*)</title>", block)
            btitle = html.unescape(tm.group(1)) if tm else None
            tcand = [c for c, _ in cmods if c.get("title") == btitle]
            cm = tcand[0] if len(tcand) == 1 else None
        if cm is None:
            return block
        before = stats[0]
        # module-level fields (first occurrence in the block = module level)
        block, c = _set_tag(block, "title", cm.get("title") or "")
        stats[0] += c
        block, c = _set_tag(block, "workflow_state",
                            "active" if cm.get("published") else "unpublished")
        stats[0] += c
        if cm.get("position") is not None:
            block, c = _set_tag(block, "position", str(cm["position"]))
            stats[0] += c
        # per-item title + position, joined by identifierref
        by_ref = {it["identifierref"]: it for it in cm.get("items", []) if it.get("identifierref")}

        def item_repl(im):
            iblock = im.group(0)
            rm = re.search(r"<identifierref>([^<]+)</identifierref>", iblock)
            cit = by_ref.get(rm.group(1)) if rm else None
            if not cit:
                return iblock
            iblock, c1 = _set_tag(iblock, "title", cit.get("title") or "")
            c2 = 0
            if cit.get("position") is not None:
                iblock, c2 = _set_tag(iblock, "position", str(cit["position"]))
            stats[0] += c1 + c2
            return iblock

        block = re.sub(r"<item\b[^>]*>.*?</item>", item_repl, block, flags=re.S)
        if stats[0] > before:
            stats[1] += 1
        return block

    text = re.sub(r"<module\b[^>]*>.*?</module>", repl, text, flags=re.S)
    return text, stats[0], stats[1]


def learning_outcomes_xml(outcomes: list) -> str:
    """Build course_settings/learning_outcomes.xml from course/_outcomes.json
    (shape offline_import.parse_learning_outcomes reads back: identifier + title
    + description). Course-OWNED outcomes only."""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', f"<learningOutcomes {_CC_NS}>"]
    for o in outcomes:
        lines.append(f'  <learningOutcome identifier="{_esc(o.get("id"))}">')
        lines.append(f"    <title>{_esc(o.get('title'))}</title>")
        if o.get("display_name"):
            lines.append(f"    <display_name>{_esc(o.get('display_name'))}</display_name>")
        lines.append(f"    <description>{_esc(o.get('description'))}</description>")
        lines.append("    <calculation_method>highest</calculation_method>")
        lines.append("  </learningOutcome>")
    lines.append("</learningOutcomes>")
    return "\n".join(lines)


def _ensure_manifest_file_ref(manifest: str, file_href: str) -> str:
    """Add `<file href="file_href"/>` to the course-settings resource (the one
    whose href is course_settings/canvas_export.txt) if absent — so a newly
    added learning_outcomes.xml is actually imported. No-op if already present or
    the resource can't be located (Jidoka: never corrupt the manifest)."""
    if f'<file href="{file_href}"/>' in manifest:
        return manifest
    m = re.search(r'<resource[^>]*href="course_settings/canvas_export\.txt"[^>]*>', manifest)
    if not m:
        return manifest
    opening = m.group(0)
    return manifest.replace(opening, f'{opening}\n      <file href="{file_href}"/>', 1)


# --- course/ reader (raw; needs identifierref that the loader drops) --------

def _load_course_edits(course_dir) -> dict:
    """Read course/ into the maps the mirror needs, joining each item to its
    source resource by the EXACT ref->file map offline_import wrote to
    _index.json. A resource can appear in several modules under different
    per-module titles, so a title/slug guess is not a reliable join (it can miss
    an item, or load the wrong file into a ref) — the recorded path is."""
    course_dir = Path(course_dir)

    def load(p):
        return json.loads(Path(p).read_text(encoding="utf-8"))

    idx = course_dir / "_index.json"
    if not idx.exists():
        raise SystemExit(
            f"{idx} missing — this course/ was created before recordable indexing. "
            "Re-run offline_import on the source .imscc to enable imscc_record."
        )
    index = load(idx)

    assignments, quizzes, pages, missing = {}, {}, {}, []
    for ref, info in index.items():
        p = course_dir / info["path"]
        if not p.exists():
            missing.append(info["path"])
            continue
        t = info.get("type")
        if t == "Assignment":
            assignments[ref] = load(p)
        elif t == "Quizzes::Quiz":
            quizzes[ref] = load(p)
        elif t == "WikiPage":
            pages[ref] = p.read_text(encoding="utf-8")
    if missing:  # Jidoka: never silently skip an item the index promised
        raise SystemExit(
            f"course/_index.json references {len(missing)} missing file(s) "
            f"(e.g. {missing[0]}) — course/ is inconsistent with its index."
        )

    module_metas = [load(p) for p in course_dir.glob("*/_module.json")]

    def opt(name, is_json=True):
        p = course_dir / name
        if not p.exists():
            return None
        return load(p) if is_json else p.read_text(encoding="utf-8")

    return {
        "assignments": assignments,
        "quizzes": quizzes,
        "pages": pages,
        "modules": module_metas,
        "outcomes": opt("_outcomes.json"),
        "groups": opt("_assignment_groups.json"),
        "syllabus": opt("syllabus.html", is_json=False),
    }


def mirror_course_into_imscc(course_dir, src, out) -> dict:
    """PATCH course/ edits into the source cartridge `src`, writing `out`. Every
    field course/ tracks is set in the matching resource; every other byte
    (quiz QTI, web_resources, LTI, formatting) is copied VERBATIM. Returns a
    dict of counts. Idempotent: with no course/ edits, `out` re-encodes the same
    tracked values (tracked bytes unchanged)."""
    course_dir, src, out = Path(course_dir), Path(src), Path(out)
    e = _load_course_edits(course_dir)
    counts = {k: 0 for k in ("assignments", "quizzes", "pages", "modules",
                             "assignment_groups", "outcomes", "syllabus",
                             "descriptions", "fields_changed", "skipped")}
    seen: set[str] = set()

    with zipfile.ZipFile(src) as zin:
        names = set(zin.namelist())
        href_to_ref = {href: ref for ref, href in
                       manifest_hrefs(zin.read("imsmanifest.xml").decode("utf-8", "ignore")).items()}
        add_outcomes = bool(e["outcomes"]) and "course_settings/learning_outcomes.xml" not in names

        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                fname = item.filename
                data = zin.read(fname)

                if fname == "imsmanifest.xml" and add_outcomes:
                    data = _ensure_manifest_file_ref(
                        data.decode("utf-8"), "course_settings/learning_outcomes.xml"
                    ).encode("utf-8")

                elif fname == "course_settings/module_meta.xml" and e["modules"]:
                    text, nf, nm = _patch_module_meta(data.decode("utf-8"), e["modules"])
                    counts["modules"] += nm
                    counts["fields_changed"] += nf
                    data = text.encode("utf-8")

                elif fname == "course_settings/assignment_groups.xml" and e["groups"]:
                    text, nf, ng = _patch_assignment_groups(data.decode("utf-8"), e["groups"])
                    counts["assignment_groups"] += ng
                    counts["fields_changed"] += nf
                    data = text.encode("utf-8")

                elif fname == "course_settings/learning_outcomes.xml" and e["outcomes"] is not None:
                    data = learning_outcomes_xml(e["outcomes"]).encode("utf-8")
                    counts["outcomes"] = len(e["outcomes"])

                elif fname == "course_settings/syllabus.html" and e["syllabus"] is not None:
                    if data.decode("utf-8", "ignore") != e["syllabus"]:
                        counts["syllabus"] = 1
                        counts["fields_changed"] += 1
                    data = e["syllabus"].encode("utf-8")

                elif fname.endswith("/assignment_settings.xml") and fname.split("/")[0] in e["assignments"]:
                    ref = fname.split("/")[0]
                    seen.add(ref)
                    text, nf = _patch_assignment(data.decode("utf-8"), e["assignments"][ref])
                    if nf:
                        counts["assignments"] += 1
                        counts["fields_changed"] += nf
                    data = text.encode("utf-8")

                elif fname.endswith("/assessment_meta.xml") and fname.split("/")[0] in e["quizzes"]:
                    ref = fname.split("/")[0]
                    seen.add(ref)
                    text, nf = _patch_quiz(data.decode("utf-8"), e["quizzes"][ref])
                    if nf:
                        counts["quizzes"] += 1
                        counts["fields_changed"] += nf
                    data = text.encode("utf-8")

                elif fname.startswith("wiki_content/") and href_to_ref.get(fname) in e["pages"]:
                    ref = href_to_ref[fname]
                    seen.add(ref)
                    new = e["pages"][ref]
                    if data.decode("utf-8", "ignore") != new:
                        counts["pages"] += 1
                        counts["fields_changed"] += 1
                    data = new.encode("utf-8")

                elif fname.endswith(".html") and "/" in fname and fname.split("/")[0] in e["assignments"]:
                    # assignment description body: <ref>/<slug>.html
                    body = e["assignments"][fname.split("/")[0]].get("description")
                    if body is not None:
                        if data.decode("utf-8", "ignore") != body:
                            counts["descriptions"] += 1
                            counts["fields_changed"] += 1
                        data = body.encode("utf-8")

                zout.writestr(item, data)

            if add_outcomes:
                zout.writestr("course_settings/learning_outcomes.xml",
                              learning_outcomes_xml(e["outcomes"]))
                counts["outcomes"] = len(e["outcomes"])

    tracked = set(e["assignments"]) | set(e["quizzes"]) | set(e["pages"])
    counts["skipped"] = len(tracked - seen)  # course/ items with no source resource
    return counts
