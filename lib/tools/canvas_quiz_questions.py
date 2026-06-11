"""
canvas_quiz_questions.py

Create, replace, or list questions for a classic Canvas quiz from a local JSON file.

Each quiz is defined as a JSON file (e.g. course/.../my-quiz.questions.json).
The tool reads that file and pushes questions to the matching Canvas quiz.

Usage:
    uv run python tools/canvas_quiz_questions.py --push <questions-file.json>
    uv run python tools/canvas_quiz_questions.py --list  <questions-file.json>
    uv run python tools/canvas_quiz_questions.py --clear <questions-file.json>

    --push   Delete all existing questions, then create from file (idempotent)
    --list   Show current questions in Canvas for this quiz (no changes)
    --clear  Delete all existing questions (no create)

Question file format (.questions.json):
    {
      "canvas_quiz_id": 5911959,
      "course_id": "415322",          // optional — overrides CANVAS_COURSE_ID
      "questions": [
        {
          "question_name": "Short label shown in gradebook",
          "question_text": "Full question text shown to student.",
          "question_type": "multiple_choice_question",
          "points_possible": 1,
          "answers": [
            {"answer_text": "Correct answer", "answer_weight": 100},
            {"answer_text": "Wrong answer A",  "answer_weight": 0},
            {"answer_text": "Wrong answer B",  "answer_weight": 0},
            {"answer_text": "Wrong answer C",  "answer_weight": 0}
          ]
        },
        ...
      ]
    }

Supported question_type values:
    multiple_choice_question   — one correct answer (answer_weight 100 = correct)
    true_false_question        — answers: [{"answer_text":"True",...},{"answer_text":"False",...}]
    short_answer_question      — fill-in-the-blank, answers are accepted values (weight 100 each)
    multiple_answers_question  — "select all that apply", multiple answers with weight 100
    essay_question             — open response, no answers needed

Notes:
    - --push always clears existing questions first (fully idempotent)
    - Classic quizzes only. NewQuiz (external_tool) questions cannot be managed via REST API.
    - After pushing questions, Canvas recalculates points_possible on the quiz automatically.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import requests

try:
    from _env_loader import load_env
    load_env()
except ImportError:
    pass

CANVAS_API_TOKEN = os.environ.get("CANVAS_API_TOKEN", "")
_raw = os.environ.get("CANVAS_BASE_URL", "").strip().rstrip("/")
CANVAS_BASE_URL = ("https://" + _raw) if _raw and not _raw.startswith("http") else _raw
DEFAULT_COURSE_ID = os.environ.get("CANVAS_COURSE_ID", "")


def _h():
    return {"Authorization": f"Bearer {CANVAS_API_TOKEN}", "Content-Type": "application/json"}


def _check_env():
    if not CANVAS_API_TOKEN or not CANVAS_BASE_URL:
        print("ERROR: CANVAS_API_TOKEN and CANVAS_BASE_URL required in .env")
        sys.exit(1)


def _load_file(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        print(f"ERROR: File not found: {path}")
        sys.exit(1)
    return json.loads(p.read_text(encoding="utf-8"))


def _get_questions(course_id: str, quiz_id: int) -> list:
    url = f"{CANVAS_BASE_URL}/api/v1/courses/{course_id}/quizzes/{quiz_id}/questions"
    results = []
    while url:
        r = requests.get(url, headers=_h(), params={"per_page": 50}, timeout=20)
        if r.status_code >= 400:
            print(f"ERROR fetching questions: {r.status_code} {r.text[:150]}")
            return []
        results.extend(r.json())
        url = None
        for part in r.headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
    return results


def _delete_question(course_id: str, quiz_id: int, question_id: int) -> bool:
    r = requests.delete(
        f"{CANVAS_BASE_URL}/api/v1/courses/{course_id}/quizzes/{quiz_id}/questions/{question_id}",
        headers=_h(), timeout=20
    )
    return r.status_code in (200, 204)


def _create_question(course_id: str, quiz_id: int, q: dict) -> dict:
    payload = {
        "question": {
            "question_name":  q.get("question_name", "Question"),
            "question_text":  q.get("question_text", ""),
            "question_type":  q.get("question_type", "multiple_choice_question"),
            "points_possible": q.get("points_possible", 1),
        }
    }
    # Include answers for question types that use them
    if "answers" in q and q["question_type"] != "essay_question":
        payload["question"]["answers"] = [
            {
                "answer_text":   a.get("answer_text", ""),
                "answer_weight": a.get("answer_weight", 0),
                "answer_comments": a.get("answer_comments", ""),
            }
            for a in q["answers"]
        ]
    if q.get("correct_comments"):
        payload["question"]["correct_comments"] = q["correct_comments"]
    if q.get("incorrect_comments"):
        payload["question"]["incorrect_comments"] = q["incorrect_comments"]
    if q.get("neutral_comments"):
        payload["question"]["neutral_comments"] = q["neutral_comments"]

    r = requests.post(
        f"{CANVAS_BASE_URL}/api/v1/courses/{course_id}/quizzes/{quiz_id}/questions",
        headers=_h(), json=payload, timeout=20
    )
    if r.status_code >= 400:
        return {"error": r.text[:300]}
    return r.json()


def cmd_list(file_path: str):
    _check_env()
    data = _load_file(file_path)
    quiz_id = data.get("canvas_quiz_id")
    course_id = str(data.get("course_id") or DEFAULT_COURSE_ID)
    if not quiz_id or not course_id:
        print("ERROR: canvas_quiz_id and course_id required in question file.")
        sys.exit(1)

    questions = _get_questions(course_id, quiz_id)
    print(f"Quiz {quiz_id} in course {course_id}: {len(questions)} question(s)\n")
    for i, q in enumerate(questions, 1):
        print(f"  {i}. [{q['id']}] {q.get('question_name')} ({q.get('question_type')}, {q.get('points_possible')}pt)")
        print(f"     {q.get('question_text', '')[:100]}")
        for a in q.get("answers", []):
            correct = "✓" if a.get("weight", 0) == 100 else " "
            print(f"     {correct} {a.get('text', a.get('answer_text', ''))}")
        print()


def cmd_clear(file_path: str):
    _check_env()
    data = _load_file(file_path)
    quiz_id = data.get("canvas_quiz_id")
    course_id = str(data.get("course_id") or DEFAULT_COURSE_ID)
    if not quiz_id or not course_id:
        print("ERROR: canvas_quiz_id and course_id required in question file.")
        sys.exit(1)

    existing = _get_questions(course_id, quiz_id)
    if not existing:
        print(f"Quiz {quiz_id}: no existing questions to clear.")
        return
    print(f"Clearing {len(existing)} existing question(s) from quiz {quiz_id}...")
    for q in existing:
        ok = _delete_question(course_id, quiz_id, q["id"])
        print(f"  {'OK' if ok else 'FAILED'} delete question {q['id']}: {q.get('question_name')}")
    print("Done.")


def cmd_push(file_path: str):
    _check_env()
    data = _load_file(file_path)
    quiz_id = data.get("canvas_quiz_id")
    course_id = str(data.get("course_id") or DEFAULT_COURSE_ID)
    questions = data.get("questions", [])

    if not quiz_id or not course_id:
        print("ERROR: canvas_quiz_id and course_id required in question file.")
        sys.exit(1)
    if not questions:
        print("ERROR: No questions found in file.")
        sys.exit(1)

    print(f"Pushing {len(questions)} question(s) to quiz {quiz_id} in course {course_id}...\n")

    # Clear existing questions first (idempotent)
    existing = _get_questions(course_id, quiz_id)
    if existing:
        print(f"  Clearing {len(existing)} existing question(s)...")
        for q in existing:
            _delete_question(course_id, quiz_id, q["id"])
        print(f"  Cleared.\n")

    # Create questions in order
    created = 0
    for i, q in enumerate(questions, 1):
        result = _create_question(course_id, quiz_id, q)
        if result.get("error"):
            print(f"  [{i}] FAILED: {q.get('question_name')} — {result['error'][:100]}")
        else:
            pts = q.get("points_possible", 1)
            print(f"  [{i}] OK  {q.get('question_name')} ({q.get('question_type')}, {pts}pt)")
            created += 1

    print(f"\n{created}/{len(questions)} questions created.")
    if created == len(questions):
        print(f"Quiz {quiz_id} is ready. Canvas will recalculate total points automatically.")


def main():
    parser = argparse.ArgumentParser(
        description="Manage classic Canvas quiz questions from a local JSON file"
    )
    parser.add_argument("--push",  metavar="FILE", help="Clear existing + create from file (idempotent)")
    parser.add_argument("--list",  metavar="FILE", help="List current questions in Canvas")
    parser.add_argument("--clear", metavar="FILE", help="Delete all existing questions")
    args = parser.parse_args()

    if args.push:
        cmd_push(args.push)
    elif args.list:
        cmd_list(args.list)
    elif args.clear:
        cmd_clear(args.clear)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
