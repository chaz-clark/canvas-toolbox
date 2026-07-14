"""The METADATA_ONLY_TYPES sidecars a pull writes must survive its stale sweep.

ExternalUrl / ExternalTool module items get a <slug>.json written to disk, but
are deliberately NOT added to index["files"] — those types cannot be
content-pushed (canvas_api_lessons_learned L8), and an index entry would make
cmd_push try.

The stale-file sweep then deleted every *.json / *.html under COURSE_DIR that
wasn't in index["files"] (exempting _module.json / .questions.json /
.newquiz.json, but not these). So each pull created and destroyed the sidecars
in a single run, and reported them as "stale file(s) removed" on a mirror that
had just been built from scratch — nothing pre-existed to go stale.

Consequence: the local mirror silently omitted every ExternalUrl/ExternalTool
module item, so anything reading course/ saw an incomplete course.
"""
import importlib.util
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location("canvas_sync", TOOLS / "canvas_sync.py")
canvas_sync = importlib.util.module_from_spec(spec)
sys.modules["canvas_sync"] = canvas_sync
spec.loader.exec_module(canvas_sync)


def test_sidecars_written_this_pull_are_preserved(tmp_path):
    mod = tmp_path / "student-resources"
    mod.mkdir(parents=True)
    sidecar = mod / "university-policies.json"
    sidecar.write_text(json.dumps({"type": "ExternalUrl"}), encoding="utf-8")

    deleted = canvas_sync._cleanup_stale_files(
        tmp_path, tracked_paths=set(), meta_paths={str(sidecar)}
    )

    assert deleted == []
    assert sidecar.exists(), "the sidecar this pull just wrote was deleted in the same run"


def test_genuinely_stale_files_are_still_removed(tmp_path):
    """The sweep must keep working: a file Canvas no longer has is deleted."""
    mod = tmp_path / "week-1"
    mod.mkdir(parents=True)
    stale = mod / "deleted-in-canvas.html"
    stale.write_text("<p>gone</p>", encoding="utf-8")

    deleted = canvas_sync._cleanup_stale_files(tmp_path, tracked_paths=set(), meta_paths=set())

    assert deleted == [str(stale)]
    assert not stale.exists()


def test_a_sidecar_canvas_dropped_is_swept(tmp_path):
    """If Canvas removes the item, this pull stops writing the sidecar — so it
    is absent from meta_paths and correctly swept. Stale-cleanup still works."""
    mod = tmp_path / "student-resources"
    mod.mkdir(parents=True)
    orphan = mod / "removed-from-canvas.json"
    orphan.write_text(json.dumps({"type": "ExternalUrl"}), encoding="utf-8")

    deleted = canvas_sync._cleanup_stale_files(tmp_path, tracked_paths=set(), meta_paths=set())

    assert deleted == [str(orphan)]
    assert not orphan.exists()


def test_existing_exemptions_still_hold(tmp_path):
    mod = tmp_path / "week-1"
    mod.mkdir(parents=True)
    tracked = mod / "quiz.json"
    tracked.write_text("{}", encoding="utf-8")
    exempt = ("_module.json", "quiz.questions.json", "quiz.newquiz.json")
    for name in exempt:
        (mod / name).write_text("{}", encoding="utf-8")

    deleted = canvas_sync._cleanup_stale_files(
        tmp_path, tracked_paths={str(tracked)}, meta_paths=set()
    )

    assert deleted == []
    assert all((mod / n).exists() for n in exempt)
    assert tracked.exists()


def test_sidecars_stay_out_of_index_so_push_never_touches_them():
    """Guard the fix: if a future change adds these to index["files"], cmd_push
    would try to POST an ExternalUrl/ExternalTool item back to Canvas (L8)."""
    assert "ExternalUrl" in canvas_sync.METADATA_ONLY_TYPES
    assert "ExternalTool" in canvas_sync.METADATA_ONLY_TYPES
