# Canvas Toolbox

The words this toolkit uses for managing Canvas courses as code: mirroring, building,
grading, auditing, and protecting student data. One agreed meaning per word, so people,
agents, and code say the same thing.

## Language

### People

**User**:
The person using the toolkit: an instructor or a TA. Name the role only where it changes what happens.
_Avoid_: Operator, reviewer, approver, admin

**Instructor**:
The teacher of record, who owns every decision about the course and authorizes what a TA may do.
_Avoid_: Professor, faculty

**TA**:
A user the instructor has authorized to act on the course, such as reviewing grades before they reach students.
_Avoid_: Grader, assistant

**Canvas user ID**:
Canvas's number for an account; in this toolkit it always identifies a student, never the user.
_Avoid_: User (for a student), user number

**Test Student**:
Canvas's built-in fake student, used by Student View; never a real student.
_Avoid_: Test user, dummy student

### Courses and copies

**Master**:
The template course where authoring happens.
_Avoid_: Template, dev course

**Blueprint**:
The Canvas Blueprint course that Course Sections are cloned from in online programs.
_Avoid_: Parent course

**Course Section**:
One live, per-semester Canvas course that students are enrolled in (S1, S2, …); it holds one or more Sections.
_Avoid_: Section course, offering, live course, shell

**Section**:
Canvas's standard meaning: a group of enrollments inside one course. A course can hold several, and Sections can be merged.
_Avoid_: Canvas section, Course Section (for this)

**Source of truth**:
The local course files; Canvas is the target they sync to, never the reverse.

**Mirror**:
The local copy of a Canvas course's content, kept as files.
_Avoid_: Snapshot, export, backup

**Refresh from Canvas**:
Bringing the mirror up to date with what is in Canvas now.
_Avoid_: Pull, download, fetch

**Update Canvas**:
Making a Canvas course match the local course files.
_Avoid_: Push, content push, sync (alone), upload, deploy

**Update Course Sections from the Blueprint**:
Carrying content and settings from Master → Blueprint → Course Sections.
_Avoid_: Blueprint sync, propagate

**Blueprint exception**:
A Course Section's local change to content the Blueprint locks.
_Avoid_: Exception (unqualified), override

**New Quiz**:
A quiz in Canvas's newer engine, New Quizzes, which runs as an external tool. The toolkit updates its settings and questions; stimulus and item-bank items stay read-only.
_Avoid_: NewQuiz (in prose), quiz engine 2

**Classic Quiz**:
A quiz in Canvas's original engine, Classic Quizzes, which the toolkit can read and write.
_Avoid_: Old quiz, legacy quiz

### Canvas

Canvas's own words, as Canvas shows them to instructors and TAs. When Canvas's screen and
its data use different names, the screen's name wins. Section, New Quiz, Classic Quiz,
Override, Excused, Test Student and Canvas user ID are under their topics.

**Course**:
One Canvas course, with its own content, people, and gradebook.
_Avoid_: Class, shell

**Term**:
The academic period a course belongs to, such as Fall 2026; its dates can limit when students take part.
_Avoid_: Semester (for the Canvas object), session

**Published**:
Visible to students. A course, module, or item can each be published or unpublished.
_Avoid_: Live (for content), visible, released

**Concluded**:
A course past its end date, read-only for students: nothing more can be submitted.
_Avoid_: Archived, closed, ended

**Enrollment**:
One person's place in a course or section, with a role.
_Avoid_: Registration, roster entry

**Role**:
What an enrollment may do: Teacher, TA, Student, Designer, or Observer.
_Avoid_: Permission level

**Teacher**:
Canvas's role name for an instructor. Say "instructor" in prose; say "Teacher" only when naming the Canvas role.
_Avoid_: Teacher in prose

**Group set**:
A set of student groups made for one purpose, such as project teams.
_Avoid_: Group category, team set

**Student View**:
Canvas's preview of a course as a student sees it.
_Avoid_: Preview mode, act as student

**Module**:
An ordered collection of module items that sets the path through a course.
_Avoid_: Unit, week (as the Canvas object), folder

**Module item**:
An entry in a module that points to content (a page, assignment, quiz, discussion, file, link, or text header); it is not the content itself.
_Avoid_: Content (for the entry), link

**Text header**:
A label inside a module that groups the items under it.
_Avoid_: Subheader, divider

**Prerequisite**:
A module a student must complete before the next one opens.
_Avoid_: Gate, unlock rule

**Requirement**:
What a student must do with a module item (view it, mark it done, submit, or reach a score) for its module to count as complete.
_Avoid_: Completion rule, completion requirement

**Page**:
Ungraded course content, written in Canvas's editor.
_Avoid_: Wiki page, content page

**Syllabus**:
The course's syllabus page, which Canvas pairs with a list of the course's dated work.
_Avoid_: Course outline

**Assignment**:
Work Canvas tracks in the gradebook. Graded quizzes and graded discussions are assignments underneath.
_Avoid_: Task, challenge, homework

**Assignment group**:
A named group of assignments in the gradebook, such as Projects, which can carry a share of the final grade.
_Avoid_: Category, bucket

**Discussion**:
A topic students reply to in threads; it may be graded.
_Avoid_: Forum, board

**Announcement**:
A message posted to everyone in a course.
_Avoid_: News, broadcast

**External tool**:
A third-party tool that opens inside Canvas; New Quizzes is one.
_Avoid_: LTI (in prose), plugin, integration

**Due**:
When work is due.
_Avoid_: Deadline

**Available from**:
When students can first open the work.
_Avoid_: Unlock date, start date, open date

**Until**:
When the work closes to students; after it, they can't submit.
_Avoid_: Lock date, close date, end date

**To-do date**:
The date an ungraded page or discussion shows on students' to-do lists.
_Avoid_: Due (for ungraded items)

**Submission**:
One student's (or group's) turned-in work for one assignment, across all their attempts.
_Avoid_: Upload, turn-in, artifact

**Attempt**:
One try within a submission; turning work in again makes a new attempt.
_Avoid_: Version, resubmission (for the try itself)

**Missing**:
Canvas's mark for work past due with nothing submitted.
_Avoid_: Zero, not turned in

**Late policy**:
A course setting that takes points off late work automatically, or gives missing work a set grade.
_Avoid_: Penalty

**Gradebook**:
The course's grid of students and assignments, with every grade.
_Avoid_: Grade book, grade sheet

**SpeedGrader**:
Canvas's screen for grading one student's submission at a time.
_Avoid_: Grader (for the screen)

**Rubric**:
A set of criteria, each with ratings worth points, attached to an assignment to score it.
_Avoid_: Scoring guide, checklist (a course checklist is not a rubric)

**Criterion**:
One row of a rubric: one thing being judged.
_Avoid_: Dimension, category

**Rating**:
One level within a criterion, worth a number of points.
_Avoid_: Band, level

**Outcome**:
A learning goal tracked across assignments through rubrics.
_Avoid_: Objective, competency (unless the course names it so)

**Display grade as**:
How an assignment's grade appears: points, percentage, letter grade, complete/incomplete, or GPA scale.
_Avoid_: Grading type, grade format

**Grading scheme**:
The scale that turns a percentage into a letter grade.
_Avoid_: Grade scale, letter scale, grading standard (Canvas's API name for it)

**Posting policy**:
Whether an assignment's grades show to students as soon as they're entered (automatic) or only once posted (manual).
_Avoid_: Muting, mute, release policy

**Posted**:
A grade students can see. Under a manual posting policy, a grade is entered but hidden until it is posted.
_Avoid_: Released, published (for grades)

**Peer review**:
One student reviewing another's submission, assigned per submission.
_Avoid_: Peer grading, peer feedback (for the assignment)

### Toolkit and installation

**Toolkit**:
canvas-toolbox itself: the shared tools, skills, and constitution every course folder runs.
_Avoid_: Toolbox (in prose), framework, library

**Course folder**:
One course's own folder (a git repository underneath): one course, one folder, one settings file, one editor window.
_Avoid_: Course repo, consumer repo, consumer

**Flat layout**:
The current install shape, where the toolkit's files live directly in the course folder.

**Nested layout**:
The older install shape, where the toolkit is a visible subfolder of the course folder.
_Avoid_: Legacy mode

**Pristine clone**:
The hidden, untouched copy of the toolkit inside a flat-layout course folder, used only as the update source.
_Avoid_: Hidden clone, cache

**Distribution manifest**:
The allowlist of toolkit files that reach a course folder.
_Avoid_: Payload list, file list

**Agent package**:
A named bundle of toolkit capability (course design, grading, student support) with a declared list of what it can do.
_Avoid_: Plugin, module

**Capability consent**:
The instructor's explicit approval of an agent package's capabilities, asked again whenever a new version can do more.
_Avoid_: Permission, opt-in

**Constitution**:
The always-on rules in AGENTS.md that bind every session whatever the task.
_Avoid_: System prompt, policy

**Skill**:
A loadable playbook for one operating mode (grading, course build, audit, …).
_Avoid_: Mode file, agent

**Runtime adapter**:
A generated copy of the skills in the folder a particular AI tool reads; never edited by hand.
_Avoid_: Adapter (unqualified)

**Handoff**:
A dated, structured file passing work between repos or sessions, with a status that controls whether it may be acted on.
_Avoid_: Note, memo

### Student data (FERPA)

**AI-readable**:
Material with names replaced by codes, safe for the AI and the cloud: de-identified work, de-id codes or keys, grades without names.
_Avoid_: Zone 1, safe zone

**Local only**:
Material that links students to their names; it stays on this computer and is never shown to the AI, written to a log, or sent to the cloud.
_Avoid_: Zone 2, PII files, restricted

**Named working file**:
A file that may contain names and that the AI may read, under one rule: a name never appears beside a grade.
_Avoid_: Zone 2-adjacent, semi-restricted

**De-id master**:
The course-wide record of every enrolled student, linking each to their de-id code. It is local only.
_Avoid_: Roster, key file

**De-id code**:
A student's single stable, opaque, course-wide identifier (e.g. `S-68BC40`), safe to say to an agent.
_Avoid_: De-id key, deid code, student code, anonymous ID

**De-id key**:
An opaque label for one student's submission within one batch; a student has a different key in every batch.
_Avoid_: De-id code, token, alias

**Keymap**:
The local-only record linking each de-id key back to its student, used to re-identify a batch.
_Avoid_: Key file, lookup

**De-identify**:
Replacing names and identity in student work with de-id keys before anything reaches an LLM.
_Avoid_: Anonymize, scrub (for the whole process)

**Re-identify**:
Mapping keyed results back to students locally, by key and never by row order.
_Avoid_: Unmask, de-anonymize

**Format adapter**:
The de-identifier for one file type (Word, PDF, notebook, …).
_Avoid_: Adapter (unqualified), parser

**Name leak**:
A real name that survived de-identification.

**Student-facing text**:
Anything written for one identified student to read; refers to them by given name and last initial only.
_Avoid_: Message (alone), output

**Delivery details**:
The minimum identifying detail the user needs to find and confirm the right place to deliver student-facing text; never prose.
_Avoid_: Operator-facing scaffolding, context, notes

### Grading

**Grading folder**:
The local working folder for grading one assignment.
_Avoid_: Challenge dir, assignment dir

**Consensus grading**:
Grading the same work in three independent passes and reconciling them, instead of trusting one pass.
_Avoid_: Multi-pass, ensemble

**Hybrid grading**:
Routing each rubric criterion to the cheapest method that can check it reliably (script before LLM), with a human on top.
_Avoid_: Mixed grading

**Review gate**:
The rule that no AI-drafted grade or comment reaches a student until the instructor, or a TA they authorized, has read the work and the draft, then approved twice. Its principle number is HG-5.
_Avoid_: Approval step, human-in-the-loop (alone)

**Update grades in Canvas**:
Sending reviewed grades and comments to students' submissions in Canvas. Whether students see them yet is the posting policy.
_Avoid_: Push, grade push, upload, post

**Disclosure tag**:
The line appended to every comment sent to Canvas, saying truthfully what graded it, who drafted it, and who reviewed it.
_Avoid_: Provenance tag, AI label, signature

**Standing**:
A student's running overall grade, sent by the instructor to a no-submission column students see as "Your Grade."
_Avoid_: Your-grade column, running total, current grade

**Update standing in Canvas**:
Sending each student's standing to that column.
_Avoid_: Standing push, push

**Waiting**:
Submitted work that Canvas says still needs grading.
_Avoid_: Ungraded, needs grading, pending, queue

**Late submission**:
Work Canvas marks as turned in after its due date.
_Avoid_: Late (for work that is only slow to be graded)

**Grade correction**:
An instructor-directed change to a grade already in Canvas, with the old and new value recorded.
_Avoid_: Regrade (that's re-grading a resubmission), fix

**Regrade**:
Grading a resubmission again.
_Avoid_: Correction

**Andon**:
A built-in stop that halts a run when something is wrong (e.g. a comment would be posted twice), rather than letting it continue.
_Avoid_: Warning, check

**Voicing profile**:
A course's written description of the instructor's feedback voice, which every student-facing draft follows.
_Avoid_: Tone guide, persona, style

### Per-student interventions

**Intervention**:
Any change to one student's dates, limits, or requirements that the instructor directs.
_Avoid_: Exception, adjustment

**Accommodation**:
An intervention a disability-services letter entitles a student to.
_Avoid_: Intervention (when the letter is the source), SAS (alone)

**Time extension**:
More time on timed quizzes, as a multiplier.
_Avoid_: Extra time, extension (alone)

**Late grace**:
Letting one student submit after the due date by removing the Until date for them; the work still shows as late.
_Avoid_: Late accommodation, reopen, late pass

**Override**:
A set of dates on an assignment that applies to one student, a section, or a group instead of the assignment's own; Canvas sets it under "Assign to".
_Avoid_: Exception

**Excused**:
Canvas's mark (EX in the gradebook) for a student who doesn't have to do an assignment; it doesn't count toward their grade.
_Avoid_: Exemption, exempt, waiver

### Compliance (Title IV)

**Engagement**:
Academically related activity: a submission, quiz attempt, or discussion entry. Logging in is not engagement.
_Avoid_: Attendance, activity, participation

**Last engagement date**:
The date of a student's most recent engagement; the regulation calls it the last date of academically related activity.
_Avoid_: Last date of attendance, LDA, last login

**Unofficial withdrawal (UW)**:
A student whose last engagement falls before the UF date.
_Avoid_: Dropout, ghost

**Unofficial fail (UF)**:
An unofficial withdrawal with a failing grade, which makes the student a candidate for a federal-aid return calculation.
_Avoid_: F, fail

**Never participated**:
An enrolled student with no engagement on record.
_Avoid_: No-show

### Course improvement

**Improvement**:
One thing to fix, try, or revisit in a course, kept as a card on the course's board.
_Avoid_: Ticket, issue, task, finding (once it's logged)

**Board**:
A course's improvement backlog, with columns Backlog → Ready → In Progress → In Review → Done.
_Avoid_: Kanban, backlog (for the whole board)

**Finding**:
Something an audit observed; it becomes an improvement when logged.
_Avoid_: Issue, defect
