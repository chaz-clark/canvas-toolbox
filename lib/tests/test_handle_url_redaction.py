"""#396 — GitHub/Gist/Colab URLs carry the author's handle (often a real name,
never a roster entry). Every de-id adapter must drop them and the leak check
must flag any that remain."""
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import grader_deidentify_comments as comments  # noqa: E402
import grader_deidentify_databricks as dbx  # noqa: E402
import grader_deidentify_docx as docx  # noqa: E402
import grader_deidentify_jupyter as jupyter  # noqa: E402
import grader_deidentify_pdf as pdf  # noqa: E402
import grader_deidentify_text as text_mod  # noqa: E402
import grader_deidentify_xlsx as xlsx  # noqa: E402
import grader_name_leak_check as leak  # noqa: E402

URLS = [
    "https://colab.research.google.com/gist/janedoe123/abc123/notebook.ipynb",
    "https://colab.research.google.com/github/janedoe123/proj/blob/main/a.ipynb",
    "https://gist.github.com/janedoe123/abc123",
    "https://github.com/janedoe123/proj/blob/main/a.py",
    "gist.github.com/janedoe123/abc123",
    "https://janedoe123.github.io/portfolio",
]


@pytest.mark.parametrize("url", URLS)
def test_redact_handle_urls_removes_the_handle(url):
    out, n = dbx.redact_handle_urls(f"See {url} for details.")
    assert "janedoe123" not in out
    assert n == 1
    assert out.endswith(" for details.")


def test_trailing_sentence_punctuation_is_kept():
    out, _ = dbx.redact_handle_urls("Notebook: https://gist.github.com/janedoe123/abc123.")
    assert out == "Notebook: [LINK REDACTED]."


def test_markdown_link_parens_are_kept():
    out, _ = dbx.redact_handle_urls("[my notebook](https://github.com/janedoe123/proj)")
    assert out == "[my notebook]([LINK REDACTED])"


def test_unrelated_urls_are_untouched():
    text = "See https://pandas.pydata.org/docs and https://example.com/github"
    assert dbx.redact_handle_urls(text) == (text, 0)


@pytest.mark.parametrize("scrub", [
    lambda t: dbx.scrub(t, []),
    lambda t: jupyter.scrub(t, []),
    lambda t: pdf.scrub(t, []),
    lambda t: text_mod.scrub(t, []),
    lambda t: xlsx.scrub(t, []),
    lambda t: docx.scrub(t, [], []),
    lambda t: comments.scrub_comment(t, []),
], ids=["databricks", "jupyter", "pdf", "text", "xlsx", "docx", "comments"])
def test_every_adapter_redacts_handle_urls(scrub):
    out, n = scrub("Analysis at https://gist.github.com/janedoe123/abc123 done.")
    assert "janedoe123" not in out
    assert n >= 1


def _leak_run(tmp_path, body, monkeypatch, capsys):
    import json
    (tmp_path / "keymap.json").write_text(json.dumps({"map": {"KEY1": "f.docx"}}))
    (tmp_path / "KEY1.md").write_text(body, encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["leak", "--map", str(tmp_path / "keymap.json"),
                                      "--deid-dir", str(tmp_path)])
    rc = leak.main()
    return rc, capsys.readouterr().out


def test_leak_check_flags_a_remaining_handle_url_without_echoing_it(tmp_path, monkeypatch, capsys):
    rc, out = _leak_run(tmp_path, "see https://github.com/janedoe123/proj", monkeypatch, capsys)
    assert rc == 2
    assert "URL(s) remain" in out and "janedoe123" not in out


def test_leak_check_passes_a_clean_file(tmp_path, monkeypatch, capsys):
    rc, _ = _leak_run(tmp_path, "plain prose with no links", monkeypatch, capsys)
    assert rc == 0
