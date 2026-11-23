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
    """present / would-install / installed. Never overwrites an existing map."""
    target = Path(course_root) / MAP_FILE
    if target.exists():
        return "present"
    if not apply:
        return "would-install"
    target.write_text(render_glossary_map(toolkit_subdir), encoding="utf-8")
    return "installed"
