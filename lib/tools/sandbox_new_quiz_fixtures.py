#!/usr/bin/env python3
"""Seed or remove a populated New Quiz fixture in CANVAS_SANDBOX_ID.

The fixture is unpublished, contains no student data, and is intentionally
marked so it can be identified in Canvas. It exercises common QuestionItem
payloads for sync development. Use --teardown with the printed quiz id when
the fixture is no longer needed.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from uuid import uuid4

import requests

from new_quiz_crud_probe import (
    BASE_URL,
    PREFIX,
    SANDBOX_ID,
    TIMEOUT,
    _delete,
    _headers,
    _json_response,
    _url,
)
import canvas_course_guard as guard
from __toolbox_version__ import __version__


def _item(position: int, title: str, entry: dict, points: int = 1) -> dict:
    return {
        "item": {
            "entry_type": "Item",
            "points_possible": points,
            "position": position,
            "entry": entry,
        }
    }


def _fixtures() -> list[dict]:
    choice_ids = [str(uuid4()) for _ in range(3)]
    return [
        _item(1, "True/false fixture", {
            "title": "True/false fixture",
            "item_body": "<p>New Quiz API fixtures can be synchronized.</p>",
            "calculator_type": "none",
            "interaction_type_slug": "true-false",
            "interaction_data": {"true_choice": "True", "false_choice": "False"},
            "scoring_data": {"value": True},
            "scoring_algorithm": "Equivalence",
        }),
        _item(2, "Choice fixture", {
            "title": "Choice fixture",
            "item_body": "<p>Which API namespace serves New Quizzes?</p>",
            "calculator_type": "none",
            "interaction_type_slug": "choice",
            "interaction_data": {"choices": [
                {"id": choice_ids[0], "position": 1, "itemBody": "<p>/api/quiz/v1</p>"},
                {"id": choice_ids[1], "position": 2, "itemBody": "<p>/api/v1 only</p>"},
                {"id": choice_ids[2], "position": 3, "itemBody": "<p>/api/lti/v9</p>"},
            ]},
            "properties": {"shuffle_rules": {"choices": {"to_lock": [], "shuffled": False}}},
            "scoring_data": {"value": choice_ids[0]},
            "scoring_algorithm": "Equivalence",
        }),
        _item(3, "Essay fixture", {
            "title": "Essay fixture",
            "item_body": "<p>Describe one safe use for the New Quiz API.</p>",
            "calculator_type": "none",
            "interaction_type_slug": "essay",
            "interaction_data": {
                "rce": True, "essay": None, "word_count": True,
                "file_upload": False, "spell_check": True,
                "word_limit_max": "250", "word_limit_min": "0",
                "word_limit_enabled": True,
            },
            "properties": {},
            "scoring_data": {"value": "Fixture grading note"},
            "scoring_algorithm": "None",
        }),
        _item(4, "Numeric fixture", {
            "title": "Numeric fixture",
            "item_body": "<p>What is the documented probe point value?</p>",
            "calculator_type": "basic",
            "interaction_type_slug": "numeric",
            "interaction_data": {},
            "properties": {},
            "scoring_data": {"value": [{"id": "1", "type": "exactResponse", "value": "1"}]},
            "scoring_algorithm": "Numeric",
        }),
    ]


def seed() -> int:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    title = f"{PREFIX} matrix {timestamp}"
    quiz_response = requests.post(
        _url(SANDBOX_ID),
        headers={"Authorization": _headers()["Authorization"],
                 "Content-Type": "application/x-www-form-urlencoded"},
        data={
            "quiz[title]": title,
            "quiz[points_possible]": "4",
            "quiz[grading_type]": "points",
            "quiz[instructions]": "Automated unpublished fixture; do not publish.",
            "quiz[quiz_settings][calculator_type]": "none",
            "quiz[quiz_settings][has_time_limit]": "false",
        },
        timeout=TIMEOUT,
    )
    quiz = _json_response(quiz_response, "CREATE fixture quiz")
    quiz_id = int(quiz["id"])
    print(f"✓ created unpublished fixture quiz {quiz_id}: {title}")
    created = []
    try:
        for fixture in _fixtures():
            response = requests.post(
                _url(SANDBOX_ID, f"/{quiz_id}/items"),
                headers=_headers(), json=fixture, timeout=TIMEOUT,
            )
            item = _json_response(response, "CREATE fixture item")
            created.append(item["id"])
            print(f"  ✓ item {item['id']}: {item.get('entry', {}).get('title', '<untitled>')}")
    except Exception:
        for item_id in created:
            _delete(_url(SANDBOX_ID, f"/{quiz_id}/items/{item_id}"), "cleanup fixture item")
        _delete(_url(SANDBOX_ID, f"/{quiz_id}"), "cleanup fixture quiz")
        raise
    print(f"Fixture ready. Preserve quiz id {quiz_id} for sync testing; teardown with --teardown --quiz-id {quiz_id}.")
    return 0


def teardown(quiz_id: int) -> int:
    items_response = requests.get(
        _url(SANDBOX_ID, f"/{quiz_id}/items"), headers=_headers(), timeout=TIMEOUT
    )
    items = _json_response(items_response, "LIST fixture items")
    for item in items if isinstance(items, list) else []:
        _delete(_url(SANDBOX_ID, f"/{quiz_id}/items/{item['id']}"), "DELETE fixture item")
    _delete(_url(SANDBOX_ID, f"/{quiz_id}"), "DELETE fixture quiz")
    print(f"✓ removed fixture quiz {quiz_id}")
    return 0


def publish(quiz_id: int) -> int:
    """Publish the fixture's Canvas assignment shell for Test Student use."""
    response = requests.put(
        f"{BASE_URL}/api/v1/courses/{SANDBOX_ID}/assignments/{quiz_id}",
        headers={"Authorization": _headers()["Authorization"],
                 "Content-Type": "application/x-www-form-urlencoded"},
        data={"assignment[published]": "true"},
        timeout=TIMEOUT,
    )
    result = _json_response(response, "PUBLISH fixture assignment")
    if result.get("published") is not True:
        raise RuntimeError("Canvas did not verify the fixture as published")
    print(f"✓ published fixture quiz {quiz_id} for Test Student validation")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--teardown", action="store_true")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--quiz-id", type=int)
    args = parser.parse_args()
    if not BASE_URL or not SANDBOX_ID:
        print("ERROR: CANVAS_BASE_URL and CANVAS_SANDBOX_ID are required")
        return 2
    if args.teardown and not args.quiz_id:
        print("ERROR: --teardown requires --quiz-id")
        return 2
    if args.publish and not args.quiz_id:
        print("ERROR: --publish requires --quiz-id")
        return 2
    if not args.apply or not args.yes:
        print("DRY RUN: pass --apply --yes to seed or remove the sandbox fixture")
        return 0
    guard.enforce(BASE_URL, _headers(), SANDBOX_ID, mode="write", label="New Quiz fixture target")
    try:
        if args.teardown:
            return teardown(args.quiz_id)
        if args.publish:
            return publish(args.quiz_id)
        return seed()
    except (requests.RequestException, RuntimeError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
