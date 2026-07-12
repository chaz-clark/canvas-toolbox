"""
Read the local course/ folder into a source-agnostic model (Sprint 5).

course/ is produced by `canvas_sync --pull` (from the Canvas API) OR by
`offline_import` (from a .imscc). Tools that read it therefore run identically
online or offline — the only difference is how course/ got populated. Reading
course/ instead of re-hitting the API also removes redundant API calls for
tools run after a sync.

Structure (see canvas_sync.py):
  course/_course.json                 course metadata (name, canvas_id, dates, ...)
  course/<module-slug>/_module.json   module metadata (title, position, items)
  course/<module-slug>/<item>.json    assignment / quiz / discussion / tool metadata
  course/<module-slug>/<page>.html    page body

Per-item field names match the Canvas API shape (name, points_possible, due_at,
submission_types, ...), so a list of these dicts is a drop-in for an API
`/courses/:id/assignments` response.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_COURSE_DIR = "course"


class CourseNotFound(FileNotFoundError):
    """course/ isn't populated. Hard stop with actionable guidance."""


@dataclass
class Module:
    slug: str
    meta: dict                      # the _module.json
    items: list[dict] = field(default_factory=list)  # loaded item .json dicts

    @property
    def title(self) -> str:
        return self.meta.get("title", self.slug)


@dataclass
class Course:
    dir: Path
    meta: dict                      # _course.json
    modules: list[Module] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.meta.get("name", "<unknown course>")

    @property
    def canvas_id(self):
        return self.meta.get("canvas_id")

    @property
    def items(self) -> list[dict]:
        """Every per-item metadata dict across all modules (assignments, quizzes,
        discussions, external tools) — the .json files, not pages."""
        return [it for m in self.modules for it in m.items]

    @property
    def assignments(self) -> list[dict]:
        """Gradeable items — those carrying a points_possible or submission_types.
        Shaped like an API /assignments response (same field names)."""
        return [
            it for it in self.items
            if "points_possible" in it or "submission_types" in it
        ]

    def page_paths(self) -> list[Path]:
        """All page .html files across modules."""
        return sorted(p for m in self.modules for p in (self.dir / m.slug).glob("*.html"))

    def syllabus(self) -> str:
        """The syllabus HTML (course/syllabus.html), or '' if none — mirrors the
        API's course.syllabus_body."""
        p = self.dir / "syllabus.html"
        return p.read_text(encoding="utf-8") if p.is_file() else ""

    def pages(self) -> list[dict]:
        """Page bodies shaped loosely like an API /pages response
        ({title, body}). Title is the file slug (identifies the page in reports)."""
        return [{"title": p.stem, "body": p.read_text(encoding="utf-8")} for p in self.page_paths()]


def load_course(course_dir=DEFAULT_COURSE_DIR) -> Course:
    """Load course/ into a Course model. Raises CourseNotFound if it isn't
    populated (run `canvas_sync --pull` online, or `offline_import` offline)."""
    root = Path(course_dir)
    course_json = root / "_course.json"
    if not course_json.is_file():
        raise CourseNotFound(
            f"No {course_json} — course/ is not populated.\n"
            f"  online:  uv run python lib/tools/canvas_sync.py --pull\n"
            f"  offline: uv run python lib/tools/offline_import.py --imscc <file>"
        )
    course = Course(dir=root, meta=json.loads(course_json.read_text(encoding="utf-8")))
    for mod_meta_path in sorted(root.glob("*/_module.json")):
        mod_dir = mod_meta_path.parent
        module = Module(slug=mod_dir.name, meta=json.loads(mod_meta_path.read_text(encoding="utf-8")))
        for item_path in sorted(mod_dir.glob("*.json")):
            if item_path.name == "_module.json":
                continue
            try:
                data = json.loads(item_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                data.setdefault("_source_path", str(item_path))
                # Normalize to the API shape: quizzes store `title`, assignments
                # store `name`. Give every item a `name` so tools that expect the
                # API field work uniformly.
                if "name" not in data and data.get("title"):
                    data["name"] = data["title"]
                module.items.append(data)
        course.modules.append(module)
    return course
