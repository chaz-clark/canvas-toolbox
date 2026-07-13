# Contributing to canvas-toolbox

Thanks for thinking about giving back. This doc covers **three contribution
shapes**, from lightest to heaviest:

1. **Report a bug or request a feature** — `bin/cb-report-bug`
2. **Share something you built locally** — `bin/cb-share`
3. **Push code via a pull request** — standard GitHub PR workflow

If you're not sure which one fits, **start with #1 or #2** — the maintainer
will tell you if a PR is the better path. There's no rule that says small
fixes need PRs.

---

## 1. Report a bug or request a feature

Use this when the toolkit broke, surprised you, or you want it to do something
it doesn't yet.

```bash
./bin/cb-report-bug
# (your editor opens — fill in a description + a title with the right prefix)
# bug: <short title>          ← toolkit broke
# enhancement: <short title>  ← want a feature
```

No GitHub account, no `gh` CLI, no browser auth required. The CLI scrubs PII
locally (names, emails, `/Users/` paths) before posting through a
Cloudflare-fronted intake worker that files the GitHub issue.

Full docstring + flags: [`lib/tools/cb_report_bug.py`](../lib/tools/cb_report_bug.py).
Worker architecture: [`bug-intake-worker/README.md` (edge-infra sister repo)](https://github.com/chaz-clark/edge-infra/blob/main/workers/bug-intake-worker/README.md).

---

## 2. Share something you built

Use this when you've already built a tool / config pattern / workflow
extension and want to contribute it back — distinct from "I wish the
toolkit did X" because you've already done X locally.

```bash
./bin/cb-share
# Title: share: <what you built>
# Body should include:
#   - What it does and what use case it solves
#   - A link to a gist / branch / paste of the code or config
#   - Any environment / FERPA notes
```

The maintainer triages `share:` issues differently from `enhancement:` ones —
they're already-built contributions waiting for integration, not feature
requests waiting for someone to do the work.

If your contribution is substantial (>200 lines, touches multiple tools,
introduces a new module), the maintainer may ask you to convert it into a
pull request (path #3 below). For small patterns / configs / single-tool
additions, the `cb-share` path is usually enough.

---

## 3. Push code via a pull request

Use this when you have a branch you want merged. Standard GitHub PR workflow:

```bash
# 1. Fork chaz-clark/canvas-toolbox on GitHub
# 2. Clone your fork + branch
git clone https://github.com/<you>/canvas-toolbox.git
cd canvas-toolbox
git checkout -b feat/<short-description>

# 3. Make changes; commit; push
# (the pre-commit hooks run ruff + actionlint + shellcheck on your changes)
git add ... && git commit -m "..."
git push origin feat/<short-description>

# 4. Open the PR on GitHub
gh pr create --base main --title "..." --body "..."
```

### Pre-commit hooks (required)

After cloning, install the pre-commit hooks once:

```bash
uv run pre-commit install
```

They run automatically on every `git commit`:

- **ruff** — Python lint (bug-catching rules; see `[tool.ruff]` in
  `pyproject.toml` for the rule set)
- **actionlint** — `.github/workflows/*.yml` syntax + action issues
- **shellcheck** — `scripts/` and `bin/` shell scripts

To run them manually against the whole tree:

```bash
uv run pre-commit run --all-files
```

### Tests (required)

Before opening the PR:

```bash
uv run pytest lib/tests/ -k "not sprint"
```

The `-k "not sprint"` deselects the Canvas-API regression suite that needs
`CANVAS_SANDBOX_ID` + a real token. The pure-logic unit tests run in any
environment and must pass.

If your change adds a new tool with pure-logic helpers, **please add a
matching test file** under `lib/tests/test_<your_tool>.py` following the
existing patterns (e.g. [`test_grader_filename_parsing.py`](../lib/tests/test_grader_filename_parsing.py)).

### Windows testing (required for cross-platform changes)

If your change has **potential for Mac/Windows differences**, test on Windows 11 before opening the PR:

**When Windows testing is required:**
- Console output (Unicode glyphs, encoding, color codes)
- File path handling (`/` vs `\`, case sensitivity)
- Shell command execution (`cmd.exe` vs `bash`)
- Environment variable handling (`%VAR%` vs `$VAR`)
- Line ending handling (CRLF vs LF)

**How to test via Parallels CLI** (macOS → Windows 11):

```bash
# Resume Windows 11 VM
prlctl resume "Windows 11"

# Run your test script
prlctl exec "Windows 11" cmd /c "\"C:\Program Files\Python311\python.exe\" C:\test_script.py"

# Suspend when done
prlctl suspend "Windows 11"
```

**Why this matters:** Issue #123 (Windows UTF-8 console crash) shipped and broke Windows users because Unicode glyphs (✓, —, ⏭) weren't tested on `cp1252` console before release. The Parallels CLI workflow prevents this class of bug.

If you don't have Windows 11 available, note that in your PR and the maintainer will test it.

### What the maintainer reviews

- Does it match the project rules in [`AGENTS.md`](../AGENTS.md) → Working Style?
  Especially: local-files-are-source-of-truth, match by title not ID, confirm
  scope before any write, run `course_quality_check.py` after Canvas pushes.
- FERPA discipline (no names in console output, two-zone architecture
  preserved, deid before any LLM call, the salt+pseudonym pattern).
- New tools have a `--help` that explains what they do + `--version` flag +
  some pure-logic unit tests.
- Changes that touch multiple tools are split across multiple commits where
  reasonable, not a single mega-diff.

If you're not sure whether your change fits the project's shape, **open a
draft PR early** or use `cb-share` first — easier to course-correct before
hours of code than after.

---

## What the maintainer is NOT looking for

- **Style-only PRs** — ruff handles those; the maintainer is not interested
  in reformat-only diffs unless paired with substantive change.
- **Tool-renaming PRs** — the existing naming is shipped + referenced
  across vended consumer repos; renames are expensive.
- **PRs that remove FERPA scrubbing layers** under any optimization claim.
  The two-zone architecture is non-negotiable.
- **Demographic data integrations** without a documented institutional
  research partnership. See `handoffs/parkinglot.md` → "Demographic
  enrichment" for the design constraints.

---

## Communication

If a PR conversation runs long, it's normal for the maintainer to ask you
to use `cb-share` to file the design + then split the code change into
smaller PRs. The `cb-share` issue becomes the design discussion; the PRs
become the implementation. This keeps the PR review focused on code, not
design debate.

For substantive questions before you start coding, **use `cb-share` first**.
A 10-line issue describing what you're thinking of building costs the
maintainer ~2 minutes to read + reply — much cheaper than reviewing a
~500-line PR that needs significant rework.

---

## License

By contributing, you agree your contribution is licensed under the MIT
License (see [`LICENSE`](../LICENSE)). canvas-toolbox is brain-agnostic by
design — contributions should keep that property (don't lock the toolkit
to a specific LLM provider in tools that work without one).
