#!/usr/bin/env python3
"""Probe New Quizzes quiz and QuestionItem CRUD in the configured sandbox.

This is an intentionally narrow validation fixture, not the production sync
writer. It creates one unpublished, clearly marked New Quiz, creates one
true/false QuestionItem, reads both back, updates both, then deletes the item
and quiz. Cleanup runs after every successful create, including failure paths.

The probe refuses any course other than CANVAS_SANDBOX_ID and requires --apply
--yes for writes. It uses canvas_course_guard before touching Canvas.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

import canvas_course_guard as guard
from __toolbox_version__ import __version__

try:
    from _env_loader import force_utf8_console, load_env
except ImportError:  # pragma: no cover - standalone fallback
    def force_utf8_console() -> None:
        pass

    def load_env():
        load_dotenv()

load_env()

BASE_URL = os.environ.get("CANVAS_BASE_URL", "").strip().rstrip("/")
if BASE_URL and not BASE_URL.startswith(("http://", "https://")):
    BASE_URL = f"https://{BASE_URL}"
TOKEN = os.environ.get("CANVAS_API_TOKEN", "")
SANDBOX_ID = os.environ.get("CANVAS_SANDBOX_ID", "").strip()
TIMEOUT = 30
PREFIX = "FIXTURE: New Quiz API CRUD Probe"


def _headers(content_type: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {TOKEN}"}
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def _url(course_id: str, suffix: str = "") -> str:
    return f"{BASE_URL}/api/quiz/v1/courses/{course_id}/quizzes{suffix}"


def _fail(response: requests.Response, operation: str) -> RuntimeError:
    return RuntimeError(
        f"{operation} failed ({response.status_code}): {response.text[:400]}"
    )


def _json_response(response: requests.Response, operation: str) -> dict | list:
    if response.status_code >= 400:
        raise _fail(response, operation)
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(f"{operation} returned non-JSON response") from exc


def _get_quiz(course_id: str, quiz_id: int) -> dict:
    response = requests.get(
        _url(course_id, f"/{quiz_id}"), headers=_headers(), timeout=TIMEOUT
    )
    if response.status_code == 404:
        raise RuntimeError(f"quiz {quiz_id} was not found")
    result = _json_response(response, "GET quiz")
    if not isinstance(result, dict):
        raise RuntimeError("GET quiz returned a non-object")
    return result


def _get_item(course_id: str, quiz_id: int, item_id: int) -> dict:
    response = requests.get(
        _url(course_id, f"/{quiz_id}/items/{item_id}"),
        headers=_headers(), timeout=TIMEOUT,
    )
    if response.status_code == 404:
        raise RuntimeError(f"item {item_id} was not found")
    result = _json_response(response, "GET item")
    if not isinstance(result, dict):
        raise RuntimeError("GET item returned a non-object")
    return result


def _delete(path: str, operation: str) -> None:
    response = requests.delete(path, headers=_headers(), timeout=TIMEOUT)
    if response.status_code >= 400 and response.status_code != 404:
        raise _fail(response, operation)


def _confirm(title: str) -> bool:
    print("\nPROPOSED SANDBOX CHANGE")
    print(f"  Course: CANVAS_SANDBOX_ID ({SANDBOX_ID})")
    print(f"  Create: unpublished quiz {title!r}")
    print("  Create/update/delete: one fake true/false QuestionItem")
    print("  Cleanup: delete the fixture item and quiz")
    return input("Approve this sandbox CRUD probe? (yes/no): ").strip().lower() in {
        "yes", "y"
    }


def run_probe(course_id: str) -> int:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    title = f"{PREFIX} {timestamp}"
    quiz_id: int | None = None
    item_id: int | None = None

    try:
        quiz_payload = {
            "quiz[title]": title,
            "quiz[points_possible]": "1",
            "quiz[grading_type]": "points",
            "quiz[instructions]": "Automated sandbox CRUD probe; do not publish.",
            "quiz[quiz_settings][calculator_type]": "none",
            "quiz[quiz_settings][has_time_limit]": "false",
        }
        response = requests.post(
            _url(course_id), headers=_headers("application/x-www-form-urlencoded"),
            data=quiz_payload, timeout=TIMEOUT,
        )
        quiz = _json_response(response, "CREATE quiz")
        if not isinstance(quiz, dict) or not quiz.get("id"):
            raise RuntimeError("CREATE quiz returned no quiz id")
        quiz_id = int(quiz["id"])
        print(f"✓ created quiz {quiz_id} (published={quiz.get('published')!r})")
        if quiz.get("published") is True:
            raise RuntimeError("Canvas created the probe quiz published; refusing to continue")

        fetched = _get_quiz(course_id, quiz_id)
        if fetched.get("title") != title:
            raise RuntimeError("quiz read-back title did not match")
        print("✓ quiz read-back matched")

        item_body = {
            "item": {
                "entry_type": "Item",
                "points_possible": 1,
                "position": 1,
                "entry": {
                    "title": "Probe question",
                    "item_body": "<p>Is this a sandbox CRUD probe?</p>",
                    "calculator_type": "none",
                    "interaction_type_slug": "true-false",
                    "interaction_data": {
                        "true_choice": "True",
                        "false_choice": "False",
                    },
                    "scoring_data": {"value": True},
                    "scoring_algorithm": "Equivalence",
                },
            }
        }
        response = requests.post(
            _url(course_id, f"/{quiz_id}/items"), headers=_headers("application/json"),
            json=item_body, timeout=TIMEOUT,
        )
        item = _json_response(response, "CREATE item")
        if not isinstance(item, dict) or not item.get("id"):
            raise RuntimeError("CREATE item returned no item id")
        item_id = int(item["id"])
        print(f"✓ created item {item_id}")

        fetched_item = _get_item(course_id, quiz_id, item_id)
        if fetched_item.get("id") not in {item_id, str(item_id)}:
            raise RuntimeError("item read-back id did not match")
        print("✓ item read-back matched")

        update_quiz = {"quiz[title]": f"{title} — updated"}
        response = requests.patch(
            _url(course_id, f"/{quiz_id}"), headers=_headers("application/x-www-form-urlencoded"),
            data=update_quiz, timeout=TIMEOUT,
        )
        updated = _json_response(response, "UPDATE quiz")
        if not isinstance(updated, dict) or updated.get("title") != f"{title} — updated":
            raise RuntimeError("quiz update did not read back the new title")
        print("✓ quiz update/read-back matched")

        update_item = {"item": {"entry": {"title": "Probe question — updated"}}}
        response = requests.patch(
            _url(course_id, f"/{quiz_id}/items/{item_id}"),
            headers=_headers("application/json"), json=update_item, timeout=TIMEOUT,
        )
        updated_item = _json_response(response, "UPDATE item")
        entry = updated_item.get("entry", {}) if isinstance(updated_item, dict) else {}
        if entry.get("title") != "Probe question — updated":
            raise RuntimeError("item update did not read back the new title")
        print("✓ item update/read-back matched")
        return 0
    except (requests.RequestException, RuntimeError) as exc:
        print(f"✗ probe failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if item_id is not None:
            try:
                _delete(_url(course_id, f"/{quiz_id}/items/{item_id}"), "DELETE item")
                print(f"✓ deleted item {item_id}")
            except (requests.RequestException, RuntimeError) as exc:
                print(f"✗ cleanup item {item_id} failed: {exc}", file=sys.stderr)
        if quiz_id is not None:
            try:
                _delete(_url(course_id, f"/{quiz_id}"), "DELETE quiz")
                print(f"✓ deleted quiz {quiz_id}")
            except (requests.RequestException, RuntimeError) as exc:
                print(f"✗ cleanup quiz {quiz_id} failed: {exc}", file=sys.stderr)


def main() -> int:
    force_utf8_console()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=f"canvas-toolbox {__version__}")
    parser.add_argument("--apply", action="store_true", help="perform the sandbox writes")
    parser.add_argument("--yes", action="store_true", help="confirm the proposed probe")
    args = parser.parse_args()

    if not BASE_URL or not TOKEN or not SANDBOX_ID:
        print("ERROR: CANVAS_BASE_URL, CANVAS_API_TOKEN, and CANVAS_SANDBOX_ID are required")
        return 2
    if not args.apply:
        print("DRY RUN: pass --apply --yes to run the sandbox CRUD probe")
        return 0
    if not args.yes:
        print("ERROR: --apply requires --yes for this automated fixture")
        return 2

    guard.enforce(
        base_url=BASE_URL, headers=_headers(), course_id=SANDBOX_ID,
        mode="write", label="New Quiz CRUD probe target",
    )
    # --yes is the explicit confirmation supplied by the instructor for this run.
    # Keep the preview in output even for non-interactive execution.
    title = f"{PREFIX} <UTC timestamp>"
    print(f"Approved sandbox probe: create/update/delete unpublished {title}")
    return run_probe(SANDBOX_ID)


if __name__ == "__main__":
    raise SystemExit(main())
