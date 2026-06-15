# Code of Conduct

This project adopts the **[Contributor Covenant, version 2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/)** as its code of conduct.

The full text is the canonical reference; we adopt it by reference rather than copying it inline. Read it at the link above before participating in this project's issues, pull requests, discussions, or any other community space.

## Scope

The Contributor Covenant applies within all project spaces — the GitHub repository, issue threads, pull request reviews, the bug-intake worker's filed reports, and any external venue where someone is representing the project.

It also applies to **faculty operators** filing reports via `cb_report_bug.py`, and to **agents** acting on behalf of an operator. The expectation is the same regardless of channel.

## Reporting

Use GitHub's **Private Vulnerability Reporting** as the private intake channel for conduct issues too. It keeps the report confidential to the maintainer + you, end-to-end through GitHub's UI:

1. Go to https://github.com/chaz-clark/canvas-toolbox/security/advisories
2. Click **Report a vulnerability**.
3. **Prefix the title with `[CONDUCT]`** so the maintainer triages it to the conduct queue rather than the security queue.
4. Describe the incident in the body.

You'll need a (free) GitHub account to file — the same one-time setup as anyone contributing via PR. In exchange you get an authenticated channel with a confidential review track inside GitHub's UI, no email address exposed to scrapers.

You can expect:
- An acknowledgment within ~48 hours.
- A confidential review (the report is not shared publicly without the reporter's consent).
- A response describing what (if anything) happened next.

If the incident is also a security issue — e.g., a contributor's behavior involved deliberately leaking student PII — drop the `[CONDUCT]` prefix and follow [`SECURITY.md`](SECURITY.md) instead, which has a faster triage SLA.

## Enforcement

The maintainer follows the Contributor Covenant's enforcement guidelines (correction → warning → temporary ban → permanent ban) at their discretion. Decisions can be appealed by replying to the original notice within 30 days.

## Why this matters here specifically

This toolkit touches student data through FERPA-protected channels. Behavior in the project's collaboration spaces affects how seriously people take the FERPA discipline in the code. A project that tolerates harassment in its issue tracker is not a project anyone should trust with student names — adopting a Code of Conduct is part of the same discipline as scrubbing student names in `submissions_deid/`.
