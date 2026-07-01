# Proposal: Audit Artifact for Iterative Course Improvement

**Status:** Accepted for implementation
**Date:** 2026-06-30
**Author:** Chaz Clark (based on research from @matjmiles in PR #125)
**Type:** Enhancement — structured audit findings artifact

> **Credit:** Problem identified by @matjmiles during redesign workflow dry-run. This proposal
> refines their RFC with semester-scale iterative improvement framing.

---

## Problem: No Progress Tracking Across Audit Iterations

Instructors improve courses **iteratively over 1-3 semesters**:

1. **Audit course** (Fall 2026) → identifies 32 missing rubrics, back-loaded workload, 2 CLO issues
2. **Fix subset** over the semester → add 10 rubrics, redistribute 3 assignments
3. **Re-audit** (Spring 2027) → progress check: now 22 missing rubrics, workload improved, CLOs still flagged
4. **Fix more** → add 10 more rubrics, revise CLOs
5. **Re-audit again** → validate improvements: 12 missing, CLOs meet criteria

**Current gap:**
- Each audit writes `audit.md` / `audit.pdf` → human-readable, not machine-comparable
- No way to **compare findings across iterations** without manually reading old reports
- Redesign workflows have no **validated baseline** — might use stale/wrong-course audit
- No **course-match guard** — agent could redesign course X using course Y's audit

---

## Solution: Structured Audit Artifact

Have `course_audit.py` **also** write `.canvas/audit/<course_id>.json` (gitignored) with structured findings.

### Use Cases

1. **Progress tracking** — compare `missing_rubrics: 32 → 22 → 12` across semesters
2. **Validated redesign baseline** — redesign workflows check course_id match + freshness before using audit data
3. **Cross-session continuity** — fresh agent session has access to last audit findings without re-reading `.md`

### Artifact Schema (v1)

```json
{
  "schema_version": 1,
  "course_id": "415492",
  "course_name": "Intro to Statistics",
  "run_at": "2026-06-30T17:10:00Z",
  "tier": "full",
  "verdict": "NEEDS_ATTENTION",
  "areas": {
    "rubric_coverage": {
      "verdict": "needs_attention",
      "missing": 32,
      "decorative": 1,
      "ok": 7,
      "total_assignments": 40
    },
    "rubric_quality": {
      "verdict": "review",
      "meets_criteria": 6,
      "partial": 2,
      "needs_revision": 0
    },
    "syllabus": {
      "verdict": "incomplete",
      "sections_present": "8/9",
      "missing": ["Disclaimers"]
    },
    "clo_quality": {
      "verdict": "meets_criteria",
      "clos": 4,
      "scope": "ideal"
    },
    "workload": {
      "verdict": "back_loaded",
      "peak_week": 14,
      "peak_hours": 18.5
    }
  },
  "top_fixes": [
    "32 assignments missing a rubric",
    "workload back-loaded (18.5 hours in week 14)",
    "syllabus: add Disclaimers section"
  ]
}
```

### Guards (Prevent Wrong-Course / Stale Audit Usage)

Before a redesign workflow uses `.canvas/audit/<course_id>.json`:

1. **Course match** — `course_id` in artifact matches target course (never redesign course X using course Y's audit)
2. **Freshness** — warn if `run_at` > 30 days old (semester-scale iteration; agent decides whether to re-audit)

If absent / mismatched / stale → run `course_audit.py` first.

---

## Implementation Plan

### 1. Modify `course_audit.py`

Add artifact persistence after existing `audit.md` / `.pdf` writes:

```python
def _write_artifact(course_id: str, findings: dict, output_dir: Path) -> None:
    """Write structured audit findings to .canvas/audit/<course_id>.json"""
    artifact_dir = output_dir / ".canvas" / "audit"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    artifact_path = artifact_dir / f"{course_id}.json"
    artifact_path.write_text(json.dumps(findings, indent=2), encoding="utf-8")
    print(f"  Audit artifact: {artifact_path}")
```

Call after audit completes:
```python
# Existing: write audit.md, audit.pdf
_write_artifact(course_id, structured_findings, output_dir)
```

**Backwards compatible** — existing outputs unchanged, artifact is additive.

### 2. Update Documentation

**`docs/course_design_workflow.md` — Flow A (Redesign):**

Add step A0:
> **A0. Validate audit baseline**
> Read `.canvas/audit/<course_id>.json`:
> - If absent → run `course_audit.py --full` first
> - If course_id mismatch → ERROR (never redesign course X using course Y's audit)
> - If run_at > 30 days → WARN "audit is stale, consider re-running"
> - If valid → use structured findings to inform CLO/assessment decisions

**`AGENTS.md` — Working Style:**

Add to existing knowledge-grounding rules:
> - Read `.canvas/audit/<course_id>.json` before redesign workflows to validate baseline (course match + freshness)
> - Compare findings across re-audits to track iterative improvement (`missing_rubrics: 32 → 22 → 12`)

### 3. FERPA / .gitignore

- `.canvas/` already gitignored (runtime dir)
- Artifact contains **structural findings only** (counts, verdicts, section names) — no student data
- `course_id` is course-specific metadata, stays in gitignored dir

### 4. Testing

Add to `lib/tests/test_course_audit.py`:
- `test_artifact_written_on_full_audit()` — verify `.canvas/audit/<course_id>.json` created
- `test_artifact_schema_matches_spec()` — validate JSON structure
- `test_artifact_course_id_match()` — verify course_id in artifact
- `test_per_course_keying()` — two courses don't clobber each other's artifacts

---

## Design Decisions

### Why per-course keying (`.canvas/audit/<course_id>.json`)?

Supports **multi-course repos** — each course gets its own artifact; no clobbering.

### Why 30-day freshness threshold?

**Semester-scale iteration** — instructors audit → fix over weeks → re-audit. 7 days is too short; 30 days matches academic calendar rhythm.

### Why not write per-CLO data?

**v1 scope:** Course-level verdicts + counts only. Per-CLO/per-assignment details add complexity; agents can re-run granular audits (`clo_quality_audit.py`) when needed.

### Why JSON, not YAML/TOML?

- Already gitignored (not human-edited)
- `course_audit.py` already emits `--json` flag
- Machine-readable, agent-parseable

---

## Success Criteria

1. **Iterative improvement tracking works** — instructor audits Fall 2026, fixes 10 rubrics, re-audits Spring 2027, sees `missing: 32 → 22`
2. **Course-match guard prevents errors** — agent redesigning course 415492 rejects artifact from course 415194
3. **Freshness warning guides re-audit** — 45-day-old artifact triggers "consider re-running audit" warning
4. **Backwards compatible** — existing workflows unchanged; artifact is additive

---

## Open Questions

1. **Should we version the schema?** (v1 includes `schema_version: 1` for future evolution)
2. **Should agents auto-compare across iterations?** (e.g., "missing rubrics improved from 32 to 22 since last audit")
3. **Should we expose this via a dedicated `--artifact` flag?** (or always write it silently)

---

## References

- Problem discovered by @matjmiles in PR #125 during redesign workflow dry-run
- Complements PR #124 (course design workflow guide) and PR #121 (agent routing)
- Fits `.canvas/` runtime artifact pattern (same as NGAI handoff files)

---

**Next Steps:**
1. Implement `_write_artifact()` in `course_audit.py`
2. Add tests validating artifact creation + schema
3. Update `course_design_workflow.md` and `AGENTS.md`
4. Document in CHANGELOG as enhancement
