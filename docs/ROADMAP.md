# Canvas Toolbox API Roadmap

**Purpose:** Identify Canvas API capabilities not yet leveraged by canvas-toolbox and prioritize future tools based on instructor workflows.

---

## Current Coverage

Refreshed 2026-09-23 by grepping actual `api/v1` endpoint usage across `lib/tools/`
(method: same approach as the create-vs-update sweep below — this section was last
accurate pre-#349 and had drifted well behind what's actually built).

### ✅ Heavily used (many tools, read + write)
Assignments · Assignment Overrides · Submissions · Quizzes (Classic) + Quiz Questions ·
Modules + Module Items · Pages · Discussion Topics/Announcements · Assignment Groups ·
Rubrics · Enrollments · Files/Folders (upload, #7) · Courses (metadata, settings, guard)

(Create support for Quiz/Assignment/Page/Discussion/Module/Assignment-Group shells
landed in #349–#351 via `canvas_shell_create.py`; this section previously listed
several of these as unexplored, which was stale as of that work and is now corrected.)

### 🔶 Partially used (one or two tools each — real but narrow)
Grading Standards (`grading_scheme_setup.py` only) · Late Policy (read + blueprint
propagation, no standalone editor) · Group Categories/Groups (read-only — `peer_review_assign.py`,
`grader_fetch.py`) · Outcomes/Outcome Groups (read + CLO import, no outcome-mastery
tracking) · Content Migrations/Exports (`.imscc` + course clone) · Calendar Events
(read-only, one tool) · Custom Gradebook Columns (read-only, one tool) · Sections
(roster/enrollment tools) · Feature Flags (read-only — one gate check)

### ⛔ Never touched (zero tools, zero read-only usage)
Conversations · Analytics · Grade Change Log · Gradebook History · Usage Rights ·
Media Objects · Planner · Appointment Groups · Collaborations · External Tools (LTI) ·
Moderated Grading · Content Shares · Bookmarks · Polls · SIS Import · Developer Keys ·
Account Reports · Accounts · Roles · Terms of Service

---

## ✅ Shipped: create vs. update parity (#349–#351)

`canvas_sync.py --push` used to only ever `PUT`: every `_push_*` function required a
`canvas_id`/`page_url` already in `.canvas/index.json` and refused otherwise. #349/#350
closed this for quiz/assignment shells; a follow-up sweep (2026-09-23) found the
identical gap in 4 more object types and #351 closed those too. `canvas_shell_create.py`
now covers all six: `quiz`, `assignment`, `page`, `discussion`, `module`,
`assignment_group` — unpublished create, read-back verification, idempotent by exact
title, `canvas_course_guard`-gated.

New Quiz creation stays excluded deliberately (LTI-delivered, no content/settings write
support via the API at all — a platform ceiling, not a toolkit gap). File upload (#7)
already closed the same shape of gap for Canvas Files.

Sweep write-up and sandbox verification notes: `handoffs/parkinglot.md` ("Create-vs-update
gap sweep") and `CHANGELOG.md` [Unreleased]. Caught along the way: Canvas's Assignment
Groups API rejects the wrapped-payload convention every other object type here
accepts — documented as **L27** in `canvas_api_lessons_learned.md`, and fixed in
`sync_to_new.py`'s pre-existing, previously-untested `create_assignment_group()`.

---

## API capability audit — ranked (2026-09-23)

Spun off from the create-vs-update sweep above (parked as its own idea in
`handoffs/parkinglot.md`, "Full Canvas API capability audit"). That sweep was narrow
by design — one pattern (create missing, update exists) across 6 object types. This
is the broader question: across the *entire* Canvas API, what has canvas-toolbox
never built tooling for at all, and is it worth building?

**Method:** grepped every `api/v1` endpoint path actually constructed in `lib/tools/`,
normalized and de-duplicated (see the Current Coverage section above for the result),
then checked the remaining API categories against this toolkit's real usage patterns
— FERPA-safe grading, student accommodations, instructional-design audits, course
building — rather than generic "what could an LMS API do" brainstorming. That's the
main defect in the section this replaces: most of its "potential tools" were plausible
in the abstract but not grounded in what this toolkit's actual operators ask for.

### Tier 1 — worth scoping next

**Conversations API** ([docs](https://canvas.instructure.com/doc/api/conversations.html)).
Zero tooling today. The clearest gap: every accommodation tool in `skills/accommodations/`
(late grace, time extensions, exemptions) silently changes what a student sees in
Canvas with no notification path — the instructor tells the student by hand, outside
the toolkit, or not at all. A `--notify` flag on the existing accommodation tools
(or a small shared `canvas_conversations.py` helper) that sends a Canvas message when
an accommodation is applied closes a real loop this toolkit already opened. FERPA
discipline applies exactly as it does to grading comments — draft in the student's
voice, never bulk-blast, log what was sent.

**Grade Change Log API** ([docs](https://canvas.instructure.com/doc/api/grade_change_log.html))
and **Gradebook History API** ([docs](https://canvas.instructure.com/doc/api/gradebook_history.html)).
Zero tooling today. Directly serves an already-real workflow: `grader_audit_workflow.py`
and the HG-5 review gate exist because grade disputes and TA-oversight questions
("who changed this and when") are a recurring category of instructor ask in a
TA-managed course. Right now that question has no toolkit answer at all — the
instructor goes into Canvas's UI grade-history view by hand. A read-only export
(deid-safe, same convention as every other audit) is a small, contained build.

### Tier 2 — real, but scope before building

**Analytics API** ([docs](https://canvas.instructure.com/doc/api/analytics.html)).
Zero tooling today, but overlaps meaningfully with what `course_engagement_audit.py`
already does by fetching submissions/discussions directly for Title IV engagement
classification. Worth a scoping pass on what Analytics adds (page-view data, per-
assignment score distributions) that the existing tool can't get more cheaply before
building anything new — building this without that check risks a second tool doing
half of what the first one does.

**External Tools (LTI) API** ([docs](https://canvas.instructure.com/doc/api/external_tools.html)).
Zero tooling today. `course_audit.py`/`course_quality_check.py` already flag New-Quiz
LTI assignments as a walled-off write case (documented in
`canvas_api_lessons_learned.md`); a read-only "what LTI tools are installed and does
this course lean on any with known write-support gaps" audit generalizes that one
documented lesson into a proactive check instead of a per-incident discovery.

**Usage Rights API** ([docs](https://canvas.instructure.com/doc/api/files.html#method.usage_rights.set_usage_rights)).
Zero tooling today. Copyright/accessibility compliance for uploaded course files is
adjacent to what `accessibility_audit.py` already checks — worth folding into that
audit's scope (flag files with no usage-rights license set) rather than a standalone
tool.

### Tier 3 — real capability, low fit for this toolkit's operators

Groups API (group creation/assignment — `peer_review_assign.py`/`grader_fetch.py`
already read group membership for the workflows that need it; bulk group *creation*
is a one-time per-semester task most instructors do fine in the UI). Calendar Events
(infrequent, low pain). Planner API, Appointment Groups, Collaborations, Media
Objects, Moderated Grading, Content Shares, Bookmarks, Polls — each real, none matches
a recurring ask from this toolkit's actual operators (instructors/instructional
designers doing course-design and FERPA-safe grading work, not office-hours
scheduling or collaborative-doc management).

### Out of scope — admin/account-level, not instructor-facing

SIS Import, Developer Keys, Account Reports, Accounts API, Roles, Terms of Service.
These require account-admin permissions most instructors using this toolkit don't
have, and sit outside "things an instructor does to their own course" — the same
reasoning that already excludes New Quiz content writes (a platform permission
ceiling) and full LTI tool management (an account-admin surface, distinct from the
read-only per-course audit in Tier 2 above).

---

## Feature Roadmap by Workflow Area

Features organized by instructor workflow rather than timeline. Build what solves your immediate problems.

**Legend:**
- ✅ Implemented
- ⭐ High user demand
- 🔧 Extends existing tool

**T-shirt sizes (implementation effort):**
- **XS** = 1-2 days (simple API wrapper, existing patterns)
- **S** = 3-5 days (straightforward feature, minimal new concepts)
- **M** = 1-2 weeks (moderate complexity, new API integration)
- **L** = 2-4 weeks (complex logic, multiple APIs, significant integration)
- **XL** = 1-2 months (very complex, new paradigms, extensive testing)

---

### Planning Summary — Features by Size

**Quick wins (XS — 1-2 days each):**
- Grading audit trail exporter

**Small features (S — 3-5 days each):**
- ✅ Global student exemption (completed)
- Group override manager
- Module release scheduler
- Rubric template library

**Medium features (M — 1-2 weeks each):**
- Student engagement early warning system ⭐
- Assignment performance analyzer
- Random group generator
- Bulk assignment reminder sender
- Accommodation notification tool
- Weekly announcement publisher

**Large features (L — 2-4 weeks each):**
- Student grade forecast ⭐
- Course restoration from local repo

**Extra large features (XL — 4-6 weeks each):**
- TA grading status & voice coaching

**Suggested sprint planning:**
- Sprint 1 (1 week): Grading audit trail exporter (XS) + Group override manager (S)
- Sprint 2 (1 week): Module release scheduler (S) + Rubric template library (S)
- Sprint 3 (2 weeks): Student engagement early warning system (M) ⭐
- Sprint 4 (3 weeks): Student grade forecast (L) ⭐
- Sprint 5+: Choose based on demand and strategic fit

---

### Student Accommodations & Support

Tools that directly support individual students with special circumstances (late enrollment, accommodations, grade forecasting).

1. **Student grade forecast** — **L** (2-3 weeks) ⭐
   - Answers "what do I need to do to pass?" in office hours
   - Calculates current grade + remaining work scenarios
   - Shows priority assignments (highest impact on grade)
   - Copy-paste ready output for Slack/email
   - FERPA-safe lookup via deid code
   - **Complexity:** Gradebook calculation logic, weighted assignment groups, multiple scenario generation, accommodation-aware filtering

   **Usage:**
   ```bash
   # Default: what's needed to reach C- (70%)
   uv run python lib/tools/student_grade_forecast.py --deid-code S-68BC40

   # Custom target: "I'm at a C, how do I get a B?"
   uv run python lib/tools/student_grade_forecast.py --deid-code S-68BC40 --target-grade B

   # Include closed assignments (if willing to reopen via accommodations)
   uv run python lib/tools/student_grade_forecast.py --deid-code S-68BC40 --waive-late
   ```

   **Features:**
   - Assignment group breakdown (weighted correctly)
   - Multiple passing scenarios (Option 1: 75% avg, Option 2: 85% challenges + 70% project)
   - Priority list (sorted by point value × weight)
   - Factors in student's existing accommodations (extended deadlines)
   - Still available vs closed assignments
   - Plain English output (human-readable, not technical)

2. ✅ **Global student exemption for late enrollment** — **S** (completed) 🔧
   - Excuse student from all assignments due before enrollment date
   - Solves: "Student joined Week 5, I need to excuse them from Weeks 1-4 work"
   - One-time batch operation for single student
   - **Complexity:** Submissions API filtering, date logic, dry-run pattern

   **Use case:**
   Student enrolls mid-semester. Instead of manually marking each assignment as "EX" (excused) in the gradebook, run one command to excuse all assignments due before their enrollment date.

   **Canvas behavior:**
   "Excused" (shown as "EX" in gradebook) means the assignment doesn't count toward grade calculation, maximum points are reduced, and Canvas treats it like the assignment doesn't exist for that student. Note: "excused" and "exempt" are the same thing in Canvas — just different terminology for the same status.

   **Usage:**
   ```bash
   # Excuse student from assignments before date (dry-run preview)
   uv run python lib/tools/exempt_by_date.py --user-id 123456 --before-date 2026-02-15

   # Apply: excuse student from assignments before date
   uv run python lib/tools/exempt_by_date.py --user-id 123456 --before-date 2026-02-15 --apply

   # Excuse by week number (before Week 5 = excuse Weeks 1-4)
   uv run python lib/tools/exempt_by_date.py --user-id 123456 --before-week 5 --apply

   # Use deid-code instead of user-id (FERPA-safe)
   uv run python lib/tools/exempt_by_date.py --deid-code S-68BC40 --before-week 5 --apply

   # Undo: remove excused status from all previously excused assignments
   uv run python lib/tools/exempt_by_date.py --user-id 123456 --undo --apply
   ```

   **Features:**
   - Finds all published assignments with due dates (assignments, quizzes, discussions)
   - Filters by due date (before enrollment date or before specific week)
   - Marks submissions as excused via Canvas Submissions API
   - **One-time run per student** (not a recurring sync)
   - FERPA-safe: uses user_id or deid-code (never displays names)
   - Dry-run default (requires `--apply` to actually write)
   - Shows what will be excused before applying

   **Workflow:**
   1. Student enrolls late (e.g., Week 5 of semester)
   2. Instructor runs: `exempt_by_date.py --user-id <id> --before-week 5 --apply`
   3. All assignments due in Weeks 1-4 marked as "EX" (excused) in gradebook
   4. Grade calculation excludes excused assignments automatically
   5. If needed, use `--undo --apply` to reverse the exemptions

3. **Group override manager** — **S** (3-5 days) 🔧
   - Apply accommodations to entire group (extend due date)
   - Better UX than current fix_group_override_recalc.py
   - Frequently requested feature
   - **Complexity:** Reuses existing override patterns, familiar APIs, straightforward UX improvement

---

### Grading Workflow & TA Management

Tools that streamline grading operations and support teaching assistants.

1. **TA grading status & voice coaching** — **XL** (4-6 weeks)
   - **Timeliness:** Track grading turnaround time — are students waiting too long for feedback?
   - **Quality:** Analyze TA feedback "voice" (tone, specificity, encouragement, actionability)
   - **Consistency:** Compare scoring patterns across students (flag grading drift/outliers)
   - **Intervention signal:** Alert instructor when TA falls behind and intervention needed
   - Generate coaching feedback for instructor to share with TA
   - Compare TA feedback against instructor examples
   - Export: FERPA-safe report (no student names, deid codes only)
   - **Complexity:** AI text analysis, multi-dimensional reporting (timeliness/quality/consistency), statistical analysis, multi-TA comparison logic, coaching feedback generation

   **Usage:**
   ```bash
   # Check TA grading status for a specific assignment
   uv run python lib/tools/ta_status.py --assignment-id 12345 --ta-user-id 98765

   # Analyze TA feedback voice across all assignments
   uv run python lib/tools/ta_status.py --ta-user-id 98765 --voice-analysis

   # Compare multiple TAs for consistency
   uv run python lib/tools/ta_status.py --compare-tas --ta-user-ids 98765,98766,98767

   # Check if instructor intervention needed (grading backlog)
   uv run python lib/tools/ta_status.py --intervention-check
   ```

   **Features:**
   - **Timeliness dashboard:**
     - Average turnaround time (submission → feedback)
     - Submissions waiting >48 hours (intervention threshold)
     - Grading velocity trend (improving or declining?)
     - Projected completion date for current backlog
     - **Alert:** "⚠ 12 students waiting >5 days — instructor step-in recommended"
   - **Quality analysis:**
     - Tone: encouraging/critical, specific/vague, actionable/generic
     - Length: comment word count distribution
     - Rubric usage: % of submissions with rubric scores
     - Coaching: "TA feedback averages 1.2 sentences — encourage specificity"
   - **Consistency check:**
     - Score variance across similar submissions (flag outliers)
     - Compare against instructor's grading on same assignment
     - Identify grading drift (early submissions vs late submissions)
   - Uses existing grading infrastructure (grading/, .deid_master.csv)
   - AI analysis via existing coaching knowledge files
   - Plain English output: copy-paste ready for TA feedback meeting

   **Future enhancements (v2 or separate tool):**
   - Cross-assignment consistency (same TA over time)
   - Inter-rater reliability (multiple TAs on same assignment)
   - TA feedback template library (approved phrases for common issues)

2. **Grading audit trail exporter** — **XS** (1-2 days)
   - Export all grade changes for a course
   - Filter by assignment, student, or date range
   - Useful for: grade disputes, TA oversight, accreditation
   - **Complexity:** Simple API read, CSV export (existing pattern), basic filtering

3. **AI conversation grader — engagement-mode scoring (mirror aimodes.ai)** — **L** (2-3 weeks) ⭐
   - **Model to reverse-engineer:** [aimodes.ai](https://aimodes.ai/) — Dr. Mark Keith's (BYU Information Systems) research instrument that classifies *how* a user engages with an AI assistant. Goal: make our AI Log grading mirror its framework and outputs as closely as possible.
   - **The framework — 8 engagement modes across 3 agency tiers (Passivity → Partnership → Agency):**
     - *Passivity:* Oracle, Production Assistant
     - *Partnership:* Tutor, Collaborative Problem-Solver
     - *Agency:* Verification Agent, Creative Expander, Critical Challenger, Problem Setter
   - **Scoring to reproduce:** per-message classification into the 8 modes → tier distribution (% across the 3 agency levels) → overall intellectual-agency score (/100) → mode distribution (actual vs. target %) → student archetype (Delegator, Partner, Challenger, Explorer, Specialist, Learner) → personalized strengths / growth areas.
   - **Builds on what exists:** `grader_follow_share_url.py` already fetches the transcript behind `chatgpt.com/share` + Gemini share URLs (issue #51); today's per-turn-mixture classifier gives only a coarse verdict ("classified" / "unable to classify"). Replace/augment it with the 8-mode / 3-tier classifier so an AI Log earns a research-grounded engagement score.
   - **Faculty value:** grade the *quality* of a student's AI interaction (delegating vs. verifying/challenging) on a defensible, published rubric — exactly what permissive-AI-policy courses (m119, DS250) need to assess AI Log assignments.
   - **Open questions:** aimodes.ai is a closed research tool — reverse-engineer the mode definitions + scoring from its public outputs; reach out to Dr. Keith on whether the rubric/prompts can be cited or shared (BYU-adjacent, so plausibly collaborative). Keep it FERPA-safe — run on de-identified transcripts inside the existing `grading/` pipeline.
   - **Complexity:** LLM per-message classification against the 8-mode taxonomy, tier aggregation + scoring math, archetype mapping, prompt/rubric engineering to match aimodes' outputs, integration into the deid grader chain.

---

### Course Analytics & Early Intervention

Tools that identify at-risk students and measure course effectiveness.

1. **Student engagement early warning system** — **M** (1-2 weeks) ⭐
   - Flag students with low participation before they fall behind
   - Compare page views vs. assignment submissions
   - Identify students who view content but don't submit
   - Export: FERPA-safe deid codes
   - Complements existing engagement audit
   - **Complexity:** New Analytics API, threshold logic, FERPA-safe export, integration with existing engagement audit

2. **Assignment performance analyzer** — **M** (1-2 weeks)
   - Show which assignments have lowest completion rates
   - Identify assignments with unusual score distributions
   - Compare assignment difficulty across sections
   - Suggest which assignments need better instructions
   - Data-driven course improvement
   - **Complexity:** Analytics API (same as above), statistical analysis, visualization/reporting generation

---

### Course Setup & Infrastructure

Tools for course deployment, module management, and content organization.

1. **Course restoration from local repo** — **L** (3-4 weeks), MVP: **M** (1-2 weeks)
   - Deploy full course content from local repo to new Canvas course
   - Alternative to Canvas course copy (resilient to course deletion policy)
   - Solves: "Campus deletes old courses, I can't copy from last semester"
   - Useful for infrequent courses (taught once/year or less)
   - **Implementation:** Reverse sync (API-by-API recreation), not IMSCC import
   - **Complexity:** Multiple APIs (Assignments, Pages, Modules, Files), orchestration logic, validation & safety checks, idempotent updates, dependency ordering
   - **Advantage:** Reuses 80% of existing canvas_sync infrastructure, selective restore capability, transparent errors
   - **See:** `docs/implementation/sync_to_new.md` for detailed implementation plan

   **Use case:**
   Instructor maintains course content in local repo (assignments, pages, modules).
   Next semester: create new Canvas course, update `.env` with new course ID, run restore.
   All content deploys to new course without needing previous semester's Canvas course.

   **Usage:**
   ```bash
   # Deploy entire course from local repo to new Canvas course
   uv run python lib/tools/course_restore.py --apply

   # Preview what would be created (dry-run)
   uv run python lib/tools/course_restore.py

   # Deploy specific content types only
   uv run python lib/tools/course_restore.py --assignments --pages --apply
   ```

   **Features:**
   - Deploys assignments, pages, modules, module structure, files
   - Preserves module prerequisites and completion requirements
   - FERPA-safe (no student data in repo)
   - Idempotent (can re-run to update course)
   - Guards against overwriting live courses (requires confirmation)
   - Validation: checks for required fields, broken links, missing files

   **Workflow:**
   1. Maintain course content in `course/` directory (git-tracked)
   2. Create new Canvas course each semester
   3. Update `CANVAS_COURSE_ID` in `.env`
   4. Run `course_restore.py --apply`
   5. Course populated in ~2-5 minutes (depending on content size)

2. **Module release scheduler** — **S** (3-5 days)
   - Bulk publish modules on specific dates
   - Example: Publish week 2 module every Monday
   - JSON config: `course_schedule.json`
   - **Complexity:** Simple Modules API, JSON config parsing, date/scheduling logic

3. **Rubric template library** — **S** (3-5 days)
   - Store rubric definitions as JSON
   - Apply standard rubrics to new assignments
   - Share rubrics across courses
   - Example: `uv run python lib/tools/apply_rubric.py --assignment-id 12345 --rubric discussion_post`
   - **Complexity:** Rubrics API (straightforward), JSON template storage, association logic

4. **Random group generator** — **M** (1 week)
   - Create balanced groups based on criteria
   - Avoid putting certain students together (from config)
   - Example: `uv run python lib/tools/create_groups.py --size 4 --count 10 --avoid-pairs avoid_list.csv`
   - **Complexity:** Groups API, balancing algorithms, constraint handling (avoid-pairs logic)

---

### Communication & Automation

Tools for messaging students and automating repetitive communications.

1. **Bulk assignment reminder sender** — **M** (1-2 weeks)
   - Message all students missing specific assignment
   - Personalized reminder with assignment details
   - FERPA-safe: uses Canvas messaging (not email)
   - Integrates with existing accommodation tools
   - **Complexity:** New Conversations API, template system, FERPA considerations, filtering logic

2. **Accommodation notification tool** — **M** (1-2 weeks) 🔧
   - Auto-message students when accommodations applied
   - Explain what changed (due dates, time limits)
   - Include Canvas links to affected assignments
   - Integrates with student_late_accommodation.py
   - **Complexity:** Conversations API, integration with existing accommodation tools, message templating

3. **Weekly announcement publisher** — **M** (1-2 weeks)
   - Generate weekly course announcements from template
   - Include upcoming assignments, due dates, office hours
   - Auto-post on schedule (via cron)
   - Template-based announcement generation
   - **Complexity:** Discussion Topics API, template engine, scheduling (cron), dynamic content generation

---

## API Research Notes

### Canvas API Design Patterns We've Learned

1. **Pagination is mandatory** - Most list endpoints paginate (per_page=100, page=N)
2. **Bulk operations are rare** - Canvas prefers granular API calls (except bulk_update)
3. **Permissions vary by institution** - BYUI blocks "submit on behalf" (submit_on_behalf.py)
4. **Rate limiting exists** - 429 errors require exponential backoff (_override_recalc_helper.py)
5. **Canvas caching issues** - PUT doesn't always return updated data (Issue #1774)

### Canvas API Limitations We've Hit

1. **No bulk recalculation endpoint** - Must "touch" overrides individually
2. **No batch submission creation** - submit_on_behalf blocked at institutional level
3. **Include parameters are inconsistent** - Some endpoints support include[], others don't
4. **No schema validation** - Canvas accepts invalid dates, silently fails
5. **Payload wrapping is per-endpoint, not a platform convention** - most object-creation
   endpoints want a wrapped body (`{"assignment": {...}}`), but Assignment Groups and
   Discussion Topics want it flat, and a wrapped POST to those two returns `200` while
   silently ignoring every field. Verify per endpoint on a sandbox; don't assume the
   convention generalizes (L27, `canvas_api_lessons_learned.md`).

---

## Voting & Prioritization

This roadmap is community-driven. **Vote for features** to help prioritize development.

### How to vote

```bash
# List all roadmap features with current vote counts
uv run python lib/tools/vote_feature.py --list

# Vote for a feature by name
uv run python lib/tools/vote_feature.py --feature "student grade forecast"

# Vote using feature ID (recommended — unambiguous)
uv run python lib/tools/vote_feature.py --feature-id grade-forecast
```

Votes are:
- **Anonymous** (uses a hashed machine ID for deduplication)
- **No GitHub account required**
- **Idempotent** (voting again for the same feature returns current count)
- **Rate-limited** (10 votes per IP per hour to prevent spam)

### Voting through AI agents

AI agents working in canvas-toolbox repos detect when you express interest in roadmap features and offer to vote on your behalf. Just mention the feature you want and the agent will ask if you'd like to vote for it.

Example:
> User: "I often get asked by students what they need to pass the class"
>
> Agent: "That's roadmap item #1: 'Student grade forecast' (Phase 1, HIGH DEMAND). Would you like me to vote for this feature to signal demand?"

### How voting affects prioritization

Vote counts appear in this roadmap (updated manually or via GitHub Actions). The maintainer uses votes as one signal (alongside institutional adoption, implementation complexity, and strategic fit) when deciding what to build next. High-vote features may move up in priority or get built sooner.

### Voting infrastructure

- **CLI tool:** `lib/tools/vote_feature.py` — posts votes to Cloudflare Worker
- **Worker:** `edge-infra/workers/voting-worker/` — stores votes in D1 database, returns counts
- **Aggregation:** `lib/tools/update_roadmap_votes.py` — updates this file with vote counts

See `edge-infra/workers/voting-worker/README.md` for deployment instructions (maintainer only).

---

## Contributing

If you build a tool for one of these API categories:
1. Add it to `lib/tools/` with descriptive docstring
2. Update this roadmap (move from roadmap to "Current Coverage")
3. Add usage examples to README
4. Document any institutional permission requirements
5. Add FERPA discipline if handling student data

---

## Design Philosophy Notes — Odysseus Research (2026-07-09)

**Context:** Research from PewDiePie's Odysseus project (self-hosted AI workspace, 78k+ GitHub stars). Lessons for canvas-toolbox packaging and integration strategy.

### Key insights worth considering

**1. Packaging over features**
- Odysseus bundled existing tools (Ollama, MCP, n8n workflows) into one cohesive product
- Innovation was **putting components in one box**, not inventing new capabilities
- One Docker command vs "clone 4 repos and wire them yourself"
- **For canvas-toolbox:** Voting system, MCP servers, grading pipeline exist separately - consider tighter integration or unified installer?

**2. Hardware-aware defaults ("Cookbook" concept)**
- 270+ AI models with recommendations based on actual machine specs
- Prevents "download 70B model, get 4 tokens/sec" trap (capacity ≠ speed)
- **For canvas-toolbox:** Could detect hardware and warn about Rust compilation requirements? Recommend Python fallback for engagement audit if no Cargo?

**3. Opinionated but flexible**
- Ships with defaults that work out of box
- But allows pointing at any endpoint/service
- **For canvas-toolbox:** Already doing this well (.env + sandbox guards). Keep it.

**4. Product posture, not research artifact**
- README reads like product landing page
- Looks like something ordinary users would want to open
- **For canvas-toolbox:** README already strong. Could onboarding be even smoother? Consider guided setup mode?

**5. Privacy-explicit, local-first**
- "No telemetry" stated plainly at top of docs
- **For canvas-toolbox:** Already implements (FERPA zones, no cloud by default). Make this more prominent in marketing?

### The "bandwidth wall" lesson (critical for self-hosted AI)

**The trap Odysseus hit:**
- Removed setup friction → removed learning period → users hit hardware limits unprepared
- 78k stars ≠ 78k successful deployments
- Users download huge models that **load** but run at 4 tok/sec (unusable)

**Parallel for canvas-toolbox:**
- Grading safety gates = "read the model cookbook before you download"
- They protect users from themselves (e.g., "push zeros to 400 students")
- Keep gates visible. Don't abstract them away for convenience.

**Real-world AI setup (from article author):**
- Qwen 27B (4-bit quant) on 36GB Mac - boring but responsive
- Still uses paid APIs for hard tasks - cloud spend down 50%, **not zero**
- This is the honest model: local for bulk, cloud for complexity

### Potential future work (not roadmap items yet — needs design)

- **Unified installer:** One command setup for .env, deps, Canvas connection verification
  - But don't remove learning - maybe `--guided` mode that explains each step?
  - See: docs/research/odysseus-2026-07-09.md for full analysis

- **Hardware detection for Rust tools:**
  - Detect Cargo before recommending engagement_audit_rs
  - Graceful fallback to Python with speed note

- **"Batteries included" Docker Compose:**
  - Optional docker-compose.yml that includes voting worker + MCP bridge + grading pipeline
  - Opt-out not opt-in (Odysseus model)

- **Packaging narrative emphasis:**
  - Canvas API tools existed forever, AI grading knowledge existed forever
  - canvas-toolbox innovation is **packaging with safety gates and FERPA boundaries**
  - Same story as Odysseus - components existed, nobody made them work together for instructors

**Filed:** 2026-07-09. See `docs/research/odysseus-2026-07-09.md` for detailed research notes.

- **Catalog CLO importer (API-only write):** with explicit permission, look up a
  course's catalog Course Learning Outcomes and add them into the Canvas course
  via a script.
  - **API-only, by nature.** Outcomes are account/catalog-level and are NOT in a
    content export (`learning_outcomes.xml` is empty in a `.imscc`), so there is
    no offline path — this is a live write that must go through the API. It's the
    complement to the offline-mode work: offline covers read/report + content
    date-shift; this fills the outcomes gap online.
  - Design notes: needs a permission gate (writes course outcomes), a catalog
    source (where do the catalog CLOs live — SIS? a maintained mapping?), and
    idempotency (don't duplicate outcomes on re-run). Pairs with
    `clo_quality_audit` (which stays API-only for the same reason).
  - **Testing bonus:** it would let us seed outcomes into the sandbox (427808)
    and finally exercise the outcomes path end-to-end (`clo_quality_audit`) —
    coverage we can't get from a `.imscc` export (outcomes are absent there).
  - **Reuse:** `syllabus_outcomes.extract_outcomes(html)` already parses CLOs out
    of any HTML (used by syllabus_audit + rubric_quality) — so the parse step is
    solved; the open question is the SOURCE.
  - **✅ SHIPPED (2026-07-12): `lib/tools/clo_catalog_import.py`.** The confirmed
    source is the institution's **Kuali public catalog API** (`<institution>.kuali.co`),
    not a general websearch. BYUI's per-course `outcomes` field is already structured
    `[{id, value}]` — no HTML scraping needed. Endpoints:
    `/api/v1/catalog/public/catalogs/` (list) → `/catalog/courses/<catalogId>`
    (index; match `__catalogCourseId`) → `/catalog/course/<catalogId>/<pid>`
    (detail, `.outcomes`). The earlier "feasibility not confirmed" note was a
    general-websearch dead-end — the vendor API is the real source (BYU/BYUI/BYUH
    each have their own `*.kuali.co`, so institution scoping still matters).
  - **Design as built:** read-only preview by default (`--write` required to touch
    Canvas); `canvas_course_guard.enforce(mode="write")` refuses enrolled/blueprint
    courses unless `--allow-enrolled`; idempotent (skips outcomes whose title already
    exists); `--institution` / `--catalog-host` / `--catalog` keep it institution-
    agnostic within Kuali catalogs. Each CLO → one Canvas Outcome (`<CODE> CLO <n>`,
    description = the CLO text).
  - **Verified live (2026-07-12):** DS250 / MATH119 / ITM327 / DS460 all resolve in
    the 2026-27 catalog; DS250's 5 CLOs written into sandbox 427808, read back
    independently, re-run idempotent (0 created / 5 skipped). The outcomes path is
    now exercisable end-to-end (feeds `clo_quality_audit`).
  - **Workflow — run this BEFORE the outcome audits.** `clo_quality_audit` and
    `course_alignment_audit` discover CLOs via `fetch_course_outcomes` → the
    **Canvas Outcomes API first** (`/courses/:id/outcome_group_links`), with the
    syllabus parser only as a fallback (they do NOT read CLOs from the rubric). So
    seed the outcomes with `clo_catalog_import` first, then audit — otherwise the
    audit runs `unverified` or guesses from the syllabus. Verified 2026-07-12:
    after seeding ITM327 (402262), `clo_quality_audit` found all 6 from Canvas
    (MEETS_CRITERIA). Seed the **master/blueprint** course (e.g. DS250 → 415094,
    ITM327 → 402262) so new courses *copied* from it inherit the outcomes (note:
    blueprint *sync* does not push outcomes to existing children — course copy does).
  - **Filed:** 2026-07-12 during offline-mode S7; shipped same day.

- **SAS accommodations LTI — bundle the API-only student-write tools into a Canvas LTI app.**
  Take the student-specific accommodation tools — `apply_sas_accommodations` (YAML dispatcher,
  4-tier classify, FERPA audit log), `student_late_accommodation` (submit-anything-late +
  `--shift-by-days` test-reschedule), `student_quiz_time_extension` (per-student classic-quiz
  time multiplier), and the candidates `exempt_by_date` + `submit_on_behalf` — and expose them
  through a **Canvas LTI 1.3 app** launched from inside a course, instead of the CLI.
  - **Why LTI, not offline:** these are inherently **API-only** — they act on per-student data
    (enrollments, per-student overrides / quiz extensions) that is NOT in a `.imscc` export, so
    offline mode can't cover them. That's the tool-boundary line: read/report → offline;
    per-student writes → API. An LTI is the right way to make them faculty-usable **without** a
    personal API token or the CLI: LTI Advantage (OIDC launch, Names-and-Roles for the roster,
    Assignment & Grade Services) handles auth + per-student targeting from inside Canvas.
  - **Shape:** LTI 1.3 tool (OIDC login → launch/deep-link), registered as a Canvas Developer
    Key; a small course-nav / assignment-level UI to pick a student + accommodation and apply it.
    Reuses the existing FERPA discipline + `canvas_course_guard` posture. The per-student writes
    map to the same Canvas overrides / quiz-extension endpoints the CLI already calls.
  - **Hosting:** natural fit for **`edge-infra`** (the Cloudflare sister repo) — an LTI tool is a
    small web service; Workers + KV/D1 can host the OIDC dance + state alongside the heartbeat /
    bug-intake workers.
  - **Payoff:** removes the CLI/token barrier for faculty on the accommodations that can't go
    offline; complements offline mode (which covers the read/report + content tools).
  - **Filed:** 2026-07-13 (parking lot).

---

## References

- Canvas API Documentation: https://canvas.instructure.com/doc/api/
- Instructure Developer Portal: https://developerdocs.instructure.com/services/canvas
- Canvas Community API Forum: https://community.canvaslms.com/t5/Developers-Group/bd-p/developers
- This toolbox's AGENTS.md: Project context and FERPA boundaries
