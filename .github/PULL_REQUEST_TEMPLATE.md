<!--
Welcome — thanks for the PR.

If this PR is BIG (>200 lines or touches multiple tools), consider filing
a `share:` issue first describing the design — keeps the PR review focused
on code, not design debate. See CONTRIBUTING.md → Communication for the why.
-->

## Summary

<!-- 1-3 sentences. What does this PR change and why? -->

## Test plan

<!-- How did you verify the change works? Examples:
     - Ran `uv run pytest lib/tests/ -k "not sprint"` — 208 passing
     - Ran `uv run python lib/tools/<tool>.py --help` — output unchanged
     - Manual end-to-end against CANVAS_SANDBOX_ID — confirmed X behavior
     - Added new tests under `lib/tests/test_<tool>.py` — covers Y, Z cases
-->

## Pre-merge checklist

- [ ] Pre-commit hooks pass locally (`uv run pre-commit run --all-files`)
- [ ] Pure-logic tests added/updated for new code (under `lib/tests/`)
- [ ] AGENTS.md Active Context updated if behavior changed
- [ ] Triple-version-sync if `pyproject.toml`'s `[project].version` is bumped (also bump `.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json`)
- [ ] FERPA two-zone architecture preserved (names stay in local zone; deid'd content for anything an AI reads)

## Related issue / context

<!-- Closes #123, or "follow-up to the v0.X.Y conversation in handoffs/..." -->
