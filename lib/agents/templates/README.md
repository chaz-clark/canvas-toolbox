# Agent Templates

Reusable artifacts the audit agents can read, inject, or hand to instructors as drop-in components. Distinct from `agents/knowledge/` (which is *conceptual* — theory, principles, audit indicators) and from `agents/<agent>.md/.json` (which is *agent specification* — mission, workflow, tool definitions).

Templates are the **implementation layer**: actual HTML, JSON, or text files an agent can use without rewriting from scratch.

## Why a separate folder

The [`agents/knowledge/README.md`](../knowledge/README.md) explicitly defines knowledge files as conceptual references — theory and audit signals, not implementation. Stuffing HTML or JSON templates into a knowledge file dilutes that conceptual layer. Templates live here instead, referenced from knowledge files where appropriate.

This also positions cleanly for the future deployable-skill direction: when a knowledge area becomes a `.agents/skills/<skill-name>/` package per the [Agent Skills standard](https://agentskills.io/specification), templates here map cleanly to that skill's `assets/` directory. See [`AGENTS.md`](../../../AGENTS.md#roadmap) Roadmap items 1–3.

## Layout convention

Two valid layouts depending on size:

**(a) Subdirectory per template-set** — for multi-file sets (multiple HTML components, JSON shapes, etc.):

```
agents/templates/
├── README.md                          ← this file
└── <framework_name>/                  ← e.g., byui_course_design/
    ├── README.md                      ← describes the template-set
    ├── <component>.html               ← e.g., core_questions_callout.html
    ├── <component>.json               ← e.g., rubric_3level.json
    └── ...
```

**(b) Flat file** — for single-template sets where a subdirectory would be ceremony:

```
agents/templates/
├── README.md                          ← this file
└── <template_name>.md                 ← e.g., course_map_blank.md
```

A template-set's `README.md` (subdirectory layout) should document:

- What framework or knowledge file the templates support
- Each template's purpose, inputs (placeholder variables), and where it gets injected
- Naming conventions used inside the template-set

For flat single-file templates, the file's own front-matter / opening paragraphs serve the same purpose, and the entry below in "Currently active template-sets" documents it.

## Naming

- Template files use **lowercase + underscores**: `core_questions_callout.html`, not `CoreQuestionsCallout.html`
- Subdirectories use **lowercase + underscores**: `byui_course_design/`, not `BYUI-Course-Design/`
- Use the file extension that matches the artifact type (`.html`, `.json`, `.md`, etc.)

## Reference pattern from knowledge files

Knowledge files reference templates by relative path:

> Use the Core Questions callout when introducing module outcomes. See [`agents/templates/byui_course_design/core_questions_callout.html`](../templates/byui_course_design/core_questions_callout.html).

Don't inline the template body in the knowledge file. The reference is the contract; the template file is the implementation.

## Adding a new template-set

1. Create `agents/templates/<framework_name>/`
2. Add a `README.md` documenting the set
3. Add the template files
4. From the corresponding `agents/knowledge/<framework>_knowledge.md`, reference each template at the point in the prose where the agent should use it
5. Update this top-level README's "Currently active template-sets" list (below)

## Currently active template-sets

| Set | Used by | Contents |
|---|---|---|
| [`byui_course_design/`](byui_course_design/) | [`agents/knowledge/course_design_language_knowledge.md`](../knowledge/course_design_language_knowledge.md) | 11 HTML component templates (banner wrapper, Core Questions callout, section header, Purpose+Outcome pair, red Readings card, tan Architect's Lens card, Weekly Schedule table, assignment Purpose+Overview, Instructions+Parts, Submission Criteria, Architect's Reflection closing card) + 1 canonical 3-level rubric JSON shape |
| [`course_map_blank.md`](course_map_blank.md) | [`agents/knowledge/learned/2026-06-05_course-map-from-canvas-pass-1-lessons.md`](../knowledge/learned/2026-06-05_course-map-from-canvas-pass-1-lessons.md) | Blank Markdown template for the *Architects of Learning* "Course Map & Schedule" assignment artifact. University-agnostic — works for any institution's AoL-style course-design submission. 6 sections covering Course Outcomes & Assessment Strategy (1.1-1.4), optional Assessment Design Deep-Dive (1.5), At-a-Glance (2), Per-Module Details (3), Semester Schedule (4), Pacing Reflection (5), Appendix (6). Validated against two filled exemplars (Data Warehousing online pilot + Construction Mgmt campus). Generator script at `/tmp/build_course_map_v11.py` (promotion to `lib/tools/` pending). |
