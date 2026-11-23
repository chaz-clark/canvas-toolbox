# Domain Docs

How the engineering skills read this repo's domain documentation.

## Before exploring, read these

- **`GLOSSARY-MAP.md`** at the repo root. It points to the one glossary: **`knowledge/glossary.md`** (it lives under `knowledge/` so it ships to every course folder).
- **Decisions** in `docs/architecture/`, named `adr-NNN-<slug>.md` (e.g. `adr-001-runtime-neutral-agent-packages.md`). Read the ones that touch the area you're working in.

## Writing them

- A resolved term goes into `knowledge/glossary.md` at once, in its format (bold term, one- or two-sentence definition, `_Avoid_:` list). AGENTS.md's rule: **a new concept gets its glossary entry in the same PR that first names it.**
- A new decision record goes in `docs/architecture/` as the next `adr-NNN-<slug>.md`, **not** in `docs/adr/`. Write one only when all three hold: hard to reverse, surprising without context, and the result of a real trade-off. One paragraph is enough.

## Use the glossary's vocabulary

When your output names a domain concept (an issue title, a proposal, a test name, a flag), use the glossary's term, never one on its *Avoid* list. If the concept isn't in the glossary yet, either you're inventing language the project doesn't use (reconsider), or there's a real gap (add the entry, per the rule above).

## Flag decision conflicts

If your output contradicts an existing decision record, say so explicitly rather than silently overriding it:

> _Contradicts adr-001 (runtime-neutral agent packages), but worth reopening because…_
