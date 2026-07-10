---
description: One-command pre-semester course health check
---

# Course Audit Tool

**What it does:** Comprehensive course health audit - checks rubrics, CLOs, syllabus completeness, and workload distribution in one command.

**Common usage:**
```bash
# Run full audit (rubrics + CLOs + syllabus + workload)
uv run python lib/tools/course_audit.py

# Audit with detailed output
uv run python lib/tools/course_audit.py --detailed

# Generate markdown report
uv run python lib/tools/course_audit.py --report audit_report.md

# Audit specific course
uv run python lib/tools/course_audit.py --course-id 123456
```

**What it checks:**
- **Rubric coverage:** Missing/decorative rubrics
- **Rubric quality:** Rating levels, process-oriented criteria, alignment
- **CLO quality:** Measurable outcomes, appropriate scope/rigor
- **Syllabus completeness:** Required sections, AI policy
- **Workload distribution:** Crunch weeks, front/back-loading

**Output:** Rolled-up verdict (HEALTHY / REVIEW / NEEDS_ATTENTION) + prioritized fix list

**Need help?** See [lib/tools/README.md](../../lib/tools/README.md#quality--audit-tools)

---

Would you like to run a course audit?
