# 38. Workflows by task size: the consolidated design

Draft of 2026-11-13 for TSR story DVDG-565. It gathers the owner's decisions and the proposals made so far into one place. Measurements and reasons are in file 37. Nothing here is implemented. Drafts of the agent definitions are in `workflows/` at the repository root.

Each statement is marked: **Decided** (the owner said so), **Proposed** (my answer, used as the default until the owner says otherwise), or **Open**.

## 1. Aim

Reach a goal faster and with better results than the current workflow did on G-001 (8h 55m, 253 messages, 67 agent sessions), while staying autonomous.

- **Decided.** Criteria, in order: quality of implementation, speed of delivery. Resources are not a criterion.
- **Decided.** The current workflow stays. New workflows are added beside it and are selectable.
- **Decided.** Extend Hivemill as safely as possible, so upstream changes affect the extensions little.
- **Decided.** G-001 is the reference goal; its prompt for the boss is used word for word (TSR task HM-5, branch `baseline/pre-g-001`).

## 2. Principles

1. Code routes the work; agents think, build and check. Agents do not ask each other to start, stop or report.
2. Design first, then freeze. The design is written into the Taskosaur task before any code.
3. The Taskosaur task is the single record of a piece of work (**Decided**): design, acceptance, tests, each agent's comments, commits, review and test marks.
4. One builder per story, working the children in sequence (**Decided**), keeping its context until the story is merged.
5. Findings go from the reviewer straight to the builder. The architect is called only when something does not converge.
6. Mechanical steps are code: preflight, checks, routing, the merge queue, Done in Taskosaur, reports.

## 3. The workflows

**Decided:** three workflows, for simple, medium and huge tasks; hardcoded in the filesystem for now; chosen from the task's complexity by default; the owner can tell the boss which one to use.

**Proposed** content and selection:

| | simple | medium | huge |
|---|---|---|---|
| Picked when | size XS or S, and complexity 1 or 2 | size M, or complexity 3 | size L or XL, or complexity 4 or 5, or the task already has children |
| Architect | readiness check only | writes design and acceptance into the task | design, design attack for risky areas, split into children |
| Builder | 1 | 1 | 1, children in sequence |
| Review | reviewer, with the tests | reviewer, with the tests | reviewer per child as it reaches In Review |
| QA | none separate | none separate | QA on the whole branch when all children are In Review |
| PR | one | one | one per story (**Decided**) |

- When size and complexity point to different workflows, the larger one wins.
- A task with neither is rated by the architect first, as the Taskosaur skill requires for every task.
- `current` remains the name of today's workflow with its full set of roles.

## 4. Roles

| Role in the flow | Runs as factory role | Model | Session |
|---|---|---|---|
| Architect | **Proposed:** the existing `staff-engineer` role, with the workflow's own prompt | Fable 5.2 | one per goal, resumed on events |
| Builder | `coder` | Opus 5.5 | one per story, resumed until merge |
| Reviewer | `reviewer` | Opus 5.5 | one per story, resumed for each child and each round |
| QA (huge only) | `qa` | Opus 5.5 | one per story |
| Orchestrator | code | none | always |

- Existing role names are reused so the worker guard, the permission templates and the sandbox need no change. Whether `staff-engineer`'s permissions fit the architect's job was not checked.
- The boss stays as the owner's contact. Director, lead, pm and judge take no part in these workflows.
- Models: Fable for the architect reverses the code comment "Never Fable (owner rule)" (the owner asked for it on 2026-11-13). The model per role is the `MODELS` table in the CLI; a per-workflow model needs a seam there.

## 5. The run, step by step

1. **Intake (boss).** The owner names a Taskosaur task, or gives a goal as text. The boss creates the factory goal with the TSR key and, if the owner said so, the workflow.
2. **Preflight (code).** Git identity, toolchains, base branch, CI, Taskosaur reachable. A failure stops the goal before any agent starts.
3. **Workflow choice (code).** From the task's size and complexity, unless overridden.
4. **Readiness (architect).** Reads the task. If it is enriched (section 6), the design step is skipped (**Decided**). Otherwise the architect does what the workflow asks: acceptance, design, or design plus split.
5. **Freeze.** The design and acceptance are fixed. A later change is a visible edit plus a comment with the reason, and pauses the builder.
6. **Build (builder).** One child at a time: implement, test, run the checks, commit with the child's TSR key, comment on the child, move it to In Review. Then the next child.
7. **Review (reviewer).** Starts for a child when it is In Review (**Decided**), while the builder goes on. Result: "reviewed by agent: passed" or "changes requested", set in Taskosaur (TSK-590).
8. **Fix (code routes).** "Changes requested" moves the child back to In Progress (**Decided**) and the findings go to the builder, who fixes them after the child it is working on and before starting the next (**Proposed**). The same reviewer session then checks its findings and the delta.
9. **QA (huge only).** Starts when all children are In Review and reviewed (**Decided** for "all In Review"). Tests the whole branch. A failure goes back to the builder like a review finding.
10. **Merge (code).** Reviewed, tested where the workflow asks, checks green: the story enters the merge queue. One merge at a time per project.
11. **Done (code).** After the merge is verified: commits linked, closing comment, every child and the story moved to Done in Taskosaur (**Decided**).
12. **Audit (architect, huge only).** Each success criterion against evidence.
13. **Report (code).** The owner's report is generated from the database.

## 6. "Enriched"

**Proposed** test, applied by code and confirmed by the architect's readiness check:

- the description has a goal, context, acceptance criteria and how to verify;
- size and complexity are set;
- for size L or XL: children exist, each meeting the same test, with their dependencies;
- anything a user sees has its tests designed.

A task that fails the test is not rejected: the architect fills the gaps and the run goes on.

## 7. Merge conflicts

- **Decided:** stories that touch the same files run in sequence by default; the architect or the owner can mark an overlap as safe.
- **Decided:** one PR per story.
- **Proposed** (file 37 has the reasons): merges one at a time; after every merge each open story branch is test-merged; a clean result with green checks is refreshed by code; a conflict, or a clean merge with red checks, is resolved by the builder of the story that has not merged yet, using the merged task's design; the same reviewer re-checks the affected parts; only affected children lose their marks; the architect decides after two failed rounds or when a design would change.

## 8. Limits on rounds

- **Proposed:** at most 5 fix rounds per child (the owner's "maximum 5 tries" for the lean workflow). After 2 rounds on the same kind of finding the architect is called before the third.
- **Open:** TSR story HM-2 asks for limits by cost ("a size-1 task with a 2 USD round trip gets no more tries"). That conflicts with "resources are not a criterion". Proposed reading: the limits stop a loop that is not converging; cost is shown, not used as a stop.

## 9. Taskosaur

- **Decided:** tight integration; breakdown the way the `working-with-taskosaur` skill does it; reviewed and tested marks (TSK-590, TSK-591).
- **Proposed:** REST API from the factory CLI; the token stays with the CLI; agents use `factory tsr …` commands; the orchestrator, not the reviewing agent, sets the mark from the recorded verdict.
- **Proposed:** a goal given as plain text (the reference goal) gets a Taskosaur story and children created by the architect first, so the record rule holds for every run.

## 10. How it is added to Hivemill

Extend beside, do not rewrite inside (**Decided** as the aim; the layout is **Proposed**):

| What | Where |
|---|---|
| Workflow definitions | `workflows/<name>.md` |
| Agent definitions | `workflows/roles/<role>.md` |
| Engine: selection, states, fix loop, merge queue, conflict checks | a new package, loaded lazily like the `scout/` modules |
| Taskosaur client and `factory tsr` commands | the same package |
| Tests | their own files |

Seams in `bin/factory_cli.py`, each a one-line hand-over that does nothing for the `current` workflow:

1. goal creation: accept and store the workflow and the TSR key;
2. the tick: let the engine advance its goals;
3. spawn: the workflow's prompt and model for a role, and resume by session id;
4. the merge gate: the engine's rule for these workflows;
5. command registration for `factory tsr` and the workflow commands.

Database, additive only: a workflow column on goals; a TSR key on goals and tasks; a marker for a frozen spec. New config keys under one prefix.

Not checked in the code: that these five points can be added as one-line seams.

## 11. Open questions

| # | Question | Proposed answer |
|---|---|---|
| 1 | Which task fields pick the workflow? | size and complexity; the larger wins (section 3) |
| 2 | What exactly is in each workflow? | the table in section 3 |
| 3 | What does "enriched" mean? | the test in section 6 |
| 4 | A child is rejected while the builder is ahead: when is it fixed? | after the current child, before the next |
| 5 | Where do the workflows live and how does the boss name one? | `workflows/<name>.md`; the owner says "use workflow simple", the boss passes `--workflow simple` |
| 6 | A goal given as text: is a Taskosaur story created first? | yes |
| 7 | Which factory roles may call which `factory tsr` command? | builder and reviewer: read, comment; architect: also create and edit children; marks and Done: orchestrator only |
| 8 | Limits by cost (HM-2) or by convergence? | convergence; cost shown only |
| 9 | Does the architect run as `staff-engineer`? | yes, if its permissions fit; to check |

## 12. Build order

1. Taskosaur: TSK-590, then TSK-591.
2. Hivemill: the Taskosaur client and `factory tsr` (DVDG-545, re-scoped).
3. Hivemill: workflow selection and the `simple` workflow end to end.
4. `medium`, then `huge` with the per-child review, QA and the merge queue.
5. Run the reference goal (HM-5) on `current` and on the new workflow, and compare.

## Q: Will we keep the boss and the director, or will we not need them?

Keep the boss. The new workflows do not need the director; it stays only for goals that run on the `current` workflow.

### Boss: stays

- It is the owner's one contact: it takes the request ("pick up TSK-590", "use workflow simple"), creates the goal, and brings back the questions only the owner can answer.
- It is cheap. On G-001 the boss made 10 requests and cost about 0.24 USD.
- In the new workflows it does less than today: it no longer relays progress reports, because the owner's report is generated from the database.

### Director: not part of the new workflows

What the director did on G-001, and who does it in the new flow:

| Director's job on G-001 | In the new workflows |
|---|---|
| Staff the goal: start the lead, brief it | code starts the architect and the builder |
| Receive status reports (44 from the lead) and chase them ("status?") | not needed: the state is in the database and Taskosaur |
| Technical decisions (13, for example "one helper, not two", "fix the security hole in this goal") | the architect decides and writes it on the task |
| Grant extra attempts | the round limit in the workflow, then the architect |
| Reports to the boss for the owner (13) | generated by code |
| Capacity: how many agents run, which goal goes first | code: the resource gate and spawn queue that exist today, the overlap rule and the merge queue |
| Owner-level decisions | the architect asks the boss, the boss asks the owner |

On G-001 the director made 485 requests, cost about 16.74 USD and exchanged 79 messages with the lead. None of that work is building or checking.

### What still needs a director

- Goals on the `current` workflow, which keeps its lead and director.
- Factory-wide chores the director does today outside any goal: folding the skill-scout reports into the owner report, watching utilization and cap breaches, the daily digest. In the new design these would be code or stay with a director; not designed yet.

Not checked in the code: whether the factory starts and ticks cleanly with no director running (`factory up` resumes the director today), and what breaks when no lead exists for a goal.

## Q: Can I tell the boss "fix dropdown A: add the default option to it and change the colour of its background", and have the task created as now, with all details and references to the files to change?

Yes, that is how the design works, once it is built. Today it is a draft.

What happens with such a sentence:

1. **Boss.** Takes the sentence as given and creates the goal. It does not rewrite it.
2. **Workflow choice.** No Taskosaur task exists yet, so there is no size to choose from. The architect rates the request first; a one-control change like this would be size XS or S, complexity 1 or 2, so the `simple` workflow.
3. **Architect.** Reads the code, finds dropdown A, and creates the task in Taskosaur with the same template used in this session: goal, context, what to change, the files and places to change, acceptance criteria, how to verify, labels, size and complexity; for a visible change, the test to add.
4. **Questions.** The architect asks through the boss only for what the sentence leaves undecided and the code cannot answer. Here: which colour, if the project has no obvious token for it, and which option is the default. It does not ask what it can read in the code.
5. **Builder, reviewer, merge.** As in the `simple` workflow; the task gets the builder's comment, the "reviewed by agent" mark and Done after the merge.

What this rests on:

- Open question 6 (a goal given as text gets a Taskosaur task first), proposed yes.
- The `simple` workflow's architect step, which was widened in the draft to write the files and places to change, not only the acceptance criteria.

What it costs: the architect's reading and writing comes before any code, a few minutes for a change this small. With quality first that is the intended trade.

Compared with today: the current workflow also turns a sentence into a spec, through boss, director, lead and pm, but the spec lives in the factory's database, not in Taskosaur, and earlier versions of it are not kept (file 37).

## Q: Could the factory later estimate a task from all previously executed tasks? Does the design need to change to make that easier?

Yes, and the design should change a little now, because an estimate from history is only as good as what each finished task leaves behind. Proposed; not built.

### The flow the owner described

1. The owner asks the boss for an estimate of a request or of a Taskosaur task.
2. The boss hands it to the architect as an **estimate-only run**: nothing is built.
3. The architect reads the code, drafts the breakdown, and looks up finished tasks that are similar (same area labels, same size and complexity, overlapping files).
4. The architect returns an estimate as a range, with the reference tasks it used and what they actually took.
5. The boss answers the owner.

The drafted story and children are kept in Taskosaur in the Backlog, so the work is not thrown away and can be started later without a second architecture pass (an enriched task skips it).

### What exists today

- Taskosaur keeps per task: size, complexity, the agent estimate, the human estimate, logged time entries, labels, linked commits. `model Task` also has a free `customFields` JSON column (`backend/prisma/schema.prisma`); whether the API exposes it for writing was not checked.
- The factory keeps per factory task: attempts, verdicts, agent sessions with start and end, and the token usage in session transcripts.
- G-001 shows these can be joined after the fact (file 37), but only by a one-off script.

### What to add to the design so estimation works later

1. **Actuals written at Done.** When a story is merged, the orchestrator records on each Taskosaur task what it really took: time from start to merge, working time per role (as time entries naming the role), review and QA rounds, files and lines changed, tokens and cost. One fixed format, written by code, never by an agent's summary.
2. **The planning estimate is never overwritten.** The size, complexity and estimate given before the build stay as they were, so estimate and actual can be compared. A re-rating during the work is recorded as a comment, not as a silent change.
3. **Comparable features on every task.** The area labels, the size and complexity, the task type, and the files and areas touched. The architect already lists the files per story for the overlap rule; the same list serves matching.
4. **One query for "similar finished tasks".** By labels, size and complexity among Done tasks, returning their actuals. In Taskosaur this is a list filter plus the stored actuals; it may need a small addition there once the format of the actuals is fixed.
5. **An estimate-only mode of a run**, which stops after the architect's step and reports through the boss.

### Limits

- History from the current workflow is a poor reference for the new ones: G-001's factory tasks took what they took because of the rework described in file 37. Estimates become useful once a few dozen tasks have been finished under the new workflows; that number is a judgement, not a measurement.
- An estimate from similar tasks is a range, and the architect should say how many reference tasks it found. With fewer than three it should say that it is estimating from the code alone.

## Q: Record of 2026-11-13: tasks are written only after reading the code; the breakdown agent uses the Taskosaur skill

- The owner asked for the Taskosaur tasks to be rewritten from the code, with no assumptions. TSK-590 was rewritten after reading the Taskosaur repository (branch master at 84b5450) and became a story with three children: TSK-592 backend, TSK-593 MCP tool and skill text, TSK-594 frontend. TSK-591 (roll-up) was rewritten the same way.
- What the code changed: "In Review" is a status with a user action, not a category; agents and the MCP connector account are both `isAgent`; members may change only the status through the general update, so the marks get their own endpoint; the automatic move reuses the existing update path; list and tree rows have no markers and are out of scope.
- The `working-with-taskosaur` skill has a new first write rule, "Read the code first" (its `references/creating.md`, and one line in `SKILL.md`): every statement about today's code names the file and symbol; no "decide in implementation"; size after reading.
- The architect definition (`workflows/roles/architect.md`) now says to load that skill for the breakdown and for every task it writes.

## Q: Estimation before execution is important, in time as well as cost, so the owner can choose between task A and task B. What changes?

Owner requirement of 2026-11-13. It turns the estimation proposal above into a requirement and adds elapsed time.

- **Three numbers per task and per story**: working time (the existing agent estimate), elapsed time until delivered, and cost. A range when few similar tasks exist, with the reference tasks named.
- **An estimate-only run** is a request the boss accepts as such. It can cover several tasks at once ("estimate A and B"); the architect reads the code for each, and the boss returns the comparison. Nothing is built.
- **Stored on the Taskosaur task** before the build and never overwritten; the orchestrator writes the actuals at Done. Taskosaur task TSK-595 adds the fields: `elapsedEstimate`, `costEstimate`, `actualElapsed`, `actualCost`, `actualRounds`. Working time actually spent stays in time entries. TSK-595 covers storage, API and MCP; showing the numbers in the web app is a separate task that is not written yet.
- **The drafted breakdown stays in the Backlog**, so choosing A later starts without a second architecture pass.

Found in the Taskosaur code while writing TSK-595 (branch master at 84b5450), and it affects the integration (DVDG-545):

- In `TasksService.update` a MEMBER may change only a task's status. Estimates, size, description and parent are refused.
- The organization's MCP key account is a MEMBER, and regenerating the key resets it to MEMBER and revokes the old key.
- So Hivemill needs its own agent user with the MANAGER role and a personal access token, or narrower endpoints in Taskosaur. The agent check marks are not affected: they only need an agent user.

Do the five Taskosaur tasks for the marks (TSK-590 and children, TSK-591) need changes for estimation? No. Estimation uses its own fields and its own task.
