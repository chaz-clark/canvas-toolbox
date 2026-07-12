"""
Canvas gradebook CSV parsing/writing for offline mode (Sprint 1).

Ground truth: a real BYU-Idaho export (2026-07, DS 250) — 120 columns for 65
assignments, because group weighting adds per-group total columns. Layout:

  row 0        header
  row 1        Points Possible — Student cell is '    Points Possible' (leading
               spaces); read-only columns carry the literal '(read only)'
  rows 2..n    one per student

Column classes (left → right):
  identity (6, fixed order): Student, ID, SIS User ID, SIS Login ID,
                             Root Account, Section
  assignment  : header ends with ' (<assignment_id>)'  → gradeable
  read-only   : everything else (group-total columns like
                'Checkpoints Current Score', and the trailing 8 summary columns
                'Current Score' … 'Unposted Final Grade'). Canvas RECOMPUTES
                these on import — never write them back.

Canvas gradebook Import (Grades → Import) reads identity + assignment columns
only. It ignores read-only columns and does NOT accept submission comments
(scores only — see docs/offline_mode.md and imscc_format_knowledge.md).
"""
import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Fixed identity columns, in the exact order Canvas emits them.
IDENTITY_COLUMNS = [
    "Student", "ID", "SIS User ID", "SIS Login ID", "Root Account", "Section",
]
# Some older/instance exports omit "Root Account"; accept a 5-col identity block too.
IDENTITY_COLUMNS_LEGACY = [
    "Student", "ID", "SIS User ID", "SIS Login ID", "Section",
]

_ASSIGNMENT_RE = re.compile(r"^(?P<name>.*?)\s*\((?P<id>\d+)\)\s*$")
_READ_ONLY_MARKER = "(read only)"


@dataclass
class AssignmentColumn:
    """A gradeable assignment column: header 'Name (assignment_id)'."""
    index: int
    name: str
    assignment_id: str
    points_possible: str  # kept as the raw CSV string (may be '' or e.g. '100')


@dataclass
class Gradebook:
    """Parsed Canvas gradebook CSV.

    `students` are the data rows (identity + raw cells). Read-only/group-total
    columns are preserved verbatim in each row's `raw` and re-emitted unchanged
    by write_canvas_gradebook_csv().
    """
    path: Optional[Path]
    header: list[str]
    points_possible_row: Optional[list[str]]
    assignments: list[AssignmentColumn]
    identity_columns: list[str]
    readonly_indices: set[int]
    students: list["StudentRow"] = field(default_factory=list)

    def assignment_by_id(self, assignment_id: str) -> Optional[AssignmentColumn]:
        for a in self.assignments:
            if a.assignment_id == str(assignment_id):
                return a
        return None

    def to_rows(self) -> list[list[str]]:
        rows = [list(self.header)]
        if self.points_possible_row is not None:
            rows.append(list(self.points_possible_row))
        rows.extend(s.raw for s in self.students)
        return rows


@dataclass
class StudentRow:
    """One student's row. Identity fields are convenience views onto `raw`;
    `raw` is the full, column-aligned source of truth used for writing."""
    raw: list[str]
    _gradebook: "Gradebook"

    def _idx(self, colname: str) -> int:
        return self._gradebook.header.index(colname)

    @property
    def student(self) -> str:
        return self.raw[0] if self.raw else ""

    @property
    def canvas_id(self) -> str:
        i = self._idx("ID")
        return self.raw[i] if i < len(self.raw) else ""

    @property
    def section(self) -> str:
        i = self._idx("Section")
        return self.raw[i] if i < len(self.raw) else ""

    def get_grade(self, assignment_id: str) -> Optional[str]:
        a = self._gradebook.assignment_by_id(assignment_id)
        if a is None or a.index >= len(self.raw):
            return None
        return self.raw[a.index]

    def set_grade(self, assignment_id: str, value: str) -> None:
        """Set the raw cell value for an assignment. Read-only columns are never
        addressable here (only assignment columns have ids), so this can't
        accidentally write a computed column."""
        a = self._gradebook.assignment_by_id(assignment_id)
        if a is None:
            raise KeyError(f"No assignment column with id {assignment_id!r}")
        # Pad the row if a short export truncated trailing empties.
        while len(self.raw) <= a.index:
            self.raw.append("")
        self.raw[a.index] = value


def is_points_possible_row(row: list[str]) -> bool:
    """The Points Possible row's Student cell is 'Points Possible' (Canvas emits
    it with leading spaces)."""
    return bool(row) and row[0].strip() == "Points Possible"


def _first_assignment_index(header: list[str]) -> Optional[int]:
    """Index of the first assignment column ('Name (id)'), or None when the
    gradebook has no assignments."""
    for i, h in enumerate(header):
        if _ASSIGNMENT_RE.match(h):
            return i
    return None


def _identity_block(header: list[str]) -> list[str]:
    """The leading metadata columns — everything before the first assignment
    column. DERIVED from the data, not a hardcoded list, so it adapts to
    instance variation (with/without 'Root Account', 'Integration ID', extra
    'Override' columns, etc.). Falls back to known identity names only when a
    gradebook has no assignment columns at all."""
    fa = _first_assignment_index(header)
    if fa is not None:
        return header[:fa]
    known = set(IDENTITY_COLUMNS) | set(IDENTITY_COLUMNS_LEGACY)
    return [h for h in header if h in known]


def _looks_like_gradebook(header: list[str]) -> bool:
    """A Canvas gradebook always leads with at least 'Student' and 'ID'."""
    block = _identity_block(header)
    return "Student" in block and "ID" in block


def detect_csv_format(path) -> bool:
    """True if `path` looks like a Canvas gradebook export (leads with
    Student/ID metadata columns). Cheap check for auto-detection / clear
    errors; makes no assumption about column count or which assignments exist."""
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            header = next(csv.reader(f))
    except (OSError, StopIteration):
        return False
    return _looks_like_gradebook(header)


def read_canvas_gradebook_csv(path) -> Gradebook:
    """Parse a Canvas gradebook CSV into a Gradebook.

    Raises ValueError if the header doesn't match a Canvas gradebook layout —
    fail loud rather than mis-parse (a wrong file would corrupt grades on
    re-upload).
    """
    path = Path(path)
    # utf-8-sig strips the BOM Canvas sometimes prepends.
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    if not rows:
        raise ValueError(f"{path} is empty — not a Canvas gradebook CSV")

    header = rows[0]
    if not _looks_like_gradebook(header):
        raise ValueError(
            f"{path} does not look like a Canvas gradebook export "
            f"(no leading 'Student'/'ID' columns); got {header[:6]}. "
            f"Export via Grades → Export → Export Entire Gradebook."
        )
    identity = _identity_block(header)

    body = rows[1:]
    pp_row = body[0] if body and is_points_possible_row(body[0]) else None
    data_rows = body[1:] if pp_row is not None else body

    # Classify columns and pull assignment metadata from the Points Possible row.
    assignments: list[AssignmentColumn] = []
    readonly: set[int] = set()
    id_count = len(identity)
    for i, h in enumerate(header):
        if i < id_count:
            continue
        m = _ASSIGNMENT_RE.match(h)
        if m:
            pp = (
                pp_row[i]
                if pp_row is not None and i < len(pp_row) and pp_row[i] != _READ_ONLY_MARKER
                else ""
            )
            assignments.append(
                AssignmentColumn(
                    index=i,
                    name=m.group("name"),
                    assignment_id=m.group("id"),
                    points_possible=pp,
                )
            )
        else:
            readonly.add(i)

    gb = Gradebook(
        path=path,
        header=header,
        points_possible_row=pp_row,
        assignments=assignments,
        identity_columns=identity,
        readonly_indices=readonly,
    )
    # Skip fully blank trailing rows (Canvas sometimes emits one).
    gb.students = [
        StudentRow(raw=r, _gradebook=gb)
        for r in data_rows
        if any(cell.strip() for cell in r)
    ]
    return gb


def write_canvas_gradebook_csv(gradebook: Gradebook, path) -> Path:
    """Write a Gradebook back to Canvas CSV format (QUOTE_MINIMAL, matching
    Canvas). Read-only/group-total columns are emitted unchanged from `raw`."""
    path = Path(path)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)  # QUOTE_MINIMAL — quotes only fields needing it
        w.writerows(gradebook.to_rows())
    return path
