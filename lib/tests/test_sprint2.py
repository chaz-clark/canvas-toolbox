"""
Sprint 2 regression tests — Safe to Work In
Covers issues: #4, #6
"""
import subprocess
import sys
from pathlib import Path

from conftest import sandbox_env  # noqa: F401  (used as fixture via import)


# ---------------------------------------------------------------------------
# #4 — course_ref/ must survive --pull
# ---------------------------------------------------------------------------

def test_course_ref_survives_pull(sandbox_env):
    """#4: files in course_ref/ must not be deleted by a full --pull."""
    test_file = Path("course_ref/_regression_test.txt")
    test_file.parent.mkdir(exist_ok=True)
    test_file.write_text("regression sentinel")

    try:
        result = subprocess.run(
            [sys.executable, "lib/tools/canvas_sync.py", "--pull", "--quiet"],
            env=sandbox_env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Pull failed:\n{result.stderr}"
        assert test_file.exists(), (
            "REGRESSION #4: course_ref/ file was deleted by --pull"
        )
    finally:
        test_file.unlink(missing_ok=True)


def test_questions_json_survives_pull(sandbox_env):
    """#4: *.questions.json files in course/ must not be deleted by --pull."""
    import json
    test_file = Path("course/_regression_test.questions.json")
    test_file.write_text(json.dumps([{"question_name": "regression test"}]))

    try:
        result = subprocess.run(
            [sys.executable, "lib/tools/canvas_sync.py", "--pull", "--quiet"],
            env=sandbox_env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Pull failed:\n{result.stderr}"
        assert test_file.exists(), (
            "REGRESSION #4: .questions.json file in course/ was deleted by --pull"
        )
    finally:
        test_file.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# #6 — New Quizzes sidecar files must be created on --pull
# ---------------------------------------------------------------------------

def test_new_quiz_sidecar_created(sandbox_pull):
    """#6: NewQuiz entries in the index must have quiz_engine and settings_path."""
    import json
    index = sandbox_pull
    new_quizzes = [
        (fp, meta) for fp, meta in index.get("files", {}).items()
        if meta.get("type") == "NewQuiz"
    ]
    assert new_quizzes, "No NewQuiz items found in sandbox — cannot run #6 test"

    for fp, meta in new_quizzes:
        assert meta.get("quiz_engine") == "new_quiz", (
            f"REGRESSION #6: quiz_engine missing from index entry for {fp}"
        )
        settings_path = meta.get("settings_path")
        assert settings_path, (
            f"REGRESSION #6: settings_path missing from index entry for {fp}"
        )
        assert Path(settings_path).exists(), (
            f"REGRESSION #6: sidecar file missing on disk: {settings_path}"
        )
        sidecar = json.loads(Path(settings_path).read_text())
        assert sidecar.get("quiz_engine") == "new_quiz", (
            f"REGRESSION #6: quiz_engine missing inside sidecar {settings_path}"
        )
        assert "settings" in sidecar, (
            f"REGRESSION #6: settings missing inside sidecar {settings_path}"
        )
        assert "items" in sidecar, (
            f"REGRESSION #6: items missing inside sidecar {settings_path}"
        )


def test_new_quiz_sidecar_survives_pull(sandbox_env):
    """#6: .newquiz.json sidecar files must not be deleted by --pull cleanup."""
    test_file = Path("course/_regression_test.newquiz.json")
    test_file.write_text('{"quiz_engine": "new_quiz", "settings": {}, "items": []}')

    try:
        result = subprocess.run(
            [sys.executable, "lib/tools/canvas_sync.py", "--pull", "--quiet"],
            env=sandbox_env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Pull failed:\n{result.stderr}"
        assert test_file.exists(), (
            "REGRESSION #6: .newquiz.json sidecar was deleted by --pull cleanup"
        )
    finally:
        test_file.unlink(missing_ok=True)
