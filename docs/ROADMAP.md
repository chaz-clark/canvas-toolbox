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

## Prioritized Roadmap

### Phase 1: High-Value, Low-Complexity (Next 3 Months)

1. **Student engagement early warning system** (Analytics API)
   - Complements existing engagement audit
   - Identifies at-risk students before they fail
   - Export: FERPA-safe deid codes
   - Effort: Medium (new API, but straightforward data fetching)

2. **Bulk assignment reminder sender** (Conversations API)
   - Integrates with existing accommodation tools
   - Reduces manual messaging workload
   - Effort: Medium (new API, FERPA considerations)

3. **Group override manager** (Groups API + Overrides API)
   - Better UX than current fix_group_override_recalc.py
   - Frequently requested feature
   - Effort: Low (reuses existing override logic)

### Phase 2: Medium-Value, Moderate-Complexity (6-12 Months)

4. **Assignment performance analyzer** (Analytics API)
   - Helps identify assignments needing revision
   - Data-driven course improvement
   - Effort: Medium (complex analytics, visualization)

5. **Accommodation notification tool** (Conversations API + Overrides API)
   - Auto-notify students when accommodations applied
   - Reduces confusion about changed deadlines
   - Effort: Medium (integrates multiple tools)

6. **Weekly announcement publisher** (Discussion Topics API)
   - Template-based announcement generation
   - Saves time on repetitive weekly posts
   - Effort: Medium (template engine, scheduling)

### Phase 3: Nice-to-Have (Future)

7. **Module release scheduler** (Modules API)
8. **Rubric template library** (Rubrics API)
9. **Grading audit trail exporter** (Grade Change Log API)
10. **Random group generator** (Groups API)

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

## Contributing

If you build a tool for one of these API categories:
1. Add it to `lib/tools/` with descriptive docstring
2. Update this roadmap (move from roadmap to "Current Coverage")
3. Add usage examples to README
4. Document any institutional permission requirements
5. Add FERPA discipline if handling student data

---

## References

- Canvas API Documentation: https://canvas.instructure.com/doc/api/
- Instructure Developer Portal: https://developerdocs.instructure.com/services/canvas
- Canvas Community API Forum: https://community.canvaslms.com/t5/Developers-Group/bd-p/developers
- This toolbox's AGENTS.md: Project context and FERPA boundaries
