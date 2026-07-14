"""Tier 1 unit tests — imscc_record / mirror_course_into_imscc (offline WRITE).

Source: lib/tools/_imscc.py (mirror_* + patchers) and lib/tools/imscc_record.py.

The mirror is the inverse of offline_import: it PATCHES course/ edits back into
the source cartridge in place. These tests build a synthetic .imscc that carries
a real quiz QTI question set and a web_resources/ binary, import it to course/,
make known edits, mirror, and assert:
  - the tracked tags now reflect course/ (dates/points/title/published/...);
  - the quiz QTI + web_resources/ bytes are IDENTICAL before/after (patch, not
    rebuild — the decisive property);
  - validate_imscc is clean; identifier mapping is correct;
  - a missing sidecar errors cleanly; an unedited mirror is a byte-for-byte
    idempotent copy (fields_changed == 0).
"""
import json
import subprocess
import sys
import zipfile
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from _imscc import mirror_course_into_imscc, validate_imscc  # noqa: E402
from offline_import import import_imscc  # noqa: E402

RECORD_TOOL = _TOOLS_DIR / "imscc_record.py"

gA = "g" + "a" * 32   # assignment
gB = "g" + "b" * 32   # quiz
gC = "g" + "c" * 32   # wiki page
gG = "g" + "d" * 32   # assignment group
gCOURSE = "g" + "e" * 32

QTI_BYTES = (
    '<?xml version="1.0"?><questestinterop><assessment ident="' + gB + '">'
    '<section ident="root_section">'
    '<item ident="q1" title="What is 2+2?"><presentation>4</presentation></item>'
    "</section></assessment></questestinterop>"
).encode("utf-8")
PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00binary-image-bytes\xff\xd9"


def _make_source(path: Path) -> Path:
    manifest = (
        '<?xml version="1.0"?><manifest identifier="gmanifest">'
        "<organizations/><resources>"
        f'<resource identifier="{gCOURSE}" type="associatedcontent/imscc_xmlv1p1/'
        'learning-application-resource" href="course_settings/canvas_export.txt">'
        '<file href="course_settings/module_meta.xml"/>'
        '<file href="course_settings/assignment_groups.xml"/>'
        '<file href="course_settings/canvas_export.txt"/></resource>'
        f'<resource identifier="{gA}" type="associatedcontent/imscc_xmlv1p1/'
        f'learning-application-resource" href="{gA}/hw-1.html">'
        f'<file href="{gA}/hw-1.html"/><file href="{gA}/assignment_settings.xml"/></resource>'
        f'<resource identifier="{gB}" type="imsqti_xmlv1p2/imscc_xmlv1p1/assessment">'
        f'<file href="{gB}/assessment_qti.xml"/></resource>'
        f'<resource identifier="{gC}" type="webcontent" href="wiki_content/overview.html">'
        '<file href="wiki_content/overview.html"/></resource>'
        "</resources></manifest>"
    )
    module_meta = (
        '<modules><module identifier="gmod1"><title>Week 1</title>'
        "<workflow_state>active</workflow_state><position>1</position>"
        "<require_sequential_progress>false</require_sequential_progress><locked>false</locked>"
        "<items>"
        f'<item identifier="gi1"><content_type>Assignment</content_type>'
        f"<workflow_state>active</workflow_state><title>HW 1</title>"
        f"<identifierref>{gA}</identifierref><position>1</position></item>"
        f'<item identifier="gi2"><content_type>Quizzes::Quiz</content_type>'
        f"<workflow_state>active</workflow_state><title>Quiz 1</title>"
        f"<identifierref>{gB}</identifierref><position>2</position></item>"
        f'<item identifier="gi3"><content_type>WikiPage</content_type>'
        f"<workflow_state>active</workflow_state><title>Overview</title>"
        f"<identifierref>{gC}</identifierref><position>3</position></item>"
        "</items></module></modules>"
    )
    assignment = (
        '<?xml version="1.0"?>'
        f'<assignment identifier="{gA}"><title>HW 1</title>'
        "<due_at>2026-09-05T05:59:00</due_at><lock_at/><unlock_at/>"
        f"<assignment_group_identifierref>{gG}</assignment_group_identifierref>"
        "<workflow_state>published</workflow_state>"
        "<points_possible>100.0</points_possible><grading_type>points</grading_type>"
        "<submission_types>online_upload,online_text_entry</submission_types>"
        "<position>1</position></assignment>"
    )
    quiz = (
        '<?xml version="1.0"?>'
        f'<quiz identifier="{gB}"><title>Quiz 1</title>'
        "<description>Answer the questions.</description>"
        "<quiz_type>assignment</quiz_type><points_possible>10.0</points_possible>"
        "<available>true</available>"
        f'<assignment identifier="ginner"><title>Quiz 1</title>'
        "<due_at>2026-09-12T05:59:00</due_at><lock_at/><unlock_at/>"
        "<workflow_state>published</workflow_state>"
        f"<assignment_group_identifierref>{gG}</assignment_group_identifierref>"
        "<submission_types>online_quiz</submission_types><points_possible>10.0</points_possible>"
        "</assignment>"
        f"<assignment_group_identifierref>{gG}</assignment_group_identifierref></quiz>"
    )
    groups = (
        '<?xml version="1.0"?><assignmentGroups>'
        f'<assignmentGroup identifier="{gG}"><title>Homework</title>'
        "<position>1</position><group_weight>100.0</group_weight></assignmentGroup>"
        "</assignmentGroups>"
    )
    files = {
        "imsmanifest.xml": manifest,
        "course_settings/canvas_export.txt": "Q\n",
        "course_settings/context.xml": "<context_info><course_id>4242</course_id></context_info>",
        "course_settings/course_settings.xml": "<course><title>Sample</title></course>",
        "course_settings/module_meta.xml": module_meta,
        "course_settings/assignment_groups.xml": groups,
        "course_settings/syllabus.html": "<h1>Syllabus</h1><p>Original policy.</p>",
        f"{gA}/assignment_settings.xml": assignment,
        f"{gA}/hw-1.html": "<p>Read chapter 1 and submit.</p>",
        f"{gB}/assessment_meta.xml": quiz,
        f"{gB}/assessment_qti.xml": QTI_BYTES.decode("utf-8"),
        f"non_cc_assessments/{gB}.xml.qti": QTI_BYTES.decode("utf-8"),
        "wiki_content/overview.html":
            '<html><head><title>Overview</title>'
            f'<meta name="identifier" content="{gC}"/>'
            '<meta name="workflow_state" content="active"/></head>'
            "<body><p>hi</p></body></html>",
    }
    with zipfile.ZipFile(path, "w") as z:
        for name, content in files.items():
            z.writestr(name, content)
        z.writestr("web_resources/img.png", PNG_BYTES)
    return path


def _entry(imscc, name):
    with zipfile.ZipFile(imscc) as z:
        return z.read(name)


def _prep(tmp_path):
    """Build source -> import to course/ (+ sidecar). Returns (course_dir, src)."""
    src = _make_source(tmp_path / "src.imscc")
    course = tmp_path / "course"
    import_imscc(src, course)
    sidecar = course / ".source.imscc"
    assert sidecar.is_file()                 # offline_import saved the source of truth
    assert _entry(sidecar, "web_resources/img.png") == PNG_BYTES  # byte-for-byte copy
    return course, sidecar


# --- the core: patch tracked fields, preserve everything else --------------

def test_mirror_sets_edited_fields_and_preserves_qti(tmp_path):
    course, src = _prep(tmp_path)

    # KNOWN edits in course/
    hw = json.loads((course / "week-1" / "hw-1.json").read_text())
    hw["due_at"] = "2026-09-19T05:59:00"          # shift a date
    hw["points_possible"] = 50.0                  # change points
    hw["workflow_state"] = "unpublished"          # toggle published
    hw["published"] = False
    (course / "week-1" / "hw-1.json").write_text(json.dumps(hw))
    (course / "week-1" / "overview.html").write_text(
        '<html><head><title>Overview</title>'
        f'<meta name="identifier" content="{gC}"/>'
        '<meta name="workflow_state" content="active"/></head>'
        "<body><p>EDITED BODY</p></body></html>")

    out = tmp_path / "out.imscc"
    counts = mirror_course_into_imscc(course, src, out)

    a = _entry(out, f"{gA}/assignment_settings.xml").decode()
    assert "<due_at>2026-09-19T05:59:00</due_at>" in a
    assert "<points_possible>50.0</points_possible>" in a
    assert "<workflow_state>unpublished</workflow_state>" in a
    assert f"<assignment_group_identifierref>{gG}</assignment_group_identifierref>" in a  # untouched
    assert "EDITED BODY" in _entry(out, "wiki_content/overview.html").decode()

    # the whole point: quiz questions + files survive byte-for-byte
    assert _entry(out, f"{gB}/assessment_qti.xml") == QTI_BYTES
    assert _entry(out, f"non_cc_assessments/{gB}.xml.qti") == QTI_BYTES
    assert _entry(out, "web_resources/img.png") == PNG_BYTES
    assert validate_imscc(out) == []
    assert counts["fields_changed"] >= 3 and counts["skipped"] == 0


def test_mirror_records_quiz_and_group_and_syllabus(tmp_path):
    course, src = _prep(tmp_path)

    q = json.loads((course / "week-1" / "quiz-1.json").read_text())
    q["name"] = "Quiz 1 (Renamed)"
    q["due_at"] = "2026-09-20T05:59:00"
    (course / "week-1" / "quiz-1.json").write_text(json.dumps(q))
    groups = json.loads((course / "_assignment_groups.json").read_text())
    groups[0]["group_weight"] = 40.0
    (course / "_assignment_groups.json").write_text(json.dumps(groups))
    (course / "syllabus.html").write_text("<h1>Syllabus</h1><p>NEW policy.</p>")

    out = tmp_path / "out.imscc"
    mirror_course_into_imscc(course, src, out)

    quiz_xml = _entry(out, f"{gB}/assessment_meta.xml").decode()
    assert "<title>Quiz 1 (Renamed)</title>" in quiz_xml       # quiz-level title patched
    assert "<due_at>2026-09-20T05:59:00</due_at>" in quiz_xml   # nested-assignment date patched
    assert "root_section" not in quiz_xml                       # (sanity: meta != qti)
    assert "<group_weight>40.0</group_weight>" in _entry(out, "course_settings/assignment_groups.xml").decode()
    assert "NEW policy" in _entry(out, "course_settings/syllabus.html").decode()
    assert _entry(out, f"{gB}/assessment_qti.xml") == QTI_BYTES  # still preserved


def test_mirror_writes_added_outcome(tmp_path):
    course, src = _prep(tmp_path)
    oid = "g" + "f" * 32
    (course / "_outcomes.json").write_text(json.dumps(
        [{"id": oid, "title": "Solve equations", "description": "CLO 1", "display_name": "Solve"}]))

    out = tmp_path / "out.imscc"
    mirror_course_into_imscc(course, src, out)

    lo = _entry(out, "course_settings/learning_outcomes.xml").decode()
    assert f'<learningOutcome identifier="{oid}">' in lo
    assert "Solve equations" in lo
    # and the new file is referenced in the manifest so Canvas imports it
    man = _entry(out, "imsmanifest.xml").decode()
    assert '<file href="course_settings/learning_outcomes.xml"/>' in man
    assert validate_imscc(out) == []


# --- idempotence: an unedited mirror is a byte-for-byte copy ----------------

def test_mirror_idempotent_when_nothing_edited(tmp_path):
    course, src = _prep(tmp_path)
    out = tmp_path / "out.imscc"
    counts = mirror_course_into_imscc(course, src, out)
    assert counts["fields_changed"] == 0
    with zipfile.ZipFile(src) as zs, zipfile.ZipFile(out) as zo:
        assert set(zs.namelist()) == set(zo.namelist())
        for name in zs.namelist():
            assert zs.read(name) == zo.read(name), f"{name} changed on a no-op mirror"


# --- identifier mapping ----------------------------------------------------

def test_identifier_mapping_targets_the_right_resource(tmp_path):
    course, src = _prep(tmp_path)
    # edit ONLY the assignment; the quiz resource must be untouched
    hw = json.loads((course / "week-1" / "hw-1.json").read_text())
    hw["name"] = "HW 1 RENAMED"
    (course / "week-1" / "hw-1.json").write_text(json.dumps(hw))
    out = tmp_path / "out.imscc"
    mirror_course_into_imscc(course, src, out)
    assert "HW 1 RENAMED" in _entry(out, f"{gA}/assignment_settings.xml").decode()
    assert _entry(out, f"{gB}/assessment_meta.xml") == _entry(src, f"{gB}/assessment_meta.xml")


# --- CLI: missing sidecar errors cleanly -----------------------------------

def test_cli_missing_sidecar_errors(tmp_path):
    course = tmp_path / "course"
    course.mkdir()
    (course / "_course.json").write_text("{}")
    r = subprocess.run(
        [sys.executable, str(RECORD_TOOL), "--course-dir", str(course)],
        capture_output=True, text=True,
    )
    assert r.returncode == 2
    assert "no source cartridge" in r.stderr


def _make_shared_and_unfiled_source(path: Path) -> Path:
    """A cartridge where ONE assignment (gS) is an item in two modules under
    DIFFERENT per-module titles, plus an assignment (gU) in NO module (unfiled).
    Reproduces the join bug: a title/slug guess can't reliably find gS's file and
    never finds gU at all — only the recorded _index.json path does."""
    gS = "g" + "1" * 32   # shared across two modules, different titles
    gU = "g" + "2" * 32   # unfiled (in manifest, referenced by no module)
    gCO = "g" + "3" * 32
    man = (
        '<?xml version="1.0"?><manifest identifier="gm"><organizations/><resources>'
        f'<resource identifier="{gCO}" type="associatedcontent/imscc_xmlv1p1/'
        'learning-application-resource" href="course_settings/canvas_export.txt">'
        '<file href="course_settings/module_meta.xml"/>'
        '<file href="course_settings/canvas_export.txt"/></resource>'
        f'<resource identifier="{gS}" type="associatedcontent/imscc_xmlv1p1/'
        f'learning-application-resource" href="{gS}/assignment_settings.xml">'
        f'<file href="{gS}/assignment_settings.xml"/></resource>'
        f'<resource identifier="{gU}" type="associatedcontent/imscc_xmlv1p1/'
        f'learning-application-resource" href="{gU}/assignment_settings.xml">'
        f'<file href="{gU}/assignment_settings.xml"/></resource>'
        "</resources></manifest>"
    )
    module_meta = (
        '<modules>'
        '<module identifier="gm1"><title>Week 1</title><workflow_state>active</workflow_state>'
        '<position>1</position><items>'
        f'<item identifier="gia"><content_type>Assignment</content_type>'
        f'<workflow_state>active</workflow_state><title>Project 2</title>'
        f'<identifierref>{gS}</identifierref><position>1</position></item>'
        '</items></module>'
        '<module identifier="gm2"><title>Week 2</title><workflow_state>active</workflow_state>'
        '<position>2</position><items>'
        f'<item identifier="gib"><content_type>Assignment</content_type>'
        f'<workflow_state>active</workflow_state><title>Project 2 Task 2 - Ready for Review</title>'
        f'<identifierref>{gS}</identifierref><position>1</position></item>'
        '</items></module></modules>'
    )
    def asg(ident, pts):
        return (f'<?xml version="1.0"?><assignment identifier="{ident}"><title>A</title>'
                "<due_at/><lock_at/><unlock_at/><workflow_state>published</workflow_state>"
                f"<points_possible>{pts}</points_possible><grading_type>points</grading_type>"
                "<submission_types>online_upload</submission_types></assignment>")
    files = {
        "imsmanifest.xml": man,
        "course_settings/canvas_export.txt": "Q\n",
        "course_settings/context.xml": "<context_info><course_id>1</course_id></context_info>",
        "course_settings/module_meta.xml": module_meta,
        f"{gS}/assignment_settings.xml": asg(gS, "10.0"),
        f"{gU}/assignment_settings.xml": asg(gU, "100.0"),
    }
    with zipfile.ZipFile(path, "w") as z:
        for name, content in files.items():
            z.writestr(name, content)
    return path, gS, gU


def test_shared_across_modules_and_unfiled_are_recordable(tmp_path):
    """Regression: the join must be by recorded path, not a title/slug guess —
    a resource shared under two titles AND an unfiled resource must both record."""
    src, gS, gU = _make_shared_and_unfiled_source(tmp_path / "src.imscc")
    course = tmp_path / "course"
    import_imscc(src, course)

    idx = json.loads((course / "_index.json").read_text())
    assert gS in idx and gU in idx                       # both indexed (unfiled included)

    # edit the shared assignment (via its recorded file) AND the unfiled one
    for ref in (gS, gU):
        p = course / idx[ref]["path"]
        d = json.loads(p.read_text())
        d["points_possible"] = 55.0
        p.write_text(json.dumps(d))

    out = tmp_path / "out.imscc"
    counts = mirror_course_into_imscc(course, course / ".source.imscc", out)

    assert "<points_possible>55.0</points_possible>" in _entry(out, f"{gS}/assignment_settings.xml").decode()
    assert "<points_possible>55.0</points_possible>" in _entry(out, f"{gU}/assignment_settings.xml").decode()
    assert counts["assignments"] == 2 and counts["skipped"] == 0
    assert validate_imscc(out) == []


def test_missing_index_errors_loudly(tmp_path):
    """A course/ with no _index.json can't be joined — fail loud, never silent."""
    course, _ = _prep(tmp_path)
    (course / "_index.json").unlink()
    import pytest
    with pytest.raises(SystemExit, match="_index.json"):
        mirror_course_into_imscc(course, course / ".source.imscc", tmp_path / "o.imscc")


def test_cli_records_in_place(tmp_path):
    course, src = _prep(tmp_path)
    before = src.read_bytes()
    hw = json.loads((course / "week-1" / "hw-1.json").read_text())
    hw["points_possible"] = 7.0
    (course / "week-1" / "hw-1.json").write_text(json.dumps(hw))
    r = subprocess.run(
        [sys.executable, str(RECORD_TOOL), "--course-dir", str(course)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert src.read_bytes() != before                            # sidecar updated in place
    assert "<points_possible>7.0</points_possible>" in _entry(src, f"{gA}/assignment_settings.xml").decode()
    assert _entry(src, f"{gB}/assessment_qti.xml") == QTI_BYTES   # questions preserved in place
