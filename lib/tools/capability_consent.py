#!/usr/bin/env python3
"""capability_consent.py — fingerprint, summarize, and gate agent-package
capability growth (v2, #317 Phase 7).

WHY THIS EXISTS
  A package manifest (agent-packages/<id>/manifest.yaml) declares what a
  package can do — Canvas writers, student-data classes, credentials, network
  scope. Installation is a trust event: an instructor who approved "reads
  course content" should see a fresh approval request before a later version
  quietly adds "writes grades." Without a persisted record of what was last
  approved, every install looks identical to the operator, and capability
  growth ships as silently as capability-neutral changes do.

THE BOUNDARY THIS ENFORCES
  A package cannot approve itself. Nothing here reads or trusts any "approved"
  or "pre-approved" field a manifest might try to declare — the schema doesn't
  even define one (schemas/agent-packages/package-manifest.schema.json rejects
  unknown keys). The ONLY way an approval is recorded is `record_approval()`,
  called by a human-driven invocation (an agent relaying the instructor's chat
  confirmation) with an explicit `approved_by` string this module never
  infers from manifest content.

WHAT COUNTS AS GROWTH
  A NEW package (never approved) is growth by definition — every capability it
  declares is new relative to nothing. For an already-approved package, growth
  is a NEW entry in any of: Canvas-write effect types, data classes, Canvas-
  writer tool ids, credential names, or network scope, relative to the last
  APPROVED fingerprint (not the last-flattened one — an unapproved growth from
  three versions ago must still be visible on version four).

  A version-string bump alone, a wording-only description change, or removing
  a capability are NOT growth — none of the fingerprint's capability-bearing
  fields gained an entry. `capability_diff()` computes this per field so a
  human/agent can see exactly what is new, not just that "something changed."

WHAT THIS DOES NOT DO
  Enforcement. This gates the INSTALL decision — whether `cb_flatten.py` may
  proceed. It has no relationship to grade_guardian, canvas_course_guard, or
  the HG-5 review gate, and cannot weaken them. A package could theoretically
  be approved and its Canvas writer still refuse to run without going through
  grader_push.py — the manifest describes access, hooks and tools enforce it
  (docs/proposals/v2-agent-packaging-plan.md, "invariants that must hold").

WHO MAY APPROVE (#343)
  `--approve`/`--approve-all` require an interactive terminal — enforced in
  `cb_flatten.py`'s `check_capability_consent()`, the one caller of
  `record_approval()`. A flag an agent can pass on its own isn't evidence a
  human is present; same reasoning as `grader_push.py`'s
  `require_typed_confirmation` (HG-5, #241). An unattended/scheduled
  `cb_flatten.py --apply --approve-all` run refuses on any capability growth
  rather than silently approving it — approval only counts from a real
  terminal, never a pipe, redirect, or cron invocation.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APPROVALS_FILE = ".canvas-toolbox-approvals.json"
SCHEMA_VERSION = 1

# Fields compared field-by-field for growth. Order is presentation order in
# render_install_summary() and capability_diff() output, not significance.
_FINGERPRINT_FIELDS = ("canvas_writers", "effects", "data_classes", "credentials", "network")


def compute_fingerprint(package: dict[str, Any]) -> dict[str, list[str]]:
    """A stable, order-independent capability summary from a package manifest.
    Never includes a credential VALUE — only the names manifests are already
    restricted to (schema: `credentials` is a name enum, never a secret)."""
    tools = package.get("tools") or []
    return {
        "canvas_writers": sorted(
            t["id"] for t in tools if str(t.get("effect", "")).startswith("canvas_")
        ),
        "effects": sorted({t.get("effect", "") for t in tools}),
        "data_classes": sorted({t.get("data_class", "") for t in tools}),
        "credentials": sorted(package.get("credentials") or []),
        "network": sorted(package.get("network") or []),
    }


def capability_diff(old: dict[str, list[str]] | None,
                    new: dict[str, list[str]]) -> dict[str, list[str]]:
    """{field: [newly-added entries]} for each fingerprint field. `old=None`
    (never approved) means every entry in `new` is newly added."""
    if old is None:
        return {field: list(new.get(field, [])) for field in _FINGERPRINT_FIELDS}
    return {
        field: sorted(set(new.get(field, [])) - set(old.get(field, [])))
        for field in _FINGERPRINT_FIELDS
    }


def has_grown(diff: dict[str, list[str]]) -> bool:
    """True iff `capability_diff()` found a newly-added entry in any field."""
    return any(diff.get(field) for field in _FINGERPRINT_FIELDS)


def render_install_summary(package: dict[str, Any],
                           diff: dict[str, list[str]] | None = None,
                           first_approval: bool = False) -> str:
    """Concise, human-readable — what an agent relays to the instructor before
    asking for approval. Shows Canvas-write tools by NAME (not just a count —
    the instructor is approving specific capabilities, not a number),
    student-data classes, credential names, and network scope.

    `first_approval` (True when `capability_diff()`'s `old` was None — no
    prior approval record exists at all) changes only the header wording.
    Found for real in the m119-master pilot: every capability read as "NEW
    since last approval" on this repo's first-ever v2 consent run, which
    reads as a regression ("this used to be approved and now something
    changed") when nothing was ever approved before. The gating logic is
    identical either way — `has_grown()` is True and approval is required —
    this only fixes what the human is told."""
    fp = compute_fingerprint(package)
    lines = [f"{package.get('name', package.get('id', '?'))} (v{package.get('version', '?')})"]
    lines.append(f"  {package.get('description', '')}")
    lines.append(f"  Canvas-write tools: {', '.join(fp['canvas_writers']) or 'none'}")
    lines.append(f"  Data classes touched: {', '.join(fp['data_classes']) or 'none'}")
    lines.append(f"  Credentials required: {', '.join(fp['credentials']) or 'none'}")
    lines.append(f"  Network scope: {', '.join(fp['network']) or 'none'}")
    if diff is not None:
        newly = {field: entries for field, entries in diff.items() if entries}
        if newly:
            header = ("capabilities requested (first approval for this package):"
                      if first_approval else "NEW since last approval:")
            lines.append(f"  {header}")
            for field, entries in newly.items():
                lines.append(f"    {field}: {', '.join(entries)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Persisted approval record — course-owned, plain JSON, git-tracked like
# AGENTS.md (an audit trail of what was approved and when, not a secret).
# ---------------------------------------------------------------------------

def load_approvals(course_root: Path) -> dict[str, Any]:
    """{package_id: {fingerprint, approved_at, approved_by}}. Missing/corrupt
    file → empty dict (every package treated as never-approved — fails toward
    requiring consent, never toward silently granting it)."""
    path = course_root / APPROVALS_FILE
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(doc, dict):
        return {}
    return doc.get("packages") or {}


def record_approval(course_root: Path, package_id: str,
                    fingerprint: dict[str, list[str]], approved_by: str) -> None:
    """Persist that `package_id`'s current fingerprint is approved.

    `approved_by` is REQUIRED and never defaulted — the caller (a human-driven
    CLI invocation) must supply it explicitly. Nothing in this module ever
    derives it from package content, which is the whole boundary: a package
    cannot approve itself, and this is the only function that writes approval
    state."""
    if not approved_by or not approved_by.strip():
        raise ValueError("approved_by is required — an approval must be attributable")
    path = course_root / APPROVALS_FILE
    try:
        doc = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, json.JSONDecodeError):
        doc = {}
    if not isinstance(doc, dict):
        doc = {}
    doc["schema_version"] = SCHEMA_VERSION
    packages = doc.setdefault("packages", {})
    packages[package_id] = {
        "fingerprint": fingerprint,
        "approved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "approved_by": approved_by,
    }
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
