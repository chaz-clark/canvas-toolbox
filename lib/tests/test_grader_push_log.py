"""Tier 1 unit tests — grader_push's "already pushed" log check.

Source: lib/tools/grader_push.py
  - keys_pushed_in_log: which keys the per-assignment push log says were graded
  - already_pushed: whether a key is skipped on this run

Since v0.60.0 (a103cd4) a grade push is logged as `grade <before> → <grade>`,
while the check still expected `grade <grade>`, so it never matched and a
re-run relied on Canvas's "already graded" gate alone.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from grader_push import (_PUSH_LOG_COMMENT_RE, already_pushed,  # noqa: E402
                         keys_pushed_in_log)

LOG = """# push log
- K-1: grade — → 8 pushed to assignment 55
- K-2: grade 7 → 9.5 pushed to assignment 55
- K-3: grade A- pushed to assignment 55
- K-4: grade — → 8 pushed to assignment 555
- K-5: comment 123 pushed to assignment 55
- K-6: HELD HOLD_X for assignment 55 (grade 8 withheld)
- K-7: comment-only posted to assignment 55 (grade untouched)
- K-8: grade 6 → 7 updated on assignment 55
- K-9: comment 456 updated on assignment 55
"""


def test_current_log_format_is_recognised():
    assert {"K-1", "K-2"} <= keys_pushed_in_log(LOG, "55")


def test_log_format_before_v0_60_still_recognised():
    assert "K-3" in keys_pushed_in_log(LOG, "55")


def test_log_wording_since_2_12_4_is_recognised():
    """#483: new lines say `updated on assignment`; older logs say `pushed to
    assignment`. Both must be read, or a re-run re-sends what a log already has."""
    assert "K-8" in keys_pushed_in_log(LOG, "55")


def test_retract_reads_comment_ids_in_both_wordings():
    assert _PUSH_LOG_COMMENT_RE.findall(LOG) == [("K-5", "123", "55"), ("K-9", "456", "55")]


def test_only_this_assignment_and_only_grade_lines():
    assert keys_pushed_in_log(LOG, "55") == {"K-1", "K-2", "K-3", "K-8"}
    assert keys_pushed_in_log(LOG, "555") == {"K-4"}
    assert keys_pushed_in_log("", "55") == set()


def _args(**kw):
    return SimpleNamespace(**{"force": False, "comments_only": False, "regrade": False, **kw})


def test_default_push_skips_a_key_already_pushed():
    assert already_pushed("K-1", {"K-1"}, _args()) is True
    assert already_pushed("K-9", {"K-1"}, _args()) is False


def test_force_comments_only_and_regrade_are_not_skipped():
    # --comments-only (grade now, comment later) and --regrade (a resubmission)
    # re-use keys that are already in the log; each has its own guard
    # (supersede, the resubmission gate), so the log must not block them.
    for kw in ("force", "comments_only", "regrade"):
        assert already_pushed("K-1", {"K-1"}, _args(**{kw: True})) is False, kw
