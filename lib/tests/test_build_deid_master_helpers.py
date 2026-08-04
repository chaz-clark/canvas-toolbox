"""Tier 1 unit tests — build_deid_master pure-logic helpers.

Source: lib/tools/build_deid_master.py
  - deid_code_for       (sha256-based stable hash)
  - is_withdrawn        (enrollment-state classification)
  - student_to_row      (full record builder)
  - detect_collisions   (defense against rare hash collisions)
  - render_csv_rows     (deterministic CSV output)

No Canvas API calls. No filesystem writes. Pure functions in/out.
"""
import csv
import io
import json
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from build_deid_master import (  # noqa: E402
    StudentRow,
    deid_code_for,
    dedupe_users,
    detect_collisions,
    is_withdrawn,
    render_csv_rows,
    render_known_names_lines,
    student_to_row,
    load_roster_json,
)


# ---------------------------------------------------------------------------
# dedupe_users — one row per student even when Canvas returns a multi-section
# student more than once (the .deid_master duplicate-user_id bug)
# ---------------------------------------------------------------------------

def test_dedupe_users_collapses_multi_section_student():
    """A student in two sections is returned twice by /users → must become ONE
    entry, else .deid_master.csv gets duplicate user_id rows."""
    users = [
        {"id": 1, "sortable_name": "A, A", "enrollments": [{"enrollment_state": "active"}]},
        {"id": 1, "sortable_name": "A, A", "enrollments": [{"enrollment_state": "active"}]},
        {"id": 2, "sortable_name": "B, B", "enrollments": [{"enrollment_state": "active"}]},
    ]
    unique, collapsed = dedupe_users(users)
    assert collapsed == 1
    assert sorted(int(u["id"]) for u in unique) == [1, 2]


def test_dedupe_users_merges_enrollments_so_active_wins():
    """Merged enrollments must let is_withdrawn see BOTH states — active in one
    section overrides inactive in another (student is NOT withdrawn)."""
    users = [
        {"id": 5, "sortable_name": "C, C", "enrollments": [{"enrollment_state": "inactive"}]},
        {"id": 5, "sortable_name": "C, C", "enrollments": [{"enrollment_state": "active"}]},
    ]
    unique, _ = dedupe_users(users)
    assert len(unique) == 1
    row = student_to_row(unique[0], "S-", 6)
    assert row.withdrawn == 0  # active section wins → not withdrawn


def test_dedupe_users_no_duplicates_is_a_noop():
    users = [{"id": 1, "enrollments": []}, {"id": 2, "enrollments": []}]
    unique, collapsed = dedupe_users(users)
    assert collapsed == 0 and len(unique) == 2


def test_dedupe_users_skips_record_with_bad_id():
    users = [{"id": 1, "enrollments": []}, {"sortable_name": "no id"}, {"id": "x"}]
    unique, _ = dedupe_users(users)
    assert [int(u["id"]) for u in unique] == [1]


# ---------------------------------------------------------------------------
# deid_code_for — the stable hash
# ---------------------------------------------------------------------------

def test_deid_code_deterministic():
    """Same user_id → same code, every run."""
    assert deid_code_for(173819) == deid_code_for(173819)


def test_deid_code_different_users_different_codes():
    """Different user_ids → different codes (almost always)."""
    assert deid_code_for(173819) != deid_code_for(18065)


def test_deid_code_default_format():
    """Default: S- prefix, 6 hex chars uppercase."""
    code = deid_code_for(173819)
    assert code.startswith("S-")
    body = code[2:]
    assert len(body) == 6
    assert body.isalnum()
    assert body.upper() == body


def test_deid_code_custom_prefix():
    code = deid_code_for(173819, prefix="DS-")
    assert code.startswith("DS-")
    assert len(code) == 3 + 6  # "DS-" + 6 hex


def test_deid_code_custom_hash_bits():
    """--hash-bits 8 should give an 8-char code body."""
    code = deid_code_for(173819, hash_bits=8)
    assert code.startswith("S-")
    assert len(code[2:]) == 8


def test_deid_code_int_or_str_user_id():
    """int and str user_ids should hash identically — defends against
    Canvas API returning user_id as int while operator passes a string."""
    assert deid_code_for(173819) == deid_code_for(int("173819"))


# ---------------------------------------------------------------------------
# is_withdrawn — enrollment-state classification
# ---------------------------------------------------------------------------

def test_withdrawn_no_enrollments_returns_zero():
    """A user with no enrollments isn't withdrawn (defensive default)."""
    assert is_withdrawn([]) == 0
    assert is_withdrawn(None) == 0


def test_withdrawn_active_only():
    assert is_withdrawn([{"enrollment_state": "active"}]) == 0


def test_withdrawn_invited_only():
    """Invited students haven't withdrawn yet — they're pending acceptance."""
    assert is_withdrawn([{"enrollment_state": "invited"}]) == 0


def test_withdrawn_inactive():
    assert is_withdrawn([{"enrollment_state": "inactive"}]) == 1


def test_withdrawn_completed():
    assert is_withdrawn([{"enrollment_state": "completed"}]) == 1


def test_withdrawn_deleted():
    assert is_withdrawn([{"enrollment_state": "deleted"}]) == 1


def test_withdrawn_active_wins_over_dropped():
    """A student with BOTH an active and an inactive enrollment is NOT
    withdrawn — the active record wins."""
    enrollments = [
        {"enrollment_state": "active"},
        {"enrollment_state": "inactive"},
    ]
    assert is_withdrawn(enrollments) == 0


def test_withdrawn_unknown_state_falls_back_to_zero():
    """An unknown state (future Canvas API addition?) isn't auto-classified
    as withdrawn. Safer default."""
    assert is_withdrawn([{"enrollment_state": "creator"}]) == 0


# ---------------------------------------------------------------------------
# student_to_row — full record builder
# ---------------------------------------------------------------------------

def test_student_to_row_basic():
    user = {
        "id": 173819,
        "sortable_name": "Ahlstrom, Sydney",
        "enrollments": [{"enrollment_state": "active"}],
    }
    row = student_to_row(user, prefix="S-", hash_bits=6)
    assert isinstance(row, StudentRow)
    assert row.user_id == 173819
    assert row.sortable_name == "Ahlstrom, Sydney"
    assert row.withdrawn == 0
    assert row.deid_code == deid_code_for(173819, "S-", 6)


def test_student_to_row_missing_sortable_name_falls_back_to_name():
    """Some Canvas users return `name` but not `sortable_name`
    (rare but happens for Test Student / API service users)."""
    user = {
        "id": 999,
        "name": "Service Account",
        "enrollments": [{"enrollment_state": "active"}],
    }
    row = student_to_row(user, "S-", 6)
    assert row.sortable_name == "Service Account"


def test_student_to_row_missing_both_names():
    """Defensive: missing both name and sortable_name → empty string,
    not a crash."""
    user = {"id": 999, "enrollments": [{"enrollment_state": "active"}]}
    row = student_to_row(user, "S-", 6)
    assert row.sortable_name == ""


def test_student_to_row_withdrawn_student():
    user = {
        "id": 18065,
        "sortable_name": "Alfaia Monteiro, Ronaldo",
        "enrollments": [{"enrollment_state": "inactive"}],
    }
    row = student_to_row(user, "S-", 6)
    assert row.withdrawn == 1


# ---------------------------------------------------------------------------
# detect_collisions — defends against rare sha256-prefix duplication
# ---------------------------------------------------------------------------

def test_no_collisions_returns_empty_list():
    rows = [
        StudentRow("S-AAAAAA", 1, "A", 0),
        StudentRow("S-BBBBBB", 2, "B", 0),
        StudentRow("S-CCCCCC", 3, "C", 0),
    ]
    assert detect_collisions(rows) == []


def test_collision_detected():
    rows = [
        StudentRow("S-AAAAAA", 1, "A", 0),
        StudentRow("S-AAAAAA", 2, "B", 0),  # collision
        StudentRow("S-CCCCCC", 3, "C", 0),
    ]
    result = detect_collisions(rows)
    assert len(result) == 1
    code, uids = result[0]
    assert code == "S-AAAAAA"
    assert sorted(uids) == [1, 2]


def test_multiple_collisions_all_reported():
    rows = [
        StudentRow("S-AAAAAA", 1, "A", 0),
        StudentRow("S-AAAAAA", 2, "B", 0),
        StudentRow("S-BBBBBB", 3, "C", 0),
        StudentRow("S-BBBBBB", 4, "D", 0),
    ]
    result = detect_collisions(rows)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# render_csv_rows — deterministic CSV output
# ---------------------------------------------------------------------------

def test_render_csv_rows_header_first():
    """The first row must be the header. `org_id` appended LAST (1.17.0, #279) so
    the addition is positionally additive for anything reading by index."""
    rows = [StudentRow("S-AAAAAA", 1, "Alpha, A", 0)]
    out = render_csv_rows(rows)
    assert out[0] == ["deid_code", "user_id", "sortable_name", "withdrawn", "org_id"]
    assert out[0][:4] == ["deid_code", "user_id", "sortable_name", "withdrawn"]
    assert out[1][4] == ""          # absent org_id serializes empty, never "None"


def test_render_csv_rows_sorted_by_name():
    """Rows are sorted by sortable_name (case-insensitive) for
    deterministic output across runs."""
    rows = [
        StudentRow("S-AAA", 1, "Zoe", 0),
        StudentRow("S-BBB", 2, "Alice", 0),
        StudentRow("S-CCC", 3, "Mark", 0),
    ]
    out = render_csv_rows(rows)
    names = [r[2] for r in out[1:]]
    assert names == ["Alice", "Mark", "Zoe"]


def test_render_csv_rows_withdrawn_serialized_as_int_string():
    """Withdrawn should be '0' or '1', not 'True' or 'False'."""
    rows = [
        StudentRow("S-AAA", 1, "A", 0),
        StudentRow("S-BBB", 2, "B", 1),
    ]
    out = render_csv_rows(rows)
    assert out[1][3] in ("0", "1")
    assert out[2][3] in ("0", "1")
    assert {out[1][3], out[2][3]} == {"0", "1"}


def test_render_csv_rows_deterministic():
    """Two runs over the same input produce identical output."""
    rows = [
        StudentRow("S-AAA", 1, "A", 0),
        StudentRow("S-BBB", 2, "B", 1),
    ]
    assert render_csv_rows(rows) == render_csv_rows(rows)


# ---------------------------------------------------------------------------
# render_known_names_lines — Path A: auto-derive .known_names.txt
# ---------------------------------------------------------------------------

def test_known_names_emits_both_forms():
    """Each student contributes BOTH sortable AND display forms — the
    scrub matches whichever shape appears in document text."""
    rows = [StudentRow("S-AAA", 1, "Ahlstrom, Sydney", 0)]
    lines = render_known_names_lines(rows)
    assert "Ahlstrom, Sydney" in lines
    assert "Sydney Ahlstrom" in lines


def test_known_names_includes_header_comments():
    """File leads with explanatory comments so a future reader knows
    not to hand-edit + that it's auto-derived."""
    rows = [StudentRow("S-AAA", 1, "Ahlstrom, Sydney", 0)]
    lines = render_known_names_lines(rows)
    assert lines[0].startswith("#")
    assert any("Auto-derived" in ln for ln in lines[:3])
    assert any("Do NOT hand-edit" in ln for ln in lines[:3])


def test_known_names_dedups_case_insensitively():
    """If two students have the same name, emit it once. Matches the
    case-insensitive dedup in grader_fetch's update_known_names."""
    rows = [
        StudentRow("S-AAA", 1, "Smith, John", 0),
        StudentRow("S-BBB", 2, "smith, john", 0),  # same name, different case
    ]
    lines = render_known_names_lines(rows)
    body = [ln for ln in lines if not ln.startswith("#")]
    # 2 forms × 1 unique name = 2 entries, not 4
    assert len(body) == 2


def test_known_names_skips_empty_sortable_name():
    """A student without a sortable_name (e.g. service account) is
    silently skipped, not crashed on."""
    rows = [
        StudentRow("S-AAA", 1, "", 0),
        StudentRow("S-BBB", 2, "Real, Student", 0),
    ]
    lines = render_known_names_lines(rows)
    body = [ln for ln in lines if not ln.startswith("#")]
    assert "Real, Student" in body
    assert "Student Real" in body
    assert "" not in body


def test_known_names_handles_single_word_name():
    """A name without a comma (e.g. 'Cher', 'Madonna', or single-word
    service-account name) emits as-is, no display-form duplicate."""
    rows = [StudentRow("S-AAA", 1, "Madonna", 0)]
    lines = render_known_names_lines(rows)
    body = [ln for ln in lines if not ln.startswith("#")]
    assert body == ["Madonna"]


def test_known_names_deterministic():
    """Same input → identical output (sha256-stable when scrub-validates)."""
    rows = [
        StudentRow("S-AAA", 1, "Ahlstrom, Sydney", 0),
        StudentRow("S-BBB", 2, "Smith, John", 0),
    ]
    assert render_known_names_lines(rows) == render_known_names_lines(rows)


def test_known_names_sorted_by_sortable_name():
    """Output sorted by sortable_name (case-insensitive) for stable diffs."""
    rows = [
        StudentRow("S-CCC", 3, "Zeta, Z", 0),
        StudentRow("S-AAA", 1, "Alpha, A", 0),
        StudentRow("S-BBB", 2, "beta, B", 0),
    ]
    lines = render_known_names_lines(rows)
    body = [ln for ln in lines if not ln.startswith("#")]
    # First non-comment line should be Alpha (sortable, since
    # sorted by sortable_name → 'alpha, a' < 'beta, b' < 'zeta, z')
    assert body[0] == "Alpha, A"


# ---------------------------------------------------------------------------
# roster.json — the non-Canvas identifier-map contract (#279)
# ---------------------------------------------------------------------------

def _roster(tmp_path, payload):
    p = tmp_path / "roster.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_roster_json_round_trips_into_the_same_rows_canvas_would_produce(tmp_path):
    """The contract IS the Canvas /users shape, so a non-Canvas consumer reuses the
    whole downstream pipeline (de-id codes, master, known_names, re-id, push)."""
    users = load_roster_json(_roster(tmp_path, [
        {"id": 1395396, "name": "Farmer, Andrew", "org_id": "0123456"},
        {"id": 1395397, "name": "Rembert, Cristen", "withdrawn": True},
    ]))
    rows = [student_to_row(u, "S-", 6) for u in users]
    assert rows[0].user_id == 1395396
    assert rows[0].org_id == "0123456"
    assert rows[0].withdrawn == 0
    assert rows[1].withdrawn == 1                     # explicit flag, no enrollments
    # identical code to what Canvas would produce for the same id — the join holds
    assert rows[0].deid_code == deid_code_for(1395396, "S-", 6)


def test_org_id_is_stored_but_never_becomes_the_key(tmp_path):
    """The reporting consumer measured ZERO overlap between internal ids and
    OrgDefinedId across a 25-student section. Keying on the wrong one silently
    misattributes grades, so org_id must not influence the code or the join."""
    users = load_roster_json(_roster(tmp_path, [
        {"id": 111, "name": "A", "org_id": "999999"},
        {"id": 222, "name": "B", "org_id": "888888"},
    ]))
    rows = [student_to_row(u, "S-", 6) for u in users]
    assert [r.deid_code for r in rows] == [deid_code_for(111), deid_code_for(222)]
    assert [r.org_id for r in rows] == ["999999", "888888"]     # carried, not keyed


def test_canvas_sis_user_id_populates_org_id_too():
    """Same column, both worlds — Canvas calls the institution id sis_user_id."""
    row = student_to_row({"id": 5, "name": "X", "sis_user_id": "00123"}, "S-", 6)
    assert row.org_id == "00123"


def test_roster_json_rejects_a_duplicate_id(tmp_path):
    """Canvas duplicates are an API artifact that dedupe_users merges; a duplicate
    in a HAND-BUILT map is a mistake in the map, and the master is one row per
    student. Collapsing it silently would hide the error that matters most."""
    path = _roster(tmp_path, [{"id": 7, "name": "A"}, {"id": 7, "name": "B"}])
    with pytest.raises(ValueError, match="duplicate id 7"):
        load_roster_json(path)


@pytest.mark.parametrize("payload,expected", [
    ({"id": 1}, "expected a JSON array"),
    ([{"name": "no id"}], "missing required field 'id'"),
    ([{"id": 1}], "missing required field 'name'"),
    ([{"id": "not-a-number", "name": "A"}], "'id' must be an integer"),
    (["just a string"], "expected an object"),
])
def test_roster_json_validation_is_loud(tmp_path, payload, expected):
    """A hand-built identifier map is exactly where a silent error becomes a
    misattributed grade."""
    with pytest.raises(ValueError, match=expected):
        load_roster_json(_roster(tmp_path, payload))


def test_roster_json_reports_bad_json_and_missing_file(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        load_roster_json(bad)
    with pytest.raises(ValueError, match="cannot read"):
        load_roster_json(tmp_path / "nope.json")


def test_older_master_without_org_id_still_parses():
    """The column is additive: readers use csv.DictReader, so a master written
    before 1.17.0 keeps working rather than needing a rebuild."""
    old = "deid_code,user_id,sortable_name,withdrawn\nS-AAA,1,\"Alpha, A\",0\n"
    row = next(csv.DictReader(io.StringIO(old)))
    assert row["user_id"] == "1" and row.get("org_id") is None
