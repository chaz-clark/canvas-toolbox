"""#402 — grader_grade.py must point faculty at the keyless session path, not just fail."""
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import grader_grade  # noqa: E402


def test_missing_key_message_names_keyless_path(monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit) as exc:
        grader_grade.AnthropicGraderLLM("claude-sonnet-4-6")
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "ANTHROPIC_API_KEY not set" in err
    assert "your own AI subscription" in err


def test_keyless_note_says_where_grading_actually_happens():
    assert "feedback/_grader<n>.csv" in grader_grade._KEYLESS_NOTE
