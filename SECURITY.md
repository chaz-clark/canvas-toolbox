# Security policy

`canvas-toolbox` touches student data through Canvas. The whole architecture
is built on FERPA discipline (see the two-zone boundary in
[`grading_readme.md`](grading_readme.md)). A security flaw — particularly
one that could leak student PII past the deid layer or expose the bug-intake
worker's PAT — has higher stakes than a normal bug.

## Reporting a vulnerability

**Don't file a public GitHub issue.** Don't use `cb_report_bug.py` either
(it files publicly). Both surface the problem in a place attackers can read.

Instead, **use GitHub's Private Vulnerability Reporting:**

1. Go to https://github.com/chaz-clark/canvas-toolbox/security/advisories
2. Click **Report a vulnerability** (button at top right).
3. Fill in the form. The report is private to the maintainer + you,
   end-to-end through GitHub's UI.

You'll need a (free) GitHub account to file. That's the only friction —
in exchange you get an authenticated, audited channel that's resistant
to scraping / spam, and the maintainer gets in-platform notifications
the same way they'd see a PR.

Include:
- A description of the issue (what / where / who's affected).
- A proof-of-concept if you have one (the smallest reproduction that
  shows the problem).
- The toolkit version where you found it (`uv run python lib/tools/grader_fetch.py --version`).

You'll get an acknowledgment within ~48 hours. Triage + fix timeline
depends on severity:

| Class | Example | Target turnaround |
|---|---|---|
| **Critical** | Name / PII leaking past the deid scrub into AI-safe paths; PAT extraction from the worker | 24-72 hours to a patched release |
| **High** | FERPA-class gate bypass (e.g., `_challenge_dir_guard` defeated); push-gate bypass | 1 week |
| **Medium** | Logic bug that requires unusual operator action to trigger | 2 weeks |
| **Low** | Hardening opportunity, defense-in-depth gap | Best-effort, next release |

## What I commit to

- **Acknowledge** every report. Even "false alarm" / "not actually a bug"
  gets a reply explaining the reasoning.
- **Coordinate** disclosure. We agree on a public-disclosure date AFTER
  the fix ships, so consumer repos have a clean window to update before
  the world knows about the gap. Standard 90-day disclosure default if
  no other agreement.
- **Credit** the reporter in the fix's commit message + the CHANGELOG
  entry, if they want it. (Or not — anonymous reports are equally
  welcomed.)
- **Rotate the worker PAT** on any vulnerability touching the
  Cloudflare intake path, even if the root cause is elsewhere.

## What's NOT in scope

These are intentional design choices, not vulnerabilities:

- **The bug-intake worker is open-by-design.** Anyone can POST a bug
  report; the rate limiter (5/IP/hour) is to prevent flooding, not to
  authenticate. We accept spam issues as the cost of zero-friction
  faculty reporting. If you find a way around the rate limiter, that
  IS in scope (please report).
- **`canvas_course_guard` warnings, not blocks.** On read-only mode the
  guard advises but doesn't refuse. That's by design — read operations
  against the wrong course are recoverable. The block fires on write
  mode only. If you find a write path that bypasses the guard, that IS
  in scope.
- **Faculty can choose to disable scrubbing.** `cb_report_bug.py`
  defaults to scrubbing; passing a body that bypasses the scrub IS
  possible by design (operator-controlled override). Not a vulnerability.

## FERPA-specific reporting notes

The pipeline has FOUR explicit FERPA gates:

1. The deid scrub itself (`grader_deidentify_*`).
2. `grader_name_leak_check.py` — refuses to advance if a roster name
   survived in `submissions_deid/`.
3. `grader_deidentify_comments.py` — drops `author_name` from Canvas
   comment threads (#65).
4. `_challenge_dir_guard.py` — refuses to write inside the toolkit
   clone (#44).

If you find a path that leaks PII past any of these, treat it as
**critical** and email immediately. Include the exact file path + line
range where the leak occurs, and an example payload that triggers it.
If the leak is in deployed downstream consumer repos (m119, ds250,
ds460, etc.), call that out — those may need coordinated remediation.
