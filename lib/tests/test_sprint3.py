"""
Sprint 3 regression tests — Author Like a Human
Covers issues: #9, #7
"""
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# #9 — Markdown mirror created on --pull
# ---------------------------------------------------------------------------

def test_markdown_files_created(sandbox_pull):
    """#9: pages in the index must have markdown_path pointing to an existing .md file."""
    index = sandbox_pull
    pages = [
        (fp, meta) for fp, meta in index.get("files", {}).items()
        if meta.get("type") == "Page"
    ]
    assert pages, "No Page entries found in sandbox index"

    missing_md_path = []
    missing_on_disk = []
    for fp, meta in pages:
        md_path = meta.get("markdown_path")
        if not md_path:
            missing_md_path.append(fp)
        elif not Path(md_path).exists():
            missing_on_disk.append(md_path)

    assert not missing_md_path, (
        f"REGRESSION #9: {len(missing_md_path)} page(s) missing markdown_path in index: {missing_md_path[:3]}"
    )
    assert not missing_on_disk, (
        f"REGRESSION #9: {len(missing_on_disk)} markdown file(s) missing on disk: {missing_on_disk[:3]}"
    )


def test_markdown_has_frontmatter(sandbox_pull):
    """#9: generated .md files must have YAML frontmatter with title and page_url."""
    index = sandbox_pull
    pages = [
        (fp, meta) for fp, meta in index.get("files", {}).items()
        if meta.get("type") == "Page" and meta.get("markdown_path")
    ]
    for fp, meta in pages[:5]:  # spot-check first five
        md_content = Path(meta["markdown_path"]).read_text(encoding="utf-8")
        assert md_content.startswith("---"), (
            f"REGRESSION #9: markdown file missing frontmatter: {meta['markdown_path']}"
        )
        assert "title:" in md_content, (
            f"REGRESSION #9: markdown frontmatter missing title: {meta['markdown_path']}"
        )
        assert "page_url:" in md_content, (
            f"REGRESSION #9: markdown frontmatter missing page_url: {meta['markdown_path']}"
        )


def test_build_produces_html(sandbox_pull, sandbox_env):
    """#9: --build must convert a .md file to HTML in course/."""

    index = sandbox_pull
    # Find a page with a markdown_path
    page_entry = next(
        (
            (fp, meta) for fp, meta in index.get("files", {}).items()
            if meta.get("type") == "Page" and meta.get("markdown_path")
        ),
        None,
    )
    assert page_entry, "No page with markdown_path found"

    fp, meta = page_entry
    md_path = Path(meta["markdown_path"])
    html_path = Path(fp)

    # Edit the markdown with a sentinel
    original_md = md_path.read_text(encoding="utf-8")
    original_html = html_path.read_text(encoding="utf-8") if html_path.exists() else ""
    sentinel = "<!-- regression-test-sentinel -->"

    try:
        md_path.write_text(original_md + f"\n\n{sentinel}\n", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "tools/canvas_sync.py", "--build"],
            env=sandbox_env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"--build failed:\n{result.stderr}"
        built_html = html_path.read_text(encoding="utf-8")
        assert sentinel in built_html, (
            f"REGRESSION #9: --build did not write sentinel to HTML output at {fp}"
        )
    finally:
        md_path.write_text(original_md, encoding="utf-8")
        if original_html:
            html_path.write_text(original_html, encoding="utf-8")


# ---------------------------------------------------------------------------
# #7 — Canvas file upload stores metadata in index
# ---------------------------------------------------------------------------

def test_upload_stores_metadata_in_index(sandbox_env):
    """#7: --upload must store canvas_file_id, url, folder, and local_source_path in index."""
    import json
    from pathlib import Path

    # Create a small temp file to upload
    tmp = Path("course_ref/_regression_upload_test.txt")
    tmp.parent.mkdir(exist_ok=True)
    tmp.write_text("regression upload test sentinel")

    try:
        result = subprocess.run(
            [sys.executable, "tools/canvas_sync.py", "--upload", str(tmp), "--folder", "course_assets_test"],
            env=sandbox_env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"--upload failed:\n{result.stderr}\n{result.stdout}"

        index_path = Path(".canvas/index.json")
        assert index_path.exists(), "index.json missing after --upload"
        index = json.loads(index_path.read_text())

        uploads = index.get("files_uploaded", {})
        assert uploads, "REGRESSION #7: files_uploaded missing from index after --upload"

        entry = uploads.get(str(tmp))
        assert entry, f"REGRESSION #7: uploaded file not found in index under key '{tmp}'"
        assert entry.get("canvas_file_id"), "REGRESSION #7: canvas_file_id missing from upload entry"
        assert entry.get("url"), "REGRESSION #7: url missing from upload entry"
        assert entry.get("folder") == "course_assets_test", "REGRESSION #7: folder not recorded correctly"
        assert entry.get("local_source_path") == str(tmp), "REGRESSION #7: local_source_path not recorded"
    finally:
        tmp.unlink(missing_ok=True)
