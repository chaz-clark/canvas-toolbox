"""Tier 1 unit tests — grader_scaffold pure-logic helpers.

Source: lib/tools/grader_scaffold.py (#54-A — auto-discovery of task slugs
+ surface types from Canvas assignment names).

  - infer_surface: name → 'ai_log' / 'cohesive_narrative' / 'self_review' /
    'generic' via the _SURFACE_PATTERNS regex table.
  - infer_task_slug: name → short slug. 'Project X Task Y' → pXtY,
    'KC<n>' → kc<n>, otherwise slugified + capped at 16 chars.
"""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from grader_scaffold import infer_surface, infer_task_slug  # noqa: E402


# ---------------------------------------------------------------------------
# infer_surface
# ---------------------------------------------------------------------------

def test_infer_surface_ai_log():
    assert infer_surface("Project 1 Task 1 — AI Log") == "ai_log"


def test_infer_surface_cohesive_narrative():
    assert infer_surface("P1 T1 Cohesive Narrative") == "cohesive_narrative"


def test_infer_surface_cohesive_alone():
    """Bare 'cohesive' (without 'narrative') still matches."""
    assert infer_surface("Project Cohesive Writeup") == "cohesive_narrative"


def test_infer_surface_self_review_variants():
    assert infer_surface("Mid Letter") == "self_review"
    assert infer_surface("Mid Review") == "self_review"
    assert infer_surface("Self Review") == "self_review"
    assert infer_surface("self-review") == "self_review"


def test_infer_surface_generic_default():
    assert infer_surface("KC1 — Pyspark Take-Home") == "generic"
    assert infer_surface("") == "generic"


def test_infer_surface_case_insensitive():
    assert infer_surface("AI LOG") == "ai_log"
    assert infer_surface("ai log") == "ai_log"


# ---------------------------------------------------------------------------
# infer_task_slug
# ---------------------------------------------------------------------------

def test_task_slug_project_task_pattern():
    assert infer_task_slug("Project 1 Task 2 — AI Log") == "p1t2"


def test_task_slug_project_task_with_hyphen():
    assert infer_task_slug("Project 2-Task 3 Cohesive") == "p2t3"


def test_task_slug_kc_pattern():
    assert infer_task_slug("KC1 — PySpark Take-Home") == "kc1"


def test_task_slug_kc_two_digits():
    assert infer_task_slug("KC10 Mid Review") == "kc10"


def test_task_slug_fallback_slugify():
    """No P-T or KC pattern → slugify + cap at 16 chars."""
    slug = infer_task_slug("Final Lab Report")
    assert slug == "final_lab_report"


def test_task_slug_caps_at_16_chars():
    slug = infer_task_slug("A Very Long Assignment Name With Many Words")
    assert len(slug) <= 16


def test_task_slug_strips_surface_keywords_from_fallback():
    """When falling through to slugify, surface keywords (ai log, etc.)
    are stripped before slugification — keeps the task-side semantics."""
    slug = infer_task_slug("Final Project AI Log")
    # 'ai log' should be removed via _SURFACE_PATTERNS strip
    assert "ai" not in slug
    assert "log" not in slug


def test_task_slug_empty_input_defaults_to_task():
    assert infer_task_slug("") == "task"
    assert infer_task_slug(None) == "task"  # type: ignore[arg-type]
