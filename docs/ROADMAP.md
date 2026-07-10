# Canvas Toolbox API Roadmap

**Purpose:** Identify Canvas API capabilities not yet leveraged by canvas-toolbox and prioritize future tools based on instructor workflows.

---

## Current Coverage

### ✅ Heavily Used APIs
- **Assignments API** - assignment creation, updates, fetching
- **Assignment Overrides API** - student accommodations, late submissions, group overrides
- **Submissions API** - reading submission data, grading workflows
- **Quizzes API** - quiz time extensions, quiz-to-assignment mapping
- **Users API** - user lookups, enrollments
- **Courses API** - course metadata, roster management
- **Files API** - file uploads (submit_on_behalf)

### 🔶 Partially Used APIs
- **Grading API** - basic grading in mass regrading tools
- **Sections API** - used in enrollment/roster tools
- **Modules API** - minimal use (course structure awareness)

---

## Unexplored Canvas API Categories

### 📊 Analytics & Reporting

#### **Analytics API** ([docs](https://canvas.instructure.com/doc/api/analytics.html))
**Capabilities:**
- Student participation summaries (page views, assignments submitted, on-time rate)
- Course-level activity analytics
- Department/account-level analytics
- Per-assignment analytics (min/max/median scores, submission counts)

**Potential Tools:**
1. **Student engagement early warning system**
   - Flag students with low participation before they fall behind
   - Compare page views vs. assignment submissions
   - Identify students who view content but don't submit
   - Export: `docs/engagement_alerts.csv` (deid-safe)

2. **Assignment performance analyzer**
   - Show which assignments have lowest completion rates
   - Identify assignments with unusual score distributions
   - Compare assignment difficulty across sections
   - Suggest which assignments need better instructions

3. **Course health dashboard**
   - Weekly participation trends
   - Assignment submission velocity
   - Section performance comparison
   - Export: `docs/course_health_report.md`

**Priority:** HIGH - fills gap in current engagement audit tool

---

### 💬 Communication & Engagement

#### **Conversations API** ([docs](https://canvas.instructure.com/doc/api/conversations.html))
**Capabilities:**
- Send messages to individual students or groups
- Bulk messaging with recipient filters
- Message templates
- Conversation history

**Potential Tools:**
1. **Bulk assignment reminder sender**
   - Message all students missing specific assignment
   - Personalized reminder with assignment details
   - FERPA-safe: uses Canvas messaging (not email)
   - Example: `uv run python lib/tools/message_missing_assignment.py --assignment-id 12345 --template late_reminder`

2. **Accommodation notification tool**
   - Auto-message students when accommodations are applied
   - Explain what changed (due dates, time limits)
   - Include Canvas links to affected assignments
   - Integrates with student_late_accommodation.py

3. **Grade release announcer**
   - Notify students when batch grading is complete
   - Personalized feedback summaries
   - Link to SpeedGrader for detailed comments

**Priority:** MEDIUM - useful but requires careful FERPA handling

---

#### **Discussion Topics API** ([docs](https://canvas.instructure.com/doc/api/discussion_topics.html))
**Capabilities:**
- Create announcements programmatically
- Post discussion topics
- Read discussion participation
- Grade discussion posts

**Potential Tools:**
1. **Weekly announcement publisher**
   - Generate weekly course announcements from template
   - Include upcoming assignments, due dates, office hours
   - Auto-post on schedule (via cron)
   - Example: `uv run python lib/tools/post_weekly_announcement.py --week 3`

2. **Discussion participation audit**
   - Track which students haven't posted in required discussions
   - Export missing participation report (deid-safe)
   - Integrates with engagement early warning

**Priority:** LOW - announcements are easy to post manually, discussion grading is complex

---

### 📚 Content Management

#### **Modules API** ([docs](https://canvas.instructure.com/doc/api/modules.html))
**Capabilities:**
- List course modules and module items
- Update module requirements
- Publish/unpublish modules
- Reorder module items

**Potential Tools:**
1. **Module release scheduler**
   - Bulk publish modules on specific dates
   - Example: Publish week 2 module every Monday
   - JSON config: `course_schedule.json`

2. **Module structure validator**
   - Check that all modules follow same structure
   - Verify required items are present (syllabus, assignment, quiz)
   - Export: `docs/module_audit.md`

**Priority:** LOW - mostly one-time setup, manual is fine

---

#### **Pages API** ([docs](https://canvas.instructure.com/doc/api/pages.html))
**Capabilities:**
- Create/update course pages
- List all pages
- Publish/unpublish pages

**Potential Tools:**
1. **Page content updater**
   - Bulk update semester dates across all pages
   - Find/replace across course content
   - Example: Update "Spring 2026" → "Fall 2026"

**Priority:** LOW - content updates are infrequent

---

### 📝 Grading & Assessment

#### **Rubrics API** ([docs](https://canvas.instructure.com/doc/api/rubrics.html))
**Capabilities:**
- Create rubrics programmatically
- Associate rubrics with assignments
- Grade using rubric criteria

**Potential Tools:**
1. **Rubric template library**
   - Store rubric definitions as JSON
   - Apply standard rubrics to new assignments
   - Share rubrics across courses
   - Example: `uv run python lib/tools/apply_rubric.py --assignment-id 12345 --rubric discussion_post`

**Priority:** LOW - rubrics are typically reused, not recreated

---

#### **Outcomes API** ([docs](https://canvas.instructure.com/doc/api/outcomes.html))
**Capabilities:**
- Manage learning outcomes
- Align assignments to outcomes
- Track outcome achievement

**Potential Tools:**
1. **Outcome achievement tracker**
   - Export which students have mastered which outcomes
   - Identify struggling students by outcome gaps
   - Generate outcome reports for accreditation

**Priority:** VERY LOW - most courses don't use outcomes

---

#### **Grade Change Log API** ([docs](https://canvas.instructure.com/doc/api/grade_change_log.html))
**Capabilities:**
- Query grade change history
- Track who changed grades and when
- Audit trail for grading disputes

**Potential Tools:**
1. **Grading audit trail exporter**
   - Export all grade changes for a course
   - Filter by assignment, student, or date range
   - Useful for: grade disputes, TA oversight, accreditation

**Priority:** LOW - needed only for disputes

---

### 👥 Groups & Collaboration

#### **Groups API** ([docs](https://canvas.instructure.com/doc/api/groups.html))
**Capabilities:**
- Create group sets
- Assign students to groups
- Manage group memberships

**Potential Tools:**
1. **Random group generator**
   - Create balanced groups based on criteria
   - Avoid putting certain students together (from config)
   - Example: `uv run python lib/tools/create_groups.py --size 4 --count 10 --avoid-pairs avoid_list.csv`

2. **Group override manager**
   - Apply accommodations to entire group (extend due date)
   - Better UX than current fix_group_override_recalc.py
   - Example: `uv run python lib/tools/group_late_accommodation.py --group-id 123 --days 2`

**Priority:** MEDIUM - group management is tedious

---

### 📅 Calendar & Scheduling

#### **Calendar Events API** ([docs](https://canvas.instructure.com/doc/api/calendar_events.html))
**Capabilities:**
- Create calendar events
- Bulk schedule office hours, review sessions
- Delete outdated events

**Potential Tools:**
1. **Office hours scheduler**
   - Bulk create recurring office hours events
   - Example: Every Tuesday/Thursday 2-4pm for semester
   - JSON config: `office_hours_schedule.json`

**Priority:** LOW - calendar events are infrequent

---

## Feature Roadmap by Workflow Area

Features organized by instructor workflow rather than timeline. Build what solves your immediate problems.

**Legend:**
- ✅ Implemented
- ⭐ High user demand
- 🔧 Extends existing tool

---

### Student Accommodations & Support

Tools that directly support individual students with special circumstances (late enrollment, accommodations, grade forecasting).

1. **Student grade forecast** (Submissions API + Assignment Groups API) ⭐ HIGH DEMAND
   - Answers "what do I need to do to pass?" in office hours
   - Calculates current grade + remaining work scenarios
   - Shows priority assignments (highest impact on grade)
   - Copy-paste ready output for Slack/email
   - FERPA-safe lookup via deid code
   - Effort: Medium (gradebook calculations, accommodation-aware)

   **Usage:**
   ```bash
   # Default: what's needed to reach C- (70%)
   uv run python lib/tools/student_grade_forecast.py --deid-code S-95DBB6

   # Custom target: "I'm at a C, how do I get a B?"
   uv run python lib/tools/student_grade_forecast.py --deid-code S-95DBB6 --target-grade B

   # Include closed assignments (if willing to reopen via accommodations)
   uv run python lib/tools/student_grade_forecast.py --deid-code S-95DBB6 --waive-late
   ```

   **Features:**
   - Assignment group breakdown (weighted correctly)
   - Multiple passing scenarios (Option 1: 75% avg, Option 2: 85% challenges + 70% project)
   - Priority list (sorted by point value × weight)
   - Factors in student's existing accommodations (extended deadlines)
   - Still available vs closed assignments
   - Plain English output (human-readable, not technical)

2. ✅ **Global student exemption for late enrollment** (Submissions API) 🔧
   - Excuse student from all assignments due before enrollment date
   - Solves: "Student joined Week 5, I need to excuse them from Weeks 1-4 work"
   - One-time batch operation for single student
   - Effort: Low-Medium (uses Submissions API, date filtering)

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
   uv run python lib/tools/exempt_by_date.py --deid-code S-95DBB6 --before-week 5 --apply

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

3. **Group override manager** (Groups API + Overrides API) 🔧
   - Apply accommodations to entire group (extend due date)
   - Better UX than current fix_group_override_recalc.py
   - Frequently requested feature
   - Effort: Low (reuses existing override logic)

---

### Grading Workflow & TA Management

Tools that streamline grading operations and support teaching assistants.

1. **TA grading status & voice coaching** (Submissions API + AI analysis)
   - **Timeliness:** Track grading turnaround time — are students waiting too long for feedback?
   - **Quality:** Analyze TA feedback "voice" (tone, specificity, encouragement, actionability)
   - **Consistency:** Compare scoring patterns across students (flag grading drift/outliers)
   - **Intervention signal:** Alert instructor when TA falls behind and intervention needed
   - Generate coaching feedback for instructor to share with TA
   - Compare TA feedback against instructor examples
   - Export: FERPA-safe report (no student names, deid codes only)
   - Effort: Medium-High (AI analysis, voice coaching patterns, multi-TA comparison)

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

2. **Grading audit trail exporter** (Grade Change Log API)
   - Export all grade changes for a course
   - Filter by assignment, student, or date range
   - Useful for: grade disputes, TA oversight, accreditation
   - Effort: Low (straightforward API, CSV export)

---

### Course Analytics & Early Intervention

Tools that identify at-risk students and measure course effectiveness.

1. **Student engagement early warning system** (Analytics API) ⭐
   - Flag students with low participation before they fall behind
   - Compare page views vs. assignment submissions
   - Identify students who view content but don't submit
   - Export: FERPA-safe deid codes
   - Complements existing engagement audit
   - Effort: Medium (new API, but straightforward data fetching)

2. **Assignment performance analyzer** (Analytics API)
   - Show which assignments have lowest completion rates
   - Identify assignments with unusual score distributions
   - Compare assignment difficulty across sections
   - Suggest which assignments need better instructions
   - Data-driven course improvement
   - Effort: Medium (complex analytics, visualization)

---

### Course Setup & Infrastructure

Tools for course deployment, module management, and content organization.

1. **Course restoration from local repo** (Assignments API + Pages API + Modules API + Files API)
   - Deploy full course content from local repo to new Canvas course
   - Alternative to Canvas course copy (resilient to course deletion policy)
   - Solves: "Campus deletes old courses, I can't copy from last semester"
   - Useful for infrequent courses (taught once/year or less)
   - Effort: Medium (reuses canvas_sync infrastructure, needs full-course orchestration)

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

2. **Module release scheduler** (Modules API)
   - Bulk publish modules on specific dates
   - Example: Publish week 2 module every Monday
   - JSON config: `course_schedule.json`
   - Effort: Low (straightforward API, scheduling logic)

3. **Rubric template library** (Rubrics API)
   - Store rubric definitions as JSON
   - Apply standard rubrics to new assignments
   - Share rubrics across courses
   - Example: `uv run python lib/tools/apply_rubric.py --assignment-id 12345 --rubric discussion_post`
   - Effort: Low (rubrics are typically reused, not recreated)

4. **Random group generator** (Groups API)
   - Create balanced groups based on criteria
   - Avoid putting certain students together (from config)
   - Example: `uv run python lib/tools/create_groups.py --size 4 --count 10 --avoid-pairs avoid_list.csv`
   - Effort: Medium (group balancing logic)

---

### Communication & Automation

Tools for messaging students and automating repetitive communications.

1. **Bulk assignment reminder sender** (Conversations API)
   - Message all students missing specific assignment
   - Personalized reminder with assignment details
   - FERPA-safe: uses Canvas messaging (not email)
   - Integrates with existing accommodation tools
   - Effort: Medium (new API, FERPA considerations)

2. **Accommodation notification tool** (Conversations API + Overrides API) 🔧
   - Auto-message students when accommodations applied
   - Explain what changed (due dates, time limits)
   - Include Canvas links to affected assignments
   - Integrates with student_late_accommodation.py
   - Effort: Medium (integrates multiple tools)

3. **Weekly announcement publisher** (Discussion Topics API)
   - Generate weekly course announcements from template
   - Include upcoming assignments, due dates, office hours
   - Auto-post on schedule (via cron)
   - Template-based announcement generation
   - Effort: Medium (template engine, scheduling)

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
- **Worker:** `infra/voting-worker/` — stores votes in D1 database, returns counts
- **Aggregation:** `lib/tools/update_roadmap_votes.py` — updates this file with vote counts

See `infra/voting-worker/README.md` for deployment instructions (maintainer only).

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

---

## References

- Canvas API Documentation: https://canvas.instructure.com/doc/api/
- Instructure Developer Portal: https://developerdocs.instructure.com/services/canvas
- Canvas Community API Forum: https://community.canvaslms.com/t5/Developers-Group/bd-p/developers
- This toolbox's AGENTS.md: Project context and FERPA boundaries
