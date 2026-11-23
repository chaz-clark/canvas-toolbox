"""Tests — the course folder's starter GLOSSARY-MAP.md.

The constitution tells every course to keep a GLOSSARY-MAP.md listing the
toolkit's glossary and its own, but nothing wrote one. These pin that the
starter links to where the toolkit's glossary actually is in each layout, and
that a course's own map is never touched once it exists.
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import re  # noqa: E402

from glossary_map import (COURSE_GLOSSARY, MAP_FILE, ensure_glossary_map,  # noqa: E402
                          render_glossary_map)

_TOOLKIT_ROOT = _TOOLS_DIR.parent.parent


def _toolkit_link(text):
    return re.search(r"\[Canvas Toolbox\]\(\./([^)]+)\)", text).group(1)


def test_flat_layout_links_the_glossary_at_the_course_root():
    assert _toolkit_link(render_glossary_map("")) == "knowledge/glossary.md"


def test_nested_layout_links_the_glossary_inside_the_toolkit_subfolder():
    assert (_toolkit_link(render_glossary_map("canvas-toolbox"))
            == "canvas-toolbox/knowledge/glossary.md")


def test_the_linked_glossary_is_one_the_toolkit_ships():
    """If knowledge/glossary.md moves, every course's map breaks silently."""
    assert (_TOOLKIT_ROOT / _toolkit_link(render_glossary_map(""))).is_file()


def test_course_glossary_is_not_a_toolkit_owned_path():
    """A course glossary at a path the toolkit ships would be replaced on the
    next update. knowledge/glossary.md is the obvious wrong place."""
    assert COURSE_GLOSSARY != "knowledge/glossary.md"
    assert not (_TOOLKIT_ROOT / COURSE_GLOSSARY).exists()
    assert COURSE_GLOSSARY in render_glossary_map("")


def test_ensure_writes_once_and_dry_run_writes_nothing(tmp_path):
    assert ensure_glossary_map(tmp_path, "", apply=False) == "would-install"
    assert not (tmp_path / MAP_FILE).exists()
    assert ensure_glossary_map(tmp_path, "", apply=True) == "installed"
    assert (tmp_path / MAP_FILE).read_text(encoding="utf-8") == render_glossary_map("")
    assert ensure_glossary_map(tmp_path, "", apply=True) == "present"


def test_ensure_never_touches_a_course_map(tmp_path):
    own = "# Glossary Map\n\n- [ITM 327](./GLOSSARY.md): our words\n"
    (tmp_path / MAP_FILE).write_text(own, encoding="utf-8")
    assert ensure_glossary_map(tmp_path, "canvas-toolbox", apply=True) == "present"
    assert (tmp_path / MAP_FILE).read_text(encoding="utf-8") == own


def test_an_untouched_starter_follows_a_layout_change(tmp_path):
    """A nested course migrated to flat keeps the nested starter, whose link
    now points at a canvas-toolbox/ folder that is gone. An untouched starter
    is the toolkit's own output, so it is rewritten for the current layout."""
    (tmp_path / MAP_FILE).write_text(render_glossary_map("canvas-toolbox"), encoding="utf-8")
    assert ensure_glossary_map(tmp_path, "", apply=False) == "would-update"
    assert ensure_glossary_map(tmp_path, "", apply=True) == "updated"
    assert (tmp_path / MAP_FILE).read_text(encoding="utf-8") == render_glossary_map("")


def test_an_edited_map_with_the_old_nested_link_is_flagged_not_rewritten(tmp_path):
    edited = render_glossary_map("canvas-toolbox") + "- [DS 250](./GLOSSARY.md): ours\n"
    (tmp_path / MAP_FILE).write_text(edited, encoding="utf-8")
    assert ensure_glossary_map(tmp_path, "", apply=True) == "stale-link"
    assert (tmp_path / MAP_FILE).read_text(encoding="utf-8") == edited
