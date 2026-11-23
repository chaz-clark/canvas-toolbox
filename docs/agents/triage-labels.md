# Triage Labels

The skills speak in five canonical triage roles. This repo uses the default label strings.

| Label in mattpocock/skills | Label in our tracker | Meaning |
| --- | --- | --- |
| `needs-triage` | `needs-triage` | Maintainer needs to evaluate this issue |
| `needs-info` | `needs-info` | Waiting on the reporter for more information |
| `ready-for-agent` | `ready-for-agent` | Fully specified, ready for an agent in a fresh session |
| `ready-for-human` | `ready-for-human` | Needs a human to implement or decide |
| `wontfix` | `wontfix` | Will not be actioned |

Other labels already on this repo stay as they are: `bug`, `enhancement`, `agent-submitted` (applied by a workflow to issues from the bug-intake worker behind `cb_report_bug.py`), and the version labels `no-bump`, `minor`, `major`.
