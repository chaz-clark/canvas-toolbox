#!/usr/bin/env python3
"""
Import a Canvas .imscc export into the local course/ folder (Sprint 6).

Produces the SAME structure canvas_sync --pull creates, so _course_loader and
every tool converted to read course/ work identically offline — the only
difference is that course/ was populated from a .imscc instead of the API.

Mapping (verified against 5 real exports — see imscc_format_knowledge.md):
  course_settings/course_settings.xml   -> course/_course.json
  course_settings/module_meta.xml       -> course/<module-slug>/_module.json
  <identifierref>/assignment_settings.xml -> course/<mod>/<item>.json (name,
      points_possible, due_at, submission_types, ...)  [module item = Assignment]
  <identifierref>/assessment_meta.xml   -> course/<mod>/<item>.json (quiz, shaped
      like an assignment: submission_types=["online_quiz"])  [item = Quizzes::Quiz]
  wiki_content/<page>.html (via manifest href) -> course/<mod>/<item>.html  [WikiPage]

Item field names match the Canvas API shape so the local dicts are drop-in for
API responses. (SubHeaders / ExternalUrls / external tools are skipped — they
carry no gradeable or page content.)

USAGE
  uv run python lib/tools/offline_import.py --imscc ~/Downloads/course_export.imscc
  uv run python lib/tools/offline_import.py --imscc export.imscc --out course
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass


def slugify(s: str) -> str:
    s = re.sub(r"[^\w\s-]", "", (s or "").lower())
    s = re.sub(r"[\s_]+", "-", s).strip("-")
    return s or "item"


def _field(xml: str, tag: str):
    m = re.search(rf"<{tag}>([^<]*)</{tag}>", xml)
    return m.group(1) if m else None


def _dates_points(xml: str, d: dict) -> None:
    for t in ("due_at", "unlock_at", "lock_at"):
        v = _field(xml, t)
        if v:
            d[t] = v
    pp = _field(xml, "points_possible")
    if pp:
        try:
            d["points_possible"] = float(pp)
        except ValueError:
            pass


def assignment_from_xml(xml: str, published: bool | None) -> dict:
    d = {"name": _field(xml, "title")}
    ws = _field(xml, "workflow_state")
    d["published"] = (ws == "published") if ws else bool(published)
    st = _field(xml, "submission_types")
    if st is not None:
        d["submission_types"] = [s for s in st.split(",") if s]
    gt = _field(xml, "grading_type")
    if gt:
        d["grading_type"] = gt
    ae = _field(xml, "allowed_extensions")
    if ae:
        d["allowed_extensions"] = [e for e in ae.split(",") if e]
    _dates_points(xml, d)
    return d


def quiz_from_xml(xml: str, published: bool | None) -> dict:
    d = {"name": _field(xml, "title"), "submission_types": ["online_quiz"]}
    ws = _field(xml, "workflow_state")
    d["published"] = (ws == "published") if ws else bool(published)
    qt = _field(xml, "quiz_type")
    if qt:
        d["quiz_type"] = qt
    _dates_points(xml, d)
    return d


def _manifest_hrefs(manifest: str) -> dict:
    """identifier -> first file href, for resolving WikiPage items."""
    return dict(re.findall(
        r'<resource\b[^>]*\bidentifier="([^"]+)"[^>]*>\s*<file\s+href="([^"]+)"', manifest
    ))


def import_imscc(imscc_path, out_dir="course") -> dict:
    """Convert a .imscc into course/. Returns a summary count dict."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    z = zipfile.ZipFile(imscc_path)
    names = set(z.namelist())

    def read(n):
        return z.read(n).decode("utf-8", "ignore") if n in names else ""

    # --- course metadata ---
    cs = read("course_settings/course_settings.xml")
    ctx = read("course_settings/context.xml")
    course_meta = {
        "name": _field(cs, "title") or "<imported course>",
        "course_code": _field(cs, "course_code"),
        "start_at": _field(cs, "start_at"),
        "end_at": _field(cs, "conclude_at"),
        "canvas_id": _field(ctx, "course_id") or _field(cs, "canvas_id"),
        "workflow_state": _field(cs, "workflow_state"),
    }
    (out / "_course.json").write_text(json.dumps(course_meta, indent=2), encoding="utf-8")

    hrefs = _manifest_hrefs(read("imsmanifest.xml"))
    counts = {"modules": 0, "assignments": 0, "quizzes": 0, "pages": 0}

    mm = read("course_settings/module_meta.xml")
    for mod in re.findall(r"<module\b[^>]*>(.*?)</module>", mm, re.S):
        title = _field(mod, "title") or "module"
        mod_slug = slugify(title)
        mod_dir = out / mod_slug
        mod_dir.mkdir(parents=True, exist_ok=True)
        published = _field(mod, "workflow_state") == "active"
        item_summaries = []
        for it in re.findall(r"<item\b[^>]*>(.*?)</item>", mod, re.S):
            ct = _field(it, "content_type")
            ref = _field(it, "identifierref")
            it_title = _field(it, "title") or "item"
            it_pub = _field(it, "workflow_state") == "active"
            item_summaries.append({"title": it_title, "content_type": ct, "identifierref": ref})
            if not ref:
                continue
            if ct == "Assignment" and f"{ref}/assignment_settings.xml" in names:
                data = assignment_from_xml(read(f"{ref}/assignment_settings.xml"), it_pub)
                (mod_dir / f"{slugify(it_title)}.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
                counts["assignments"] += 1
            elif ct == "Quizzes::Quiz" and f"{ref}/assessment_meta.xml" in names:
                data = quiz_from_xml(read(f"{ref}/assessment_meta.xml"), it_pub)
                (mod_dir / f"{slugify(it_title)}.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
                counts["quizzes"] += 1
            elif ct == "WikiPage" and hrefs.get(ref) in names:
                (mod_dir / f"{slugify(it_title)}.html").write_text(read(hrefs[ref]), encoding="utf-8")
                counts["pages"] += 1
        (mod_dir / "_module.json").write_text(
            json.dumps({"title": title, "published": published, "items": item_summaries}, indent=2),
            encoding="utf-8",
        )
        counts["modules"] += 1
    return counts


def main(argv=None) -> int:
    force_utf8_console()
    ap = argparse.ArgumentParser(description="Import a Canvas .imscc into course/.")
    ap.add_argument("--imscc", type=Path, required=True, help="the .imscc export")
    ap.add_argument("--out", type=Path, default=Path("course"), help="output course dir (default: course)")
    args = ap.parse_args(argv)

    if not zipfile.is_zipfile(args.imscc):
        print(f"ERROR: {args.imscc} is not a valid .imscc (ZIP).", file=sys.stderr)
        return 2
    c = import_imscc(args.imscc, args.out)
    print(f"✓ imported {args.imscc.name} -> {args.out}/")
    print(f"  modules={c['modules']} assignments={c['assignments']} quizzes={c['quizzes']} pages={c['pages']}")
    print("  Now any tool with --local reads it: e.g. workload_audit.py --local")
    return 0


if __name__ == "__main__":
    sys.exit(main())
