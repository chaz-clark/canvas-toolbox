"""Tier 1 — loader orders modules by Canvas position, never slug.

A teacher's module order is intentional student flow. offline_import captures
each module's `position` from module_meta.xml (the only place it exists in a
.imscc); the loader must order by it, not by slug — for both correct reports
and correct re-packaging/upload order.
"""
import json
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from _course_loader import load_course  # noqa: E402


def test_modules_ordered_by_position_not_slug(tmp_path):
    (tmp_path / "_course.json").write_text(json.dumps({"name": "T"}), encoding="utf-8")
    # 'zeta' sorts AFTER 'alpha' by slug, but has the earlier position — position must win.
    for slug, pos in [("zeta", 1), ("alpha", 2)]:
        d = tmp_path / slug
        d.mkdir()
        (d / "_module.json").write_text(
            json.dumps({"title": slug, "position": pos, "items": []}), encoding="utf-8")
    c = load_course(str(tmp_path))
    assert [m.slug for m in c.modules] == ["zeta", "alpha"]


def test_missing_position_falls_back_to_slug(tmp_path):
    (tmp_path / "_course.json").write_text(json.dumps({"name": "T"}), encoding="utf-8")
    for slug in ("bbb", "aaa"):  # no position -> deterministic slug order
        d = tmp_path / slug
        d.mkdir()
        (d / "_module.json").write_text(json.dumps({"title": slug, "items": []}), encoding="utf-8")
    c = load_course(str(tmp_path))
    assert [m.slug for m in c.modules] == ["aaa", "bbb"]
