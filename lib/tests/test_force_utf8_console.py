"""force_utf8_console must re-encode stdout/stderr IN PLACE.

Replacing sys.stdout with a new TextIOWrapper around the same buffer leaves two
wrappers sharing one buffer; when the old one is collected it closes the buffer.
On Windows that broke pytest's capture for every test calling a tool's main()
("ValueError: I/O operation on closed file").
"""
import io
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from _env_loader import force_utf8_console  # noqa: E402


def _cp1252_stream():
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252")


def test_reencodes_in_place_without_replacing_stream(monkeypatch):
    out, err = _cp1252_stream(), _cp1252_stream()
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    force_utf8_console()
    assert sys.stdout is out and sys.stderr is err
    assert out.encoding == "utf-8" and err.encoding == "utf-8"
    print("✓ — ρ", file=out)  # would raise UnicodeEncodeError under cp1252
    assert not out.closed


def test_noop_off_windows(monkeypatch):
    out = _cp1252_stream()
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(sys, "stdout", out)
    force_utf8_console()
    assert sys.stdout is out and out.encoding == "cp1252"


def test_none_streams_are_tolerated(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    force_utf8_console()  # must not raise
