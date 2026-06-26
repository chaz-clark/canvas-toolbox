#!/usr/bin/env python3
"""
apply_sas_accommodations.py — Dispatcher for BYUI Accessibility Services
accommodation letters.

Reads a structured SAS handoff (YAML), dispatches each accommodation
to the right Canvas tool per the catalog at
`lib/agents/knowledge/sas_accommodations_knowledge.md`. Three tiers:

  canvas      — calls a canvas-toolbox tool (per-student override / extension)
  proctoring  — flags for the operator (Proctorio / Testing Center setup)
  policy      — flags for the operator (instructor-practice checklist;
                no Canvas API change)

PII-FREE END TO END
  The YAML carries `deid_code`, never names. The dispatcher resolves
  code → user_id via the de-id master only when needed by a downstream
  tool, and never reads the sortable_name column.

HANDOFF SCHEMA (life-pm produces; canvas-toolbox consumes)

  Default path: grading/.sas_accommodations.yml (FERPA tier 2 gitignored)

  - deid_code: S-95DBB6
    letter_date: 2026-06-22
    accommodations:
      - key: extra_time_1.5x       # required
      - key: occasional_extensions
        scope: from_days_ago       # optional, defaults to all
        days: 14
      - key: test_reschedule
        shift_by_days: 7           # optional, defaults to 7
        assignment_id: 12345       # optional; if absent, applies to all
      - key: spelling_grammar      # policy tier → emit checklist line
      - key: proctorio_breaks      # proctoring tier → emit checklist line

KEY → TOOL MAPPING (only the canvas tier is dispatched here;
proctoring + policy are surfaced as a checklist)

  extra_time_1.5x       → student_quiz_time_extension --multiplier 1.5 --all-timed
  extra_time_2.0x       → student_quiz_time_extension --multiplier 2.0 --all-timed
  occasional_extensions → student_late_accommodation --all
                          (with optional scope flags from YAML)
  test_reschedule       → student_late_accommodation --shift-by-days N

USAGE — dry-run by default
  uv run python lib/tools/apply_sas_accommodations.py
  uv run python lib/tools/apply_sas_accommodations.py --apply
  uv run python lib/tools/apply_sas_accommodations.py \\
    --file /path/to/.sas_accommodations.yml --apply

REQUIRES in .env: CANVAS_API_TOKEN, CANVAS_BASE_URL, CANVAS_COURSE_ID
REQUIRES: grading/.deid_master.csv (build with build_deid_master.py)
REQUIRES (Python deps): pyyaml (already in canvas-toolbox dependencies)

Resolves: the rest of the SAS catalog dispatch path. Audit log is
written to grading/.sas_accommodations_applied.log (tier 2, gitignored)
so faculty have a per-semester record of what was applied.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml is required. Install with: uv sync", file=sys.stderr)
    sys.exit(2)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


_DEFAULT_HANDOFF = Path("grading/.sas_accommodations.yml")
_DEFAULT_AUDIT_LOG = Path("grading/.sas_accommodations_applied.log")


# ---------------------------------------------------------------------------
# Catalog — the single source of truth for what each key dispatches to
# ---------------------------------------------------------------------------

# Tier classification per the catalog handoff
# (handoffs/2026-06-26-accessibility-accommodations-catalog.md).
_CANVAS_KEYS = {
    "extra_time_1.5x",
    "extra_time_2.0x",
    "occasional_extensions",
    "test_reschedule",
}
_PROCTORING_KEYS = {
    "proctorio_breaks",
    "private_room_exams",
}
_POLICY_KEYS = {
    "assignment_clarification",
    "recording_device",
    "breaks_during_class",
    "spelling_grammar",
    "food_drink_medication",
    "class_participation_mod",
    "attendance_notification",
    "hat_in_class",
    "tinted_glasses",
    "service_animal",
}
_ALL_KEYS = _CANVAS_KEYS | _PROCTORING_KEYS | _POLICY_KEYS


# ---------------------------------------------------------------------------
# Pure helpers (no I/O, no subprocess — easy to unit-test)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DispatchPlan:
    """One planned action for one student × one accommodation key."""
    deid_code: str
    key: str
    tier: str               # "canvas" | "proctoring" | "policy" | "unknown"
    command: list[str] | None  # CLI argv for canvas tier; None otherwise
    note: str               # human-readable explanation (always set)


def classify_key(key: str) -> str:
    """Return 'canvas' | 'proctoring' | 'policy' | 'unknown' for a key."""
    if key in _CANVAS_KEYS:
        return "canvas"
    if key in _PROCTORING_KEYS:
        return "proctoring"
    if key in _POLICY_KEYS:
        return "policy"
    return "unknown"


def plan_one_accommodation(deid_code: str, acc: dict) -> DispatchPlan:
    """Build one DispatchPlan from a single accommodation dict.

    Doesn't run anything — just decides what WOULD run. The CLI walks
    a list of these and executes the `canvas` tier ones when --apply
    is set.
    """
    key = (acc.get("key") or "").strip()
    tier = classify_key(key)

    if tier == "canvas":
        cmd, note = _build_canvas_command(deid_code, key, acc)
        return DispatchPlan(deid_code, key, "canvas", cmd, note)

    if tier == "proctoring":
        return DispatchPlan(
            deid_code, key, "proctoring", None,
            f"PROCTORING: faculty action required outside Canvas "
            f"(Proctorio config or Testing Center reservation).",
        )

    if tier == "policy":
        return DispatchPlan(
            deid_code, key, "policy", None,
            f"POLICY: instructor-practice flag — no LMS change. "
            f"Add to your accommodation checklist for this student.",
        )

    return DispatchPlan(
        deid_code, key, "unknown", None,
        f"UNKNOWN key {key!r} — not in the v0.72.0 catalog. Skipping. "
        f"Either typo in the YAML or a new SAS accommodation type that "
        f"needs adding to lib/agents/knowledge/sas_accommodations_knowledge.md.",
    )


def _build_canvas_command(deid_code: str, key: str,
                          acc: dict) -> tuple[list[str], str]:
    """Build the CLI argv for one canvas-tier accommodation.

    Returns (argv, note). Note is a human-readable summary the CLI prints.

    Tools are invoked as subprocess so they each enforce their own
    env-validation + .env loading + de-id master lookup. We do NOT
    cross-import them — each tool stays standalone.
    """
    common = ["uv", "run", "python", "lib/tools/"]

    if key == "extra_time_1.5x":
        cmd = common + ["student_quiz_time_extension.py",
                        "--deid-code", deid_code,
                        "--multiplier", "1.5",
                        "--all-timed"]
        note = "Canvas: +50% extra time on all timed classic quizzes."
        return cmd, note

    if key == "extra_time_2.0x":
        cmd = common + ["student_quiz_time_extension.py",
                        "--deid-code", deid_code,
                        "--multiplier", "2.0",
                        "--all-timed"]
        note = "Canvas: +100% (double time) on all timed classic quizzes."
        return cmd, note

    if key == "occasional_extensions":
        # Default: --all (whole-semester backdated lock_at=null grant).
        # YAML may override scope: 'from_days_ago' or 'from' for a tighter window.
        cmd = common + ["student_late_accommodation.py",
                        "--deid-code", deid_code]
        scope = (acc.get("scope") or "").strip()
        if scope == "from_days_ago":
            days = int(acc.get("days", 14))
            cmd += ["--from-days-ago", str(days)]
            note = f"Canvas: lock_at=null on assignments due in the last {days} days + future."
        elif scope == "from":
            cutoff = str(acc.get("from") or "").strip()
            cmd += ["--from", cutoff]
            note = f"Canvas: lock_at=null on assignments due on/after {cutoff}."
        else:
            cmd += ["--all"]
            note = "Canvas: lock_at=null on ALL published assignments (backdated)."
        return cmd, note

    if key == "test_reschedule":
        days = int(acc.get("shift_by_days", 7))
        cmd = common + ["student_late_accommodation.py",
                        "--deid-code", deid_code,
                        "--shift-by-days", str(days)]
        if acc.get("assignment_id"):
            cmd += ["--assignment-id", str(int(acc["assignment_id"]))]
            scope_text = f"assignment {acc['assignment_id']}"
        else:
            cmd += ["--all"]
            scope_text = "ALL published assignments"
        note = f"Canvas: shift unlock+due+lock forward {days} days on {scope_text}."
        return cmd, note

    # Should never reach (classify_key filtered to canvas already)
    raise AssertionError(f"unhandled canvas-tier key: {key}")


def plan_entries(entries: list[dict]) -> list[DispatchPlan]:
    """Walk an entire SAS handoff YAML and produce a flat list of
    DispatchPlan objects — one per (student, accommodation key) pair."""
    out: list[DispatchPlan] = []
    for entry in entries:
        deid = (entry.get("deid_code") or "").strip()
        if not deid:
            continue
        for acc in entry.get("accommodations") or []:
            out.append(plan_one_accommodation(deid, acc))
    return out


def render_audit_line(plan: DispatchPlan, status: str,
                      timestamp: str) -> str:
    """One line for the applied-audit log. Single-line CSV-ish format
    so it's easy to grep / tail later."""
    return (f"{timestamp}\t{status}\t{plan.deid_code}\t{plan.key}\t"
            f"{plan.tier}\t{plan.note}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--file", type=Path, default=_DEFAULT_HANDOFF,
                    help=f"SAS handoff YAML (default {str(_DEFAULT_HANDOFF)!r})")
    ap.add_argument("--audit-log", type=Path, default=_DEFAULT_AUDIT_LOG,
                    help=f"audit log path (default {str(_DEFAULT_AUDIT_LOG)!r})")
    ap.add_argument("--apply", action="store_true",
                    help="actually invoke the downstream tools "
                         "(without this, dry-run prints planned commands)")
    args = ap.parse_args()

    if not args.file.exists():
        print(f"ERROR: SAS handoff not found at {args.file}.", file=sys.stderr)
        print(f"Expected schema documented in: "
              f"lib/agents/knowledge/sas_accommodations_knowledge.md",
              file=sys.stderr)
        return 2

    entries = yaml.safe_load(args.file.read_text(encoding="utf-8")) or []
    if not isinstance(entries, list):
        print(f"ERROR: top-level of {args.file} must be a YAML list.",
              file=sys.stderr)
        return 2

    plans = plan_entries(entries)
    apply_ = "APPLY" if args.apply else "DRY-RUN"
    print(f"Loaded {len(plans)} planned action(s) from {args.file} | {apply_}\n")

    # Print plans grouped by tier so the operator sees the checklist
    # they need to handle manually for proctoring + policy tiers.
    fails = 0
    audit_lines: list[str] = []
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

    for plan in plans:
        prefix = f"[{plan.deid_code} {plan.key:24s}]"
        if plan.tier in {"proctoring", "policy", "unknown"}:
            print(f"{prefix} {plan.note}")
            audit_lines.append(render_audit_line(plan, "FLAGGED", timestamp))
            continue

        # canvas tier
        print(f"{prefix} {plan.note}")
        print(f"    cmd: {' '.join(plan.command)}")

        if not args.apply:
            audit_lines.append(render_audit_line(plan, "PLANNED", timestamp))
            continue

        result = subprocess.run(plan.command, capture_output=True, text=True)
        if result.returncode == 0:
            print("    OK")
            audit_lines.append(render_audit_line(plan, "APPLIED", timestamp))
        else:
            print(f"    FAIL (exit {result.returncode})")
            print(f"    stderr: {result.stderr.strip()[:300]}")
            fails += 1
            audit_lines.append(render_audit_line(plan, "FAILED", timestamp))

    # Audit log append (tier 2 gitignored)
    if audit_lines:
        args.audit_log.parent.mkdir(parents=True, exist_ok=True)
        with args.audit_log.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(audit_lines) + "\n")
        print(f"\nAudit log appended: {args.audit_log}")

    if fails:
        print(f"\n{fails} action(s) failed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
