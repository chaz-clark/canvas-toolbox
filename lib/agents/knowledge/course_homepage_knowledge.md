---
name: course_homepage_knowledge
description: Pure-HTML/CSS Canvas course home page generator — DesignPLUS-free replacement. Reads a schedule.yml (one per course-section) + today's date; renders a static home page with the current week's section pre-expanded. Auto-tracks the semester via regenerate-on-cadence rather than runtime JS. Promotes the canvas-toolbox pattern used in `course_homepage_build.py`.
version: "0.1"
author: chaz-clark
license: MIT
metadata:
  topic: canvas-page-generation
  precipitating-event: 2026-06-22 — BYUI moving off DesignPLUS for cost savings; need an HTML/CSS-native course-home-page tool
  affects: any course wanting an interactive home page without DesignPLUS or JS injection
  consumed_by:
    - lib/tools/course_homepage_build.py
read_at_runtime: selective_load
---

# Course-homepage generation — pure HTML/CSS, DesignPLUS-free

## When to use this knowledge file

When an instructor (or an agent acting on an instructor's behalf) wants a Canvas course home page that:

- Has block-button navigation to each week's module
- Pre-expands the **current week** based on today's date
- Renders cleanly in Canvas without DesignPLUS (CIDI Labs) licensing or account-level CSS/JS injection
- Survives Canvas's WYSIWYG editor on re-edits (no fragile `:target` or radio-hack CSS)
- Auto-tracks the semester via a scheduled regenerate rather than runtime JavaScript

The accompanying tool is `lib/tools/course_homepage_build.py`. This knowledge file is the design rationale + when to use it + how to teach an instructor to use it.

## The pattern this replaces

DesignPLUS (CIDI Labs) ships a `dp-module-list dp-auto-update` pattern that:
1. Renders a styled module list on the home page
2. Auto-refreshes the list via JavaScript at page load by hitting the Canvas API

Without DesignPLUS, the second behavior requires either:
- Custom JavaScript in the page body (Canvas sandboxes / strips most page-body JS, plus FERPA + portability concerns)
- An account-level CSS+JS injection — same cost+lock-in shape as DesignPLUS

This knowledge file's pattern picks a third path: **the page is static at render time; "the current week" is baked in at build time; regenerate the page on a cadence to keep it fresh.**

## The model

```
schedule.yml (one per course-section, semester-long structure)
        │
        ▼
course_homepage_build.py reads schedule + today's date
        │
        ▼
Pure HTML + inline CSS rendered with current week pre-expanded
        │
        ▼
PUSH to Canvas /front_page (with --apply) OR write to local file
```

The regenerate trigger is the operator's choice:

| Trigger | Cadence | Pros | Cons |
|---|---|---|---|
| Manual `--apply` on Monday morning | Weekly | Zero infrastructure; instructor is paying attention then anyway | Depends on instructor habit |
| Local cron on operator's machine | Daily / hourly | Hands-off if their machine is on | Machine-on dependency |
| GitHub Actions scheduled workflow | Configurable | Cloud-run; reliable | Needs Canvas token as repo secret; cloud dependency |

The page itself contains NO JavaScript. Pure HTML + inline `<style>` block. Robust in Canvas's WYSIWYG editor.

## The schedule.yml schema (the source of truth)

One file per course-section. Lives in the consumer repo (the instructor's repo that vendors canvas-toolbox), NOT in canvas-toolbox itself — it's per-course state.

```yaml
course:
  name: "REL 130 — Missionary Preparation"   # REQUIRED — visible header
  code: "REL 130"                             # REQUIRED — visible header chip
  base_url: "https://institution.instructure.com"  # REQUIRED — for module links
  course_id: 415138                            # REQUIRED — for module links
  banner_url: "https://..."                    # OPTIONAL — top banner image

quick_links:                                   # OPTIONAL — top quick-link tiles
  - title: "Syllabus"
    href: "/courses/415138/assignments/syllabus"
    icon: "📄"                                 # emoji or text; no FA dependency

weeks:                                         # REQUIRED — the semester schedule
  - week: 1                                    # week number (used in #week-N anchor)
    module_id: 4592419                         # Canvas module ID; used for "Open module" link
    title: "Week 01: Come Unto Christ"         # REQUIRED — section title
    start: 2026-04-18                          # REQUIRED — ISO date YYYY-MM-DD
    end: 2026-04-24                            # REQUIRED — ISO date YYYY-MM-DD
    summary: "Optional intro text..."          # OPTIONAL — shown inside the expanded section

style:                                         # OPTIONAL — color/font overrides
  primary_color: "#800000"
  secondary_color: "#f5f5f5"
  current_color: "#FFD700"
  font_family: "system-ui, ..."
```

The full example with comments lives at `lib/agents/templates/course_homepage/schedule.example.yml`.

## Workflow for an instructor adopting this

### One-time setup (per course)

```bash
# 1. Bootstrap a starter schedule from the course's current Canvas modules
uv run python lib/tools/course_homepage_build.py \
    --bootstrap-from-canvas --course-id 415138 \
    --output schedule.yml

# 2. Hand-edit the schedule:
#    - Fill in <EDIT> date placeholders the bootstrap couldn't infer
#    - Clean up module titles if needed
#    - Add quick_links + style overrides
#    - Add summary text per week (optional)
$EDITOR schedule.yml
```

### Per-week (or per-day) refresh

```bash
# Render to a local file for review
uv run python lib/tools/course_homepage_build.py \
    --schedule schedule.yml --output homepage.html

# Preview at a future date (e.g., what will week 6 look like?)
uv run python lib/tools/course_homepage_build.py \
    --schedule schedule.yml --output homepage.html --date 2026-05-15

# Push to Canvas (overwrites the course's front_page)
uv run python lib/tools/course_homepage_build.py \
    --schedule schedule.yml --apply
```

## Pure-CSS techniques used (and why)

Three patterns make this work without JavaScript:

| Pattern | What it gives | Why this one |
|---|---|---|
| **Anchor-jump links** (`<a href="#week-04">`) | Click button → page scrolls to that week's section | Pure HTML, robust in Canvas's editor, screen-reader friendly |
| **`<details>/<summary>` accordions** | Click summary → section expands/collapses | Native HTML element, no CSS hack, accessible by default |
| **`<details open>` for the current week** | Current week is pre-expanded at render time | Set by the build script based on today + schedule; baked into HTML |
| **CSS `:scroll-behavior: smooth`** | Smooth scroll instead of jump | Nice-to-have; degrades gracefully |
| **CSS grid for responsive tiles** | Mobile / tablet / desktop layouts | One stylesheet covers all viewports |

Techniques DELIBERATELY AVOIDED:

| Pattern | Why not |
|---|---|
| `:target` pseudo-class for tab-switching | Canvas's WYSIWYG editor often strips `<style>` blocks on re-edit; breaks the pattern |
| Radio-button + `:checked` hack | Same fragility + accessibility concerns |
| JavaScript anywhere in the page body | Canvas sandboxing; portability across institutions; cost-savings goal explicitly avoids JS injection |
| External CSS via `<link>` | Adds a dependency; Canvas's allowed-CDN list is institution-specific |
| Font Awesome via CDN | Same dependency concern; emoji / SVG inline is simpler |

## Accessibility

- All buttons are `<a>` tags with descriptive text → screen-reader friendly
- `<details>/<summary>` is the native HTML accordion pattern, fully ARIA-compliant by default
- `<nav>` elements wrap link groups for semantic clarity
- Color choices need a 4.5:1 contrast ratio minimum — the `style.primary_color` + `style.current_color` should be reviewed against WCAG 2.1 AA before going live; consider running `accessibility_audit.py` on the rendered page (it doesn't catch live-CSS contrast specifically but the rest of the WCAG checks apply)

## FERPA notes

The tool reads:
- Course metadata (name, code) — institutional metadata, NOT student data
- Module structure (names, dates) — course-design metadata, NOT student data

The tool does NOT read:
- Any student submissions
- Any enrollments
- Any grades

The rendered HTML contains NO student information. FERPA-clean by construction.

## Decision tree: when NOT to use this

| If... | Use instead |
|---|---|
| The course doesn't follow a weekly cadence (free-form units) | Manual home page; `course_map_build.py` for the structural map |
| You need real-time updates (sub-day precision matters) | DesignPLUS or accept the cadence-gap |
| Your institution still has DesignPLUS licensed + the team prefers it | Keep DesignPLUS; this tool's value is for the DesignPLUS-free case |
| You want a syllabus page, not a home page | Use Canvas's built-in syllabus tool |

## Integration with other canvas-toolbox tools

- **`course_audit.py --full`** — could be extended with a "home page out of sync with current modules" check (parking-lot follow-up)
- **`canvas_pages.py`** — shared helper for "upsert a page" mechanics; the push path uses the same auth + guard discipline
- **`canvas_course_guard.py`** — the `--apply` mode enforces the enrolled-course write-gate; canvas-toolbox standard
- **`course_map_build.py`** — sibling tool with similar shape (reads Canvas + template, renders structured doc); operators familiar with course_map will find course_homepage's mental model familiar

## Anti-patterns to refuse if an instructor asks

- **"Can you add JavaScript that fetches the module list at page load?"** No — defeats the whole point. The cadence-regenerate model solves this without JS.
- **"Can you embed the entire syllabus in the homepage?"** Bad UX (huge wall of text); use a quick_link to the syllabus page instead.
- **"Can you make each week's section show the assignments INLINE (not just a link to the module)?"** Possible v0.2 enhancement — would need to fetch module ITEMS at bootstrap time + embed them. Defer until an instructor asks.
- **"Can you sync the schedule.yml back from Canvas changes automatically?"** Out of scope for v0.1. The schedule.yml is the SOURCE of truth (versioned, plannable); Canvas is the TARGET. If you change Canvas, re-run `--bootstrap-from-canvas` to detect the new structure + merge by hand.

## Bootstrap-from-Canvas caveats

The `--bootstrap-from-canvas` flag is a STARTER — output needs hand-editing:

- Modules without "Week N" / "Wk N" / "Unit N" in the title are SKIPPED (intentional; resource / overview modules don't fit the per-week structure)
- Module `unlock_at` is used as the week's `start`; the NEXT module's `unlock_at - 1 day` is used as `end`
- Modules with no `unlock_at` get `<EDIT: ...>` placeholders that the validator refuses to accept until filled in
- This is a feature: the bootstrap won't silently produce a wrong schedule; it forces the operator to make explicit choices

## Cross-reference

- Tool: `lib/tools/course_homepage_build.py`
- Template: `lib/agents/templates/course_homepage/schedule.example.yml`
- Tests: `lib/tests/test_course_homepage_build.py`
- Design discovery: `handoffs/2026-06-22_designplus-replacement-discovery.md` (gitignored; local-only)
- Source HTML referenced: `handoffs/2026-06-22_missionary-prep-homepage-source.html` (gitignored; local-only)
- Working-style rule it operationalizes: AGENTS.md → "Deterministic-first grader design" — this tool's `course_homepage_build.py` is a pure-Python deterministic generator; no LLM in the loop. Date matching is a regex/comparison; rendering is string templating. Lean Python, not LLM.
