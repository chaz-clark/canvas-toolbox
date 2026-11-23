"""The course folder's starter GLOSSARY-MAP.md (written once, then the course's).

The constitution says a course keeps its own words in its own glossary and lists
both glossaries in a GLOSSARY-MAP.md at the course root. This writes that map the
first time, pointing at wherever the toolkit's glossary lives in this layout, and
never touches it again: after the first write the map is the course's file.

The course's own glossary goes at COURSE_GLOSSARY, never at knowledge/glossary.md.
That path is the toolkit's, and a flat-layout update replaces it every time.
"""
from __future__ import annotations

from pathlib import Path

MAP_FILE = "GLOSSARY-MAP.md"
COURSE_GLOSSARY = "GLOSSARY.md"
# A flat course whose map still links here has a link to a folder that is gone.
STALE_NESTED_LINK = "./canvas-toolbox/knowledge/glossary.md"


def render_glossary_map(toolkit_subdir: str) -> str:
    """`toolkit_subdir` is "" for the flat layout, "canvas-toolbox" for nested."""
    prefix = f"{toolkit_subdir}/" if toolkit_subdir else ""
    return (
        "# Glossary Map\n"
        "\n"
        "## Contexts\n"
        "\n"
        f"- [Canvas Toolbox](./{prefix}knowledge/glossary.md): the toolkit's words. "
        "Updated with the toolkit; don't edit it here.\n"
        "\n"
        f"<!-- This course's own words go in ./{COURSE_GLOSSARY} (not in "
        f"{prefix}knowledge/, which the toolkit replaces on every update). When the "
        "first one is settled, create that file and add a line here:\n"
        f"- [<course name>](./{COURSE_GLOSSARY}): this course's words -->\n"
    )


def ensure_glossary_map(course_root: Path, toolkit_subdir: str, apply: bool) -> str:
    """present / would-install / installed / would-update / updated / stale-link.

    Never overwrites a map the course has edited. The one rewrite: a map that
    is still byte-for-byte the starter for the OTHER layout (a nested course
    migrated to flat, say), whose toolkit link would otherwise point at a
    folder that no longer exists."""
    target = Path(course_root) / MAP_FILE
    want = render_glossary_map(toolkit_subdir)
    if not target.exists():
        if not apply:
            return "would-install"
        target.write_text(want, encoding="utf-8")
        return "installed"
    other = render_glossary_map("" if toolkit_subdir else "canvas-toolbox")
    text = target.read_text(encoding="utf-8")
    if want != other and text == other:
        if not apply:
            return "would-update"
        target.write_text(want, encoding="utf-8")
        return "updated"
    if not toolkit_subdir and STALE_NESTED_LINK in text:
        return "stale-link"   # edited by the course, so flagged, not rewritten
    return "present"
