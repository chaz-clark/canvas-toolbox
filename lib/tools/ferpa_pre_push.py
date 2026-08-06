#!/usr/bin/env python3
"""pre-push FERPA guard — the git layer (#285).

WHY THIS EXISTS
  `grade_guardian` stops the AGENT reading or shell-reading a Zone-2 file. Nothing
  stopped the same data reaching a remote. All three incidents in the constitution's
  record are agent-side; that isn't evidence the git layer is safe, only that it
  hasn't been exercised. And unlike a bad read, **a push cannot be undone** — it is
  cloned, cached and indexed by things you don't control.

WHY NOT JUST A pre-commit HOOK
  A commit hook catches a mistake as you make it and misses: anything committed
  before the hook existed, anything committed with --no-verify, anything committed
  on another machine, and anything correct at commit time that a LATER ignore-rule
  change exposes. That last one is the one that actually happened: a consumer
  inverted a grading ignore block from deny-with-allowlist to source-tracked-by-
  default, and the blanket line removed had been the sole cover for three other
  name-bearing paths. Nothing about that sequence is visible to a commit hook. It is
  visible at push.

  So this checks the COMMIT RANGE, not the working tree. History is what gets
  published; a later commit deleting a file does not unpublish it.

ONE PATTERN LIST, NOT TWO
  Patterns come from `grade_guardian.load_zone2()` — the same `.claude/ferpa_zone2.txt`
  the agent-layer hook reads. A second list would drift, which is the exact bug 1.16.0
  fixed one layer down after `_FERPA_PATH` and `_FERPA_FILE` had already diverged.

GRADED, NOT ALL-ON
  Path checks run by default: cheap, deterministic, near-zero false positives.
  Content scans are OPT-IN (`touch .claude/ferpa_scan_content`) because a roster
  surname scan blocks on any tracked file containing a common surname — ordinary
  prose, citations and package names all trip it, and for an operator who can't read
  the regex that's an unexplainable wall in front of their own work.

  It never silently degrades. If a scan is skipped, it says so — a guard that quietly
  does less is the same false confidence #278 was filed about.

FILENAMES ARE WITHHELD FROM OUTPUT
  A matched path may itself carry a student name (`submissions_raw/Lastname_First…`).
  The report names the PATTERN and the containing directory, never the leaf, and
  tells the operator how to list them locally.

HOW GIT INVOKES IT
  Installed at `.git/hooks/pre-push` by cb_update. Git pipes
  `<local ref> <local sha> <remote ref> <remote sha>` lines on stdin. Exit non-zero
  blocks the push. Fails OPEN on internal error — a guardrail must never brick a repo.

  NOT via `core.hooksPath`: that is consulted INSTEAD OF `.git/hooks/`, so setting it
  makes an existing `.git/hooks/pre-commit` inert (and `pre-commit install` then
  refuses to run). Installing to the path git already reads avoids that entirely, and
  cb_update is itself the per-clone step, which is what "hooks aren't cloned" needs.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

try:
    from _env_loader import force_utf8_console
except ImportError:
    def force_utf8_console() -> None:
        pass

try:
    from grade_guardian import load_zone2, compile_zone2, credential_path_re
except ImportError:                      # standalone / partial vendoring
    load_zone2 = compile_zone2 = credential_path_re = None

_NULL_SHA = "0" * 40
_SCAN_CONTENT_FLAG = ".claude/ferpa_scan_content"

# A uid -> name mapping in any serialization: the single most dangerous artifact,
# because it re-identifies every code in the repo at once. Deterministic enough to
# be worth scanning for; unlike a surname it can't collide with ordinary prose.
# `[ ,]{1,2}` not `[ ,]`: the CSV form is `1395396,"Farmer, Andrew"` — a comma AND a
# space between the name parts. That's the .deid_master.csv shape, i.e. the case this
# most needs to catch. Deliberately not `\s`, which would span newlines.
_UID_NAME_MAP = re.compile(
    r"""["']?\b\d{4,9}\b["']?[ ]*[:=,][ ]*["'][A-Z][a-z]+(?:[ ,]{1,2}[A-Z][a-z]+)+["']"""
)


def parse_push_specs(stdin_text: str) -> list[tuple[str, str]]:
    """Git's pre-push stdin → [(local_sha, remote_sha)] worth checking.

    Skips branch DELETIONS (local sha all-zeros): nothing is being published. A
    remote sha of all-zeros means a NEW branch — the caller resolves that range
    against all remotes rather than a nonexistent base."""
    out = []
    for line in stdin_text.splitlines():
        parts = line.split()
        if len(parts) != 4:
            continue
        _, local_sha, _, remote_sha = parts
        if local_sha == _NULL_SHA:
            continue                       # deleting a ref — publishes nothing
        out.append((local_sha, remote_sha))
    return out


def range_args(local_sha: str, remote_sha: str) -> list[str]:
    """`git log` args for the commits this push would publish.

    New branch (remote all-zeros) is the case a naive `remote..local` gets wrong —
    there is no base, so `--not --remotes` excludes everything already published
    anywhere rather than walking the repo's entire history and blocking on an
    ancient commit that is not being pushed."""
    if remote_sha == _NULL_SHA:
        return [local_sha, "--not", "--remotes"]
    return [f"{remote_sha}..{local_sha}"]


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args],
                       capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def changed_paths(repo: Path, args: list[str]) -> list[str]:
    """Every path touched by the commits in range, deduped. Uses --name-only over
    the RANGE (not the worktree) so a file added and later deleted is still caught —
    it is in the history being published either way."""
    out = _git(repo, "log", "--format=", "--name-only", *args)
    return sorted({ln.strip() for ln in out.splitlines() if ln.strip()})


def match_paths(paths: list[str], path_re) -> list[str]:
    return [p for p in paths if path_re.search(p)]


def scan_content(repo: Path, args: list[str], paths: list[str],
                 roster: list[str]) -> list[str]:
    """OPT-IN. Returns the paths whose blob in this range carries a uid->name map or
    a roster surname. Reads blobs from git rather than the worktree, since the
    worktree may no longer contain what history does."""
    hits = []
    for p in paths:
        blob = ""
        for sha in _git(repo, "log", "--format=%H", *args).split():
            blob = _git(repo, "show", f"{sha}:{p}")
            if blob:
                break
        if not blob:
            continue
        if _UID_NAME_MAP.search(blob):
            hits.append(p)
            continue
        for name in roster:
            if name and re.search(rf"\b{re.escape(name)}\b", blob):
                hits.append(p)
                break
    return hits


def _load_roster(repo: Path) -> list[str]:
    """Surnames for the opt-in scan. Reading `.known_names.txt` here is the same
    sanctioned exception `grader_name_leak_check.py` already relies on — a local
    tool may read it; nothing is surfaced to an LLM and no name is ever printed."""
    try:
        text = (repo / "grading" / ".known_names.txt").read_text(encoding="utf-8")
    except (OSError, ValueError):
        return []
    names = []
    for raw in text.splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            names.extend(t for t in re.split(r"[\s,]+", line) if len(t) >= 4)
    return sorted(set(names))


def _dirs_of(paths: list[str]) -> list[str]:
    """Containing directories, deduped. The LEAF is withheld deliberately — a
    matched filename may itself carry a student name."""
    return sorted({(str(Path(p).parent) + "/").replace("./", "") or "./" for p in paths})


def format_block(path_hits: list[str], content_hits: list[str],
                 scanned_content: bool) -> str:
    """The denial an operator actually has to act on. A blocked push arrives at the
    moment someone is trying to share their work, and the honest remedy (rewriting
    history) is beyond most faculty — so this leads with the fix that does NOT
    require it. A message that only says what is wrong produces `--no-verify`."""
    n = len(set(path_hits) | set(content_hits))
    lines = [
        "",
        "⛔ PUSH BLOCKED — FERPA Zone-2 data in the commits being pushed.",
        "",
        f"  {n} file(s) in this push match a protected pattern.",
        "  Filenames are withheld here on purpose — a matched filename may itself",
        "  contain a student name. Directories only:",
        "",
    ]
    for d in _dirs_of(path_hits + content_hits):
        lines.append(f"      {d}")
    if content_hits:
        lines += ["", "  Some matched on CONTENT (a uid→name map or a roster name),",
                  "  not just their path."]
    if not scanned_content:
        lines += ["", "  NOTE: content scanning is OFF (path checks only). Enable with",
                  f"  `touch {_SCAN_CONTENT_FLAG}` — it catches name-bearing files at",
                  "  unremarkable paths, at the cost of occasional false positives."]
    lines += [
        "",
        "WHAT TO DO — in order:",
        "",
        "  1. See which files, locally:",
        "       git log --format= --name-only <your-branch> | sort -u",
        "",
        "  2. If they should never have been committed, the SAFEST fix — no history",
        "     rewriting, nothing destructive:",
        "       git switch -c clean-work            # fresh branch",
        "       # re-add only the files you mean to publish, commit, then:",
        "       git push -u origin clean-work",
        "",
        "  3. Rewriting history (git filter-repo, interactive rebase) removes them",
        "     from past commits, but is easy to get wrong and rewrites what others",
        "     may have pulled. Ask before doing this on a shared repo.",
        "",
        "  4. FALSE POSITIVE? If the match carries no student data, narrow the",
        "     pattern in .claude/ferpa_zone2.txt — don't disable the hook.",
        "",
        "  --no-verify would publish this. That cannot be undone.",
        "",
    ]
    return "\n".join(lines)


HOOK_BODY = """\
#!/bin/sh
# canvas-toolbox FERPA pre-push guard (#285). Reinstalled by cb_update.
# FAILS OPEN if the toolkit is missing — a guardrail must never brick a repo.
f="$(git rev-parse --show-toplevel)/{subdir}/lib/tools/ferpa_pre_push.py"
[ -f "$f" ] || exit 0
exec python3 "$f"
"""


def ensure_pre_push_hook(repo: Path, toolkit_subdir: str, apply: bool) -> str:
    """Install `.git/hooks/pre-push`. Returns present/would-install/installed/
    skip-foreign/no-git.

    Deliberately NOT `core.hooksPath`: git consults that INSTEAD OF `.git/hooks/`,
    so setting it silently disables an existing `.git/hooks/pre-commit` (and
    `pre-commit install` then refuses to run at all). Writing the file git already
    reads has no such collateral. The "hooks aren't cloned" problem is real — and is
    solved by cb_update being the per-clone step, not by moving the hooks directory.

    Never clobbers a hook we didn't write."""
    hooks = repo / ".git" / "hooks"
    if not (repo / ".git").is_dir():
        return "no-git"
    body = HOOK_BODY.format(subdir=toolkit_subdir)
    target = hooks / "pre-push"
    if target.is_file():
        existing = target.read_text(encoding="utf-8", errors="replace")
        if "canvas-toolbox FERPA pre-push guard" not in existing:
            return "skip-foreign"          # someone else's hook — theirs to keep
        if existing == body:
            return "present"
    if not apply:
        return "would-install"
    hooks.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    target.chmod(0o755)
    return "installed"


def main() -> int:
    force_utf8_console()
    if "--help" in sys.argv[1:]:
        print(__doc__.split("\n")[0])
        return 0
    if load_zone2 is None:
        return 0                            # no pattern source → fail open
    repo = Path(_git(Path.cwd(), "rev-parse", "--show-toplevel").strip() or ".")
    try:
        specs = parse_push_specs(sys.stdin.read())
    except (OSError, ValueError):
        return 0
    if not specs:
        return 0

    entries, _ = load_zone2(repo)
    zone2_re, _ = compile_zone2(entries)
    # Credentials too (#288). `.env` is gitignored today — but #285 exists because an
    # ignore-rule restructure quietly stopped covering three paths, and a pushed token
    # is usable by anyone who finds it the moment it lands.
    cred_re = credential_path_re() if credential_path_re else None
    path_re = re.compile(f"{zone2_re.pattern}|{cred_re.pattern}", re.IGNORECASE) \
        if cred_re else zone2_re
    scan_on = (repo / _SCAN_CONTENT_FLAG).exists()
    roster = _load_roster(repo) if scan_on else []

    path_hits, content_hits = [], []
    for local_sha, remote_sha in specs:
        args = range_args(local_sha, remote_sha)
        paths = changed_paths(repo, args)
        path_hits += match_paths(paths, path_re)
        if scan_on:
            rest = [p for p in paths if p not in set(path_hits)]
            content_hits += scan_content(repo, args, rest, roster)

    if not (path_hits or content_hits):
        return 0
    print(format_block(sorted(set(path_hits)), sorted(set(content_hits)), scan_on),
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:                       # noqa: BLE001 — fail OPEN, always
        raise SystemExit(0) from None
