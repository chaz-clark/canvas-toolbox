# Rust Value Proposition Analysis (Skeptical Review)

**Date:** 2026-07-06 (for morning 2026-07-07 review)
**Question:** Is adding Rust to canvas-toolbox worth the investment?

**Mindset:** Skeptical but open - prove the value with data, not assumptions.

---

## Current State: What We Know

### PR #136: Override Recalculation Rewrite
**Performance gain (actual):**
- Before: 5-10 minutes for 108 assignments (sequential API calls)
- After: 5-15 seconds (concurrent API calls)
- **Speedup: ~40-120x**

**Use case (actual):**
- Issue #135: M119 SP26 course (409936), 108 assignments
- Faculty applied accommodation for 1 student × 27 assignments
- Recalc tool scans ALL 108 assignments to find overrides
- Got stuck on assignment #6 for 5+ minutes before timeout

**Implementation (actual):**
- 312 lines Python (original) → 442 lines Rust + 176 lines Python wrapper
- Rust: tokio + reqwest (concurrent HTTP)
- Python: thin CLI wrapper, maintains same UX

---

## The Rust Investment Costs

### 1. Toolchain Size
- **Rust toolchain:** ~500MB (vs uv: ~20MB, Python: ~50MB)
- **Cargo cache:** ~50-200MB (grows with dependencies)
- **Build artifacts:** ~10-50MB per project
- **Total:** ~600-750MB per machine

### 2. Build Time
- **First build:** 30-60 seconds per project
- **Incremental builds:** 5-10 seconds (when changing code)
- **CI overhead:** +2-3 minutes first run, +30 sec cached

### 3. Developer Complexity
- **Two languages:** Python + Rust (agents need to know both)
- **Two package managers:** uv/pip + cargo
- **Compile errors:** Less readable than Python tracebacks
- **Cross-platform testing:** Need to verify builds on 3 OSes

### 4. User Friction
- **Installation:** Another ~500MB download + 2-5 min install
- **Build requirement:** `cargo build --release` before first use
- **Failure modes:** Compile errors, missing system deps (OpenSSL on Linux)
- **Windows:** Manual `.exe` installer (same as uv)

### 5. Maintenance Burden
- **Two implementations to maintain** (if we keep Python fallbacks)
- **Dependency updates:** Rust crates + Python packages
- **Security patches:** Both ecosystems
- **Documentation:** Explain both paths to users

---

## Potential Rust Rewrite Candidates

### Analysis Criteria
For each tool, assess:
1. **Actual usage frequency** (how often do users run this?)
2. **Actual performance problem** (do users complain it's slow?)
3. **Bottleneck location** (is it really HTTP? or Python logic?)
4. **Complexity of rewrite** (how hard to port to Rust?)
5. **Concurrent opportunity** (can we parallelize meaningfully?)

---

### Candidate 1: `fix_group_override_recalc.py` ✅ **DONE (PR #136)**

**Usage:** Medium - accommodation workflows, group override fixes
**Problem:** **YES** - 5-10 min for 108 assignments (issue #135)
**Bottleneck:** Sequential API calls (Python loop waiting for each response)
**Complexity:** Low - pure HTTP fetch/filter/PUT, no business logic
**Concurrency:** High - each assignment is independent, embarrassingly parallel
**Lines:** 312 Python → 442 Rust + 176 Python wrapper

**Verdict:** ✅ **Worth it** - proven 40-120x speedup, real user pain, clean separation

---

### Candidate 2: `grader_fetch.py` (1985 lines)

**What it does:**
- Fetches submissions for all students in an assignment
- Downloads attachments (GET /submissions, GET attachment URLs)
- Chains into deidentify + leak check

**Usage:** **Very high** - every grading run starts with this
**Current performance:** Unknown - no reported issues
**Bottleneck location:**
- API calls: GET /courses/:id/users (roster), GET /assignments/:aid/submissions (submissions), GET <attachment_url> (files)
- File I/O: Writing downloads to disk
- Chained tools: deidentify, leak check (subprocess calls)

**Question 1: Is it actually slow?**
- No open issues about grader_fetch being slow
- Users run it regularly, no complaints
- Likely fast enough for typical cohorts (20-40 students)

**Question 2: What would Rust improve?**
- Concurrent submission fetches (20-40 students → parallel HTTP)
- Concurrent attachment downloads (if multiple per student)
- **BUT:** File I/O and subprocess chains wouldn't benefit

**Question 3: Where's the real bottleneck?**
- Likely NOT grader_fetch itself
- Likely the DEIDENTIFY step (docx/pdf processing)
- Or the AI grading step (waiting for LLM API)

**Estimated gain:** 2-3x (not 40x like override recalc)
- Current: ~30 sec for 30 students (guess - no data)
- After: ~10-15 sec (parallel fetches)
- **Not user-facing pain** - 30 sec is acceptable

**Complexity:** Medium-high
- File downloads, directory management
- Subprocess orchestration (chaining)
- Business logic mixed with I/O

**Verdict:** ❌ **Not worth it** - no proven pain, modest gain, high complexity

---

### Candidate 3: `canvas_sync.py --pull` (1994 lines)

**What it does:**
- Pulls entire Canvas course to local files
- Modules, pages, assignments, quizzes, discussions, syllabus
- Hundreds of API calls for large courses

**Usage:** Medium - course design workflows, one-time pulls
**Current performance:** Unknown - no reported issues
**Bottleneck:** Potentially sequential API calls for large module structures

**Question 1: Is it actually slow?**
- No open issues
- Large courses (15+ modules, 100+ items) might be slow
- But users run this ONCE per course, not repeatedly

**Question 2: What would Rust improve?**
- Concurrent module/page/assignment fetches
- Parallel pagination (fetch page 1, 2, 3 simultaneously)

**Estimated gain:** 3-5x for large courses
- Current: ~2-3 min for 15 modules, 100 items (guess)
- After: ~30-60 sec
- **Not critical pain** - one-time operation, users can wait

**Complexity:** High
- Complex business logic (module hierarchy, item types)
- File writing, directory creation
- Markdown/HTML formatting
- Error handling for partial fetches

**Verdict:** ⚠️ **Maybe later** - potential gain, but low frequency usage, high complexity

---

### Candidate 4: `course_engagement_audit.py` (683 lines)

**What it does:**
- Title IV UW/UF audit
- Fetches submissions, discussions, quiz submissions for ALL students
- Classifies by last engagement date

**Usage:** Low-medium - end-of-term compliance, not daily
**Current performance:** Unknown - likely slow for large courses
**Bottleneck:** Sequential fetches across 3 endpoints per student

**Question 1: Is it actually slow?**
- No open issues
- Likely slow for 100+ student courses
- BUT: Run 1-2 times per semester, not daily

**Question 2: What would Rust improve?**
- Concurrent per-student fetches (100 students → parallel)
- Potentially 10-20x speedup

**Estimated gain:** 10-20x
- Current: ~5-10 min for 100 students (guess)
- After: ~30-60 sec

**Frequency:** Low (1-2x per semester)

**Complexity:** Medium
- Three API endpoints per student
- Date parsing, classification logic
- PDF generation (Python/reportlab - can't Rust this part)

**Verdict:** ⚠️ **Maybe later** - good gain, but very infrequent use

---

### Candidate 5: `build_deid_master.py` (352 lines)

**What it does:**
- Fetches full course roster (GET /courses/:id/users)
- Generates de-identification codes
- Writes .deid_master.csv

**Usage:** **High** - run whenever roster changes
**Current performance:** Fast - single API call
**Bottleneck:** None - already fast

**Verdict:** ❌ **Not worth it** - no bottleneck, already fast

---

### Candidate 6: Module/Page Traversal (various audit tools)

**What they do:**
- Scan module structures for audits (alignment, accessibility, quality)
- Many small API calls to build full course graph

**Usage:** Medium - pre-publish audits
**Current performance:** Unknown - likely acceptable
**Bottleneck:** Potentially sequential module item fetches

**Estimated gain:** 3-5x
**Complexity:** Medium-high (business logic heavy)
**Frequency:** Medium (pre-semester, occasional audits)

**Verdict:** ⚠️ **Maybe later** - modest gain, not critical pain

---

## The Honest Assessment

### What Rust Solves Well
1. **Embarrassingly parallel HTTP** - many independent API calls
2. **Large-scale enumeration** - scanning 100+ assignments/students
3. **Pure I/O bottlenecks** - where Python's GIL hurts
4. **Repeated operations** - tools run frequently by users

### What Rust Doesn't Help
1. **Business logic complexity** - Python is clearer for complex logic
2. **LLM API waits** - grading bottleneck is ChatGPT, not our code
3. **One-time operations** - users can tolerate 2-3 min once per semester
4. **File processing** - docx/pdf deidentify is CPU-bound, not I/O
5. **Single API calls** - no concurrency opportunity

### Current Evidence

**Proven value (1 tool):**
- ✅ `fix_group_override_recalc.py` - 40-120x speedup, real user pain (issue #135)

**Potential value (speculative):**
- ⚠️ `canvas_sync.py --pull` - maybe 3-5x, but infrequent use
- ⚠️ `course_engagement_audit.py` - maybe 10-20x, but 1-2x per semester
- ⚠️ Module traversal audits - maybe 3-5x, moderate frequency

**No value:**
- ❌ `grader_fetch.py` - no proven bottleneck, complex rewrite
- ❌ `build_deid_master.py` - already fast
- ❌ Most tools - business logic heavy, not I/O bound

---

## Cost-Benefit Analysis

### Path A: Merge PR #136 Only (No cb-init Auto-Install)

**Approach:**
- Merge the Rust override recalc tool
- Document manual Rust install in README
- Keep Python fallback (warn if Rust binary missing)
- Don't add Rust to cb-init
- Wait 3-6 months for more data

**Pros:**
- Proven value for 1 tool (40-120x speedup)
- No forced install (~500MB) for users who don't need it
- Can evaluate if more rewrites are worth it
- Easier rollback if problematic

**Cons:**
- Manual install friction for users who hit the pain
- Python fallback maintenance burden
- Split implementation (Rust + Python versions)

**When to revisit:**
- After 3-6 months usage
- If 2+ more tools show proven bottlenecks
- If users request more Rust rewrites

---

### Path B: Merge PR #136 + Auto-Install Rust in cb-init

**Approach:**
- Merge the Rust override recalc tool
- Add Rust auto-install to cb-init (Step 5/9)
- Build all Rust binaries during init
- Commit to Rust as part of the stack

**Pros:**
- Seamless UX (one-command setup)
- Ready for future Rust rewrites
- No Python fallback maintenance

**Cons:**
- ~500MB + 2-5 min for ALL users (even if they never hit the bottleneck)
- Commitment based on 1 proven tool
- Windows manual install friction
- CI complexity

**Risk:** Forcing ~600MB + Rust complexity on everyone for a bottleneck that only large-course users hit.

---

### Path C: Strategic Rust (Opt-In)

**Approach:**
- Merge PR #136 with Python fallback
- Add `cb-init --with-rust` flag (opt-in)
- Default cb-init skips Rust, shows optional install message
- Users who hit performance pain can opt in

**Pros:**
- Proven value available to those who need it
- No forced complexity for small-course users
- Can build evidence for future full adoption
- Graceful degradation

**Cons:**
- Two install paths to document/support
- Some users won't know to opt in until they hit pain

---

## Recommendation (Skeptical but Open)

### Short-term (Next Week): Path C - Strategic Opt-In

**Action:**
1. ✅ Merge PR #136 (proven 40-120x speedup)
2. ✅ Keep Python fallback (warn if Rust binary missing)
3. ⚠️ Add `cb-init --with-rust` flag (opt-in, not default)
4. ⚠️ Document in README: "For courses >50 students, install Rust for 10-100x speedup"
5. ⚠️ Add runtime message: "This operation is slow. Install Rust for 40x speedup: cb-init --with-rust"

**Why:**
- Proven value for 1 tool, but only 1 tool
- Large courses get the speedup
- Small courses (~20-30 students) don't pay the cost
- Gather 3-6 months of usage data before committing

---

### Mid-term (3-6 Months): Evaluate Next Candidates

**Criteria for next Rust rewrite:**
1. **User-reported pain** (open issues, complaints)
2. **High frequency** (daily use, not 1x per semester)
3. **Proven bottleneck** (profiling shows HTTP wait time)
4. **Clear concurrency win** (embarrassingly parallel operations)

**Likely candidates (IF users report pain):**
- `canvas_sync.py --pull` (if large-course users complain)
- `course_engagement_audit.py` (if 100+ student courses hit timeout)

**Threshold for auto-install:**
- 3+ tools with proven 10x+ speedups
- Combined usage covers >50% of daily workflows
- User feedback says "Rust makes canvas-toolbox usable for large courses"

---

### Long-term (6-12 Months): Decide on Full Adoption

**Option 1: Rust as core dependency**
- If 3+ tools prove value, add to cb-init by default
- Commit to Rust for all future high-performance tools

**Option 2: Keep Python-first**
- If only 1-2 tools benefit, keep Rust opt-in
- Python remains primary implementation language
- Rust for niche performance cases only

---

## What Would Change My Mind

### Evidence that would justify auto-install:

1. **More proven bottlenecks**
   - 2+ additional tools with user-reported slowness
   - Profiling confirms HTTP concurrency is the win

2. **Frequency of pain**
   - Daily-use tools (grading, syncing) hit Rust-solvable bottlenecks
   - Not just occasional accommodation workflows

3. **User demand**
   - Multiple users request Rust versions
   - "Canvas-toolbox is too slow" feedback correlates with Rust opportunities

4. **Simpler alternative doesn't exist**
   - Python asyncio can't solve it (proven by benchmark)
   - Canvas API batching isn't available

---

## Questions to Answer Before Committing

### 1. How many users actually hit this bottleneck?
- Small courses (20-30 students, <50 assignments): Likely never notice
- Medium courses (40-60 students, 50-100 assignments): Occasional pain
- Large courses (100+ students, 100+ assignments): Clear pain

**Data needed:** Survey existing users about course sizes

### 2. Can Python asyncio close the gap?
- `asyncio` + `aiohttp` could give 5-10x speedup
- Still slower than Rust (no zero-cost abstractions)
- But might be "fast enough" without new dependency

**Action:** Benchmark Python asyncio version vs Rust

### 3. What's the actual tool usage distribution?
- Which tools are run daily vs weekly vs once per semester?
- Where do users spend most time waiting?

**Data needed:** Usage telemetry (if users opt in) or survey

### 4. What's the maintenance cost of dual implementations?
- How often do Python tools break? (rare - stable codebase)
- How often would Rust tools break? (unknown)
- Can we realistically maintain both?

---

## The Bottom Line (Honest Take)

### Rust is Justified IF:
1. ✅ Proven 10x+ speedup (we have this for 1 tool)
2. ⚠️ High-frequency pain (unclear - might be rare workflow)
3. ❌ Multiple tools benefit (only 1 so far)
4. ❌ Python can't solve it (haven't tried asyncio yet)

### Current State:
- **1 tool proven** (override recalc: 40-120x speedup)
- **3-4 tools potential** (speculative, no user complaints)
- **50+ tools no benefit** (business logic, not I/O bound)

### Conservative Recommendation:
**Merge PR #136, make Rust opt-in, gather data for 3-6 months.**

Don't commit ~600MB + complexity for the entire user base until we have:
- 3+ proven bottlenecks
- User demand for speedups
- Evidence Python asyncio can't close the gap

### Aggressive Recommendation:
**If you trust the analysis that more tools will follow:**
- Auto-install Rust in cb-init
- Commit to Rust for all Canvas API heavy-lifting
- Accept ~600MB cost as "cost of doing business" for large courses

But I'm skeptical we have enough evidence yet.

---

## Proposal for Tomorrow

1. ✅ **Merge PR #136** (proven value)
2. ⚠️ **Modify to add Python asyncio fallback** (try before committing to Rust)
3. ⚠️ **Add opt-in flag to cb-init**: `--with-rust` (don't make default yet)
4. ⏸️ **Wait 3 months for usage data** (do users hit pain? do they request Rust?)
5. 🔄 **Revisit decision** based on:
   - User feedback (is it actually slow?)
   - More bottlenecks discovered (3+ tools?)
   - Python asyncio benchmark (can we close the gap without Rust?)

**Skeptical but open:** Rust has clear value for 1 tool. Let's prove it's worth the broader investment before committing the stack.
