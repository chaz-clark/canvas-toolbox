"""Tier 1 unit test — clean_sandbox invariants (the parts that don't hit Canvas).

The live delete flow is I/O and proven end-to-end against the sandbox; here we
lock the two static correctness properties: deletion ORDER (assignments before
assignment_groups, since a group delete cascades to its assignments) and the
files delete endpoint (global /files/:id, not under /courses/).
"""
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import clean_sandbox as C  # noqa: E402


def test_specs_delete_assignments_before_groups():
    labels = [s[0] for s in C._SPECS]
    assert labels.index("assignments") < labels.index("assignment_groups"), \
        "assignments must be deleted before assignment_groups (group delete cascades)"


def test_files_use_global_delete_endpoint():
    files_spec = next(s for s in C._SPECS if s[0] == "files")
    # files are deleted at the global /files/:id, not /courses/:cid/files/:id
    assert files_spec[3] == "files/{id}"
