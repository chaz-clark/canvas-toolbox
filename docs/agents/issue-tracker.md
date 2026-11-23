# Issue tracker: GitHub

Issues and specs for canvas-toolbox live as GitHub issues on `chaz-clark/canvas-toolbox`. Use the `gh` CLI for all operations.

**This repo is PUBLIC.** Nothing in an issue may identify a student (no names, no user ids next to a grade, no submission text), and nothing may describe private work in other repos. Faculty report problems through `cb_report_bug.py`, which scrubs its report first; security problems never go here (see `.github/SECURITY.md`).

## Conventions

- **Create an issue**: `gh issue create --title "..." --body-file - <<'EOF'` (a heredoc for multi-line bodies). Title prefixes match `cb_report_bug.py`: `bug:` or `enhancement:`.
- **Read an issue**: `gh issue view <number> --json number,title,body,labels,comments`.
- **List issues**: `gh issue list --state open --json number,title,labels` with `--label` / `--state` filters.
- **Sub-issue of a parent**: `gh issue create --parent <parent> ...` (`gh` 2.94+); otherwise put `Part of #<parent>` at the top of the child's body.
- **Blocking**: GitHub's native issue dependencies: `gh issue create --blocked-by <n>,<n> ...` or `gh issue edit <child> --add-blocked-by <blocker>` (`gh` 2.94+). Where those aren't available, a `Blocked by: #<n>` line at the top of the child's body. A ticket is unblocked when every blocker is closed.
- **Comment**: `gh issue comment <number> --body "..."`
- **Labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: comment the explanation first (`gh issue comment`), then `gh issue close <number>`.

File issues only into this repo. Never into `mattpocock/skills`.

## Pull requests as a triage surface

**PRs as a request surface: no.**

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Read it as in **Read an issue** above.
