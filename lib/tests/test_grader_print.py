"""grader_print — classify, convert-then-print, dry-run safety, no names in output.

Never prints for real: subprocess and the printer list are mocked. Runs on Mac and
Windows CI.
"""
import sys
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import grader_print as gp  # noqa: E402


@pytest.fixture
def work(tmp_path, monkeypatch):
    d = tmp_path / "subs"
    d.mkdir()
    for n in ("Alice Smith essay.pdf", "Bob Jones report.docx", "carol.py", ".hidden.pdf"):
        (d / n).write_bytes(b"x")
    monkeypatch.setattr(gp, "list_printers", lambda: ["LAB-1", "LAB-2"])
    return d


def test_classify_and_hidden_files_skipped(work):
    pdfs, office, skipped = gp.classify(gp.collect([work]))
    assert [p.suffix for p in pdfs] == [".pdf"] and len(pdfs) == 1
    assert [o.suffix for o in office] == [".docx"]
    assert skipped == {".py": 1}


def test_dry_run_prints_nothing_and_shows_no_file_names(work, monkeypatch, capsys):
    monkeypatch.setattr(gp, "print_pdf", lambda *a: pytest.fail("printed in dry run"))
    monkeypatch.setattr(gp, "convert_to_pdf", lambda *a: pytest.fail("converted in dry run"))
    assert gp.run([work], "LAB-1", apply=False) == 0
    out = capsys.readouterr().out
    assert "Dry run" in out and "Alice" not in out and "Bob" not in out


def test_unknown_printer_is_rejected(work, capsys):
    assert gp.run([work], "NOPE", apply=True) == 1
    assert "not found" in capsys.readouterr().out


def test_apply_converts_office_then_prints_pdfs_and_cleans_temp(work, monkeypatch, capsys):
    printed, tmpdirs = [], []

    def fake_convert(src, outdir):
        tmpdirs.append(outdir)
        out = outdir / (src.stem + ".pdf")
        out.write_bytes(b"pdf")
        return out, "fake"

    monkeypatch.setattr(gp, "convert_to_pdf", fake_convert)
    monkeypatch.setattr(gp, "print_pdf", lambda pdf, pr: printed.append((pdf.suffix, pr)) or (True, "ok"))
    assert gp.run([work], "LAB-1", apply=True) == 0
    assert printed == [(".pdf", "LAB-1"), (".pdf", "LAB-1")]      # 1 native + 1 converted
    assert not tmpdirs[0].exists()                                # temp PDFs removed
    out = capsys.readouterr().out
    assert "Alice" not in out and "Bob" not in out and "2 sent" in out


def test_failed_conversion_is_reported_not_silent(work, monkeypatch, capsys):
    monkeypatch.setattr(gp, "convert_to_pdf", lambda s, o: (None, "no converter found"))
    monkeypatch.setattr(gp, "print_pdf", lambda *a: (True, "ok"))
    assert gp.run([work], "LAB-1", apply=True) == 1
    assert "NOT converted" in capsys.readouterr().out


def test_windows_print_uses_sumatra_when_present(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(gp, "IS_WIN", True)
    monkeypatch.setattr(gp, "_first_existing", lambda n, p: "C:/Sumatra.exe")
    monkeypatch.setattr(gp.subprocess, "run",
                        lambda cmd, **k: calls.append(cmd) or type("R", (), {"returncode": 0, "stderr": ""})())
    ok, _ = gp.print_pdf(tmp_path / "a.pdf", "Lab Printer")
    assert ok and calls[0][:3] == ["C:/Sumatra.exe", "-print-to", "Lab Printer"] and "-silent" in calls[0]


def test_posix_print_uses_lp(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(gp, "IS_WIN", False)
    monkeypatch.setattr(gp.subprocess, "run",
                        lambda cmd, **k: calls.append(cmd) or type("R", (), {"returncode": 0, "stderr": ""})())
    assert gp.print_pdf(tmp_path / "a.pdf", "LAB-1")[0]
    assert calls[0][:3] == ["lp", "-d", "LAB-1"]
