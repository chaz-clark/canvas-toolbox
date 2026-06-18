# canvas-toolbox — Claude Code plugin

This directory packages `canvas-toolbox`'s agent specs + pedagogical
knowledge files for installation as a [Claude Code plugin][claudecode].

[claudecode]: https://docs.anthropic.com/claude-code

## What gets installed

`plugin.json` declares a single plugin pointing at `./lib/agents/`.
That directory carries:

- **8 agent specs** — `.md` + `.json` companion pairs:
  `canvas_blueprint_sync`, `canvas_content_sync`, `canvas_course_expert`,
  `canvas_grader`, `canvas_new_course_setup`, `canvas_schedule_auditor`,
  `canvas_semester_setup`, `ira_program_alignment`.
- **`knowledge/`** — 20+ pedagogical / Canvas-API knowledge files
  (rubrics, assessments, backwards design, cognitive load, Hattie
  3-phase, Merrill, BYU-I Learning Model + Course Design Standards,
  Canvas API + lessons learned, …).
- **`templates/`** — course-map + syllabus + rubric templates.
- **`pre_knowledge/`** — raw upstream sources (mostly gitignored;
  some open-license content tracked).

## Why a plugin (and not just clone-the-repo)

The clone-and-read flow stays the canonical install for adopters who
want the full toolkit (Python CLI tools under `lib/tools/` + the
agent skills). The plugin is the LIGHTWEIGHT path: an adopter who
already has Claude Code can pull JUST the agent skills + knowledge
into their environment and start asking pedagogical questions
without touching Python.

If they later want the deterministic audit tools, they clone the
repo and gain the same skill catalogue plus the `cb_*` / `grader_*` /
`canvas_*` / `*_audit` CLI suite.

## Brain-agnostic note

Two manifests live under this repo: `.claude-plugin/` (this dir) and,
when it's ready, `.codex-plugin/`. The agent files in `lib/agents/`
are written tool-agnostically — Claude Code, Codex, Cursor, Aider,
and any other agentic dev tool that reads markdown agent specs can
consume them without modification. Per the project's open-tooling
philosophy: the AI provider is a config swap, not a lock-in.

## Updating

Bump `version` in both `plugin.json` and `marketplace.json` whenever
`pyproject.toml`'s `[project].version` changes (single source of
truth — keep these in sync as part of the version-bump commit).
