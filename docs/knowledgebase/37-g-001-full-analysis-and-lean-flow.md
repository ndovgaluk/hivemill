# 37. G-001 measured end to end, and a leaner factory flow

Written 2026-11-13 for TSR task HM-4. Sources: the factory database of the live home, the agents' session transcripts and the merged code on `main`, all read-only. Every figure says whether it is measured or an estimate. Costs use the price table in `web/prices.py` (dated 2026-10-25); they are list prices, not a bill.

## Q: Analyse the entire process of the completed goal, and propose a flow that reaches the goal faster with far fewer interactions. Quality of implementation and speed of delivery are the top criteria; resources are not.

Short answer: G-001 spent half of its money and most of its messages on coordination, not on building or checking. A flow where code does the routing, the design is frozen before the first coder starts, and one builder and one reviewer keep their context until merge should bring a goal of this size from about 9 hours to an estimated 2.5 to 4, and from 253 messages to about 30. It fits inside Hivemill as a second workflow; an own factory is the fallback, not the first step.

## 1. What G-001 produced (measured)

| | |
|---|---|
| Goal | Opt-in worktree reuse for coder tasks |
| Wall time | 8h 55m (23:35 to 08:31) |
| Merged | 8 PRs, 18 files, 2,207 lines added, 57 removed |
| Of that | 689 lines in `bin/factory_cli.py`, about 1,450 lines of tests, 70 lines of docs |
| Factory tasks | 11: 1 plan, 4 build, 4 follow-ups, 2 audits |

## 2. What it took (measured)

| | Count |
|---|---|
| Messages between agents | 253 (165,557 characters) |
| Events in the window | 519 (the flow debugger shows 489 on its timeline) |
| Agent sessions started | 67: coder 22, reviewer 15, QA 13, judge 8, pm 3, staff-engineer 2, lead 2, cleaner 2 |
| Model requests | 4,060 |
| Spec or acceptance updates on running tasks | 90 (T-0004: 22, T-0002: 19, T-0003: 15) |
| Verdicts | reviewer 10 pass / 6 fail, QA 10 pass / 3 fail, judge 8 merges |
| List-price cost | about 129 USD |

That is about 16 USD and 32 messages per merged PR.

### Who talked to whom

| From → to | Messages | What they were |
|---|---|---|
| lead → director | 48 | 44 status reports, 3 escalations |
| director → lead | 31 | 17 requests, 13 decisions |
| workers → lead (coder 24, reviewer 19, QA 13, judge 8, pm 5) | 69 | "finished" reports and verdict notices |
| factory → workers | 62 | kickoff messages, one per spawn |
| lead → coder | 16 | 8 of them are "STOP" |
| director → boss | 13 | progress reports for the owner |

The lead and the director exchanged 79 messages, almost a third of all traffic. None of them is code or a verdict.

### Where the money went

| Role | Model | Requests | Cost (USD) |
|---|---|---|---|
| Reviewer (incl. its Sonnet sub-sessions) | Opus 5.5 | 752 | 29.70 |
| Lead | Opus 5.5 | 636 | 27.43 |
| Coder | Sonnet 5.5 | 1,281 | 25.73 |
| Director | Opus 5.5 | 485 | 16.74 |
| Judge | Opus 5.5 | 157 | 8.64 |
| PM | Opus 5.5 | 132 | 7.55 |
| QA | Sonnet 5.5 | 454 | 7.42 |
| Staff-engineer | Opus 5.5 | 56 | 3.85 |
| Other (boss, cleaner, scout, unattributed) | | 107 | 1.94 |

- Coordination (lead, director, boss, pm, judge, staff-engineer): about 64 USD, **50%**.
- Checking (reviewer, QA): about 37 USD, 29%.
- Building (coder): about 26 USD, 20%.

Why coordination is so expensive: the lead answered 636 requests with an average context of about 131,000 tokens, the director 485 with about 119,000. Every status message is handled as a full-context turn.

The judge cost 8.64 USD for 8 merges whose inputs (two passing verdicts and green checks) are all in the database.

### Where the time went

- Coder sessions total 596 minutes over 21 sessions, partly in parallel. The three runs that produced the first PRs took 23, 31 and 44 minutes. The rest is rework and restarts; five sessions lasted 5 minutes or less.
- Checking is fast: a reviewer session averages 4 minutes, QA 7, the judge under 1.
- So the wall time is rework and waiting, not review. The causes are in file 31: specs rewritten while coders ran, acceptance added after a PR was open, the design for the hard part arriving after two failed attempts, rejections for the PR description only, a box that was not ready, rulings landing mid-review.
- Every one of the 67 sessions started from zero at about 45,000 tokens and had to rebuild its understanding (file 36).

## 3. The pattern behind the numbers

1. **Agents route work that code could route.** "Coder finished", "verdict recorded", "spawn the reviewer", "merge" are state changes. In G-001 each went through the lead as a message, and many were then reported to the director.
2. **Thinking happened late and in pieces.** The plan took 7 minutes; the design that settled the hard part came three hours in. In between, 90 spec updates steered coders that were already running.
3. **Context was thrown away 67 times.** A rejected coder was replaced by a new one that knew only the findings and the code.
4. **Review found the bug class one variant per round.** Four of the rejections were the same class (redirecting git through the worktree's `.git`).
5. **Format problems cost full rounds.** Two rejections were for the PR description only.

## 4. The proposed flow

Design rules, in order of effect:

1. **Code orchestrates; agents think, build and review.** A state machine in the factory moves each factory task: planned → building → checks → review → fixing → merged. Agents never ask each other to start, stop or report.
2. **Design first, then freeze.** Nothing is built until the design and the acceptance criteria are written and, for risky areas, attacked once.
3. **One builder and one reviewer per work stream, kept until merge.** Their sessions are resumed by id on each round, with their context.
4. **Findings go straight from reviewer to builder.** The thinker is called only when something does not converge.
5. **Everything mechanical is done by code:** preflight, PR text, the merge, the reports to the owner.

### Roles and models

| Role | Model | Lives | Does |
|---|---|---|---|
| Architect (replaces pm, lead, staff-engineer for the goal) | Fable 5.2 | one session per goal, woken by events | design, plan, frozen acceptance; answers escalations; final audit |
| Builder | Opus 5.5 | one session per work stream, resumed until merge | implements, tests, fixes findings |
| Reviewer (reviewer and QA in one) | Opus 5.5 | one session per work stream, resumed until merge | code review, runs the tests, walks the acceptance list; fans out parallel angle checks on risky PRs |
| Orchestrator | code | always | routing, preflight, checks, merge, reports |

The boss stays as the owner's contact. Director, lead, pm, judge and the separate QA have no part in this flow.

### The steps

1. **Preflight (code, seconds).** Git identity, toolchains, base branch, CI reachable. A failure stops the goal before any agent starts.
2. **Design (architect, about 20 to 30 minutes).** Reads the code, writes the design, the work streams with the files each may touch, and the acceptance criteria. For anything touching spawn, clean, isolation or the guard it starts a second Fable session whose only job is to break the design, and folds the result in. Then the spec is frozen.
3. **Build (builder).** One stream at a time unless the architect marked streams as independent. The builder keeps its context across the stream's factory tasks.
4. **Checks (code).** Lint, affected tests, PR check, and a PR description generated from the task record. The reviewer is not started on a red result.
5. **Review (reviewer, one pass).** Review, tests and acceptance walk together. The verdict is a structured list of every blocking finding; for a bug class the reviewer must list the variants it can think of, not the first one.
6. **Fix loop (code routes).** A failed verdict resumes the builder session with the findings. A new push resumes the same reviewer session, which checks its own findings and the delta. No agent in between.
7. **Escalation (architect).** Only when a second round fails on the same finding class, the builder reports a gap in the spec, or two streams collide. A spec change is a recorded change request that pauses the builder.
8. **Merge (code).** Passing verdict and green required checks merge the PR. No judge session.
9. **Audit (architect, once).** Every success criterion against evidence, as today.
10. **Owner reports (code).** Generated from the database.

### Keeping context until merge

Sessions are not kept running. The pane is closed as today and the session is resumed by its id when its next step comes. The transcript is on disk, and the prompt cache lasts an hour (file 36), so a round that comes back within the hour starts warm. This gives the context without holding one of the live-agent slots.

### Interactions for a goal shaped like G-001

| Step | Messages |
|---|---|
| Brief to the architect, plan back | 2 |
| Per build stream (4): start, done, verdict | 12 |
| Fix rounds, 1.5 per stream on average: findings, fixed, verdict | about 12 |
| Escalations to the architect | about 3 |
| Audit and close | 2 |
| **Total** | **about 30, against 253** |

Sessions: 1 architect, 1 or 2 builders, 1 or 2 reviewers, plus the design attacker: 4 to 6, against 67.

### Expected time (estimate)

Built from G-001's own measured pieces: design 20 to 30 minutes; first-pass building about 100 to 120 minutes for the same code; four reviews at 10 to 15 minutes; about three fix rounds at 20 minutes. Sequential that is 3.5 to 4 hours; with two independent streams after the shared base, about 2.5 to 3. Against 8h 55m.

This assumes the frozen design removes the respawns and that Opus 5.5 as builder needs fewer rounds than Sonnet 5.5 did. Neither is proven; G-001 only shows that the reviewer on Opus kept finding what the coder on Sonnet missed.

### Cost

Not a criterion here. Fable 5.2 is not in the repository's price table, so no figure is given. Direction: the 64 USD of coordination mostly disappears, the builder's tokens cost twice as much per token on Opus as on Sonnet, and resumed sessions carry larger contexts (file 36).

### What protects quality

- The design is attacked before code exists, which is where G-001 lost the most.
- The reviewer is a different session from the builder and never sees the builder's reasoning, only the code and the acceptance list.
- Risky PRs still get the parallel angle review that exists today (`multi-angle-review`).
- The merge rule is unchanged in substance: an independent passing verdict and green required checks.
- The limit on rounds stays, with the architect instead of the director deciding on more (see HM-2).

## 5. Case 1: inside Hivemill

Hivemill's paradigm is agents coordinating by messages, with the tick nudging them. The proposed flow is code coordinating, with agents working. Hivemill has been moving that way, so most pieces exist:

| Needed | In Hivemill today |
|---|---|
| Start review when a PR opens | `review_autospawn` (off here): the tick starts reviewer and QA, or one combined agent for the low CI tiers |
| Resume the same coder session | `coder_ci_handoff` has a `resume` mode (off here); `factory relaunch` resumes |
| Merge without a judging agent | a mechanical merge path exists in the judge code; on G-001 a judge agent was still spawned 8 times |
| Parallel review angles | the `multi-angle-review` workflow |
| A design role | staff-engineer |
| Model per role | the `MODELS` table in the CLI code; only the cleaner has a config override (`model_cleaner`); `factory spawn --model` sets it for one spawn |
| Guard, sandbox, git hardening, cost data, flow debugger | all present |

What has to be built:

1. A workflow chosen per goal (TSR story DVDG-565).
2. The fix loop in the tick: failed verdict → resume the builder with the findings → push → resume the reviewer.
3. Resume by session id for workers on a retry (today every `factory spawn` is a fresh session).
4. One combined verdict accepted by the merge gate for this workflow.
5. An architect role that plans and audits, and worker starts that need no lead.
6. Spec freeze enforced by the CLI: no spec or acceptance update while a builder is live or a PR is open, except as a change request.
7. Owner reports from the database.
8. Fable allowed as a model: the code comment on the model table says "Never Fable (owner rule)", which this request reverses. Whether the config accepts a Fable id was not checked.

What does not fit well:

- Every change to the gate, spawn or the schema is a "risky path": full test suite, and for guard changes a rejecting and an accepting test.
- All of it lands in one 18,500-line file that upstream keeps changing, so the fork will collect merge conflicts.
- The guard and the sandbox are written around the current role names.

Available today without code, as a first step:

- `factory config review_autospawn on`
- `factory config coder_ci_handoff resume`
- factory lessons for the four rules from file 31 (no spec change while a worker runs, design first for risky areas, PR check before review, preflight).

These remove part of the chatter, not most of it: the lead and director still relay.

Corrected the same day: an earlier version listed `factory config model_coder claude-opus-5-5` here. That key does not exist. `role_model` reads a config override only for keys present in `DEFAULT_CONFIG`, and only `model_cleaner` is. Putting the coder on Opus 5.5 is a one-line change to the `MODELS` table in `bin/factory_cli.py` (a code change, through a PR), or `--model` on each spawn.

## 6. Case 2: an own factory on herdr

A small orchestrator, in Go. Go because the box already has the toolchain, Hivemill's worker guard already exists in Go and can be reused as it is, and a daemon with a state machine and subprocesses is plain Go. Rust would add nothing here that the task needs.

| Part | What it is |
|---|---|
| Engine | one binary; SQLite; workflows as data (states, who acts, limits, hooks), which is also what the visual designer (DVDG-567) needs |
| Sessions | starts and resumes Claude Code sessions in herdr panes, so they stay watchable; tracks session ids and idle state |
| Agent outputs | typed, through a small CLI: plan, done, verdict with findings, question. No free-form mail between agents |
| Git and GitHub | `gh` for PRs, a CI watcher, the merge |
| Guard | Hivemill's Go worker guard as the pre-tool hook (MIT licence) |
| UI | the flow debugger React app, fed the same flow JSON |

What it loses: the hardening Hivemill earned over more than a thousand factory tasks: the guard corpus, the worker sandbox, git hardening, stale-base handling, the spawn queue and resource gate, the public-text scans, the two-runtime orgs, the CI tiers. Each would be met again as an incident.

Size, as a judgement and not a measurement: a first version with one workflow, one project and no sandbox is weeks of work, and it would be less safe than Hivemill at the start.

Not verified on this box: that Claude Code sessions can be resumed non-interactively inside the factory's guard and settings; herdr's interface for driving panes.

## 7. Recommendation

Case 1, in two steps.

1. **Now:** the config switches and lessons above, and the models. Run one goal of comparable size and read it in the flow debugger.
2. **Then:** build the lean workflow inside Hivemill as DVDG-565, with this file as its design input.

Move to Case 2 if, after step 2, a factory task still needs more than about 10 messages, if the fork's gate and spawn code conflicts with upstream on most merges, or when the workflow designer (DVDG-567) needs workflows as data that the single-file CLI cannot host cleanly.

With quality and speed as the criteria, Case 1 also wins on delivery: it improves the next goal within days, on a base that is already hardened.

## Not done

- The 253 messages were counted and their subjects read; their bodies were not read in full.
- The split of wall time into "working" and "waiting" per factory task was not computed.
- No comparable goal was run under any of the proposed settings.
- Costs attribute sessions to roles by the agent name found in each session's first messages; 8 small sessions could not be attributed (1.44 USD).

## Q: Create a branch from the place before G-001 was committed; G-001 becomes the reference goal for other workflows

Done on 2026-11-13.

- Branch `baseline/pre-g-001` on the fork, at commit `8d616f6e2a83ba3246d2d4abbd4c5caf78d14450` ("T-1368: write-mode golden harness, Deps for writes, pyFloatRepr (#586)"). It is the parent of `90a2af3`, the first G-001 merge (T-0002, 00:59).
- Checked: the commit is an ancestor of `main`; `bin/factory_cli.py` at that commit has no `worktree_reuse`; all 8 G-001 merges come after it.
- The goal text the owner gave the boss, the branch and the original run's numbers are kept in TSR task HM-5, so every comparison run uses the same input.

Open: the Hivemill project is the factory's own repository and its `main` already holds the G-001 result. A comparison run needs the project worked on from `baseline/pre-g-001` while the factory runs current code, for example a second registered project on a separate clone with that branch as base. Not decided or tested.

## Q: What is the recommendation for improving the current approach? Do we need alternative agent definitions and rules, CLI changes, database changes, different models?

Yes to all four, in very different amounts. The CLI is where most of the work is. Agent definitions need a small second set, the database needs one or two columns, and the models are a few lines. Keep the current workflow as it is and add the lean one beside it, so the two can be compared on the reference goal (HM-5).

### Agent definitions and rules: yes, a small second set

- **One new role, the architect.** It plans, freezes the acceptance criteria, answers escalations and audits. It replaces pm, lead and staff-engineer for a goal that runs the lean workflow.
- **Keep the role names `coder` and `reviewer`**, with workflow-specific rules. The worker guard, the permission templates and the sandbox are keyed on role names, so new names would mean re-earning that protection. The builder is a `coder` with different rules; the lean reviewer is a `reviewer` that also does QA's job.
- **The rules go into role skills, not into the prompts.** `_common.md` plus `coder.md` is at the byte target already (file 35).
- **The rules that matter**, each from a measured G-001 problem:
  - builder: check the PR text and the tests before asking for review; report a spec gap to the architect and do not work around it;
  - reviewer: one pass with every blocking finding; for a class of bug, list the variants, not the first one; on a later round, check your own findings and the delta;
  - architect: no code before the design and acceptance are frozen; have the design attacked once for spawn, clean, isolation or guard changes; a spec change is a recorded change request.
- **For the current workflow, right now:** four factory lessons (file 31). They cost nothing and apply to newly spawned agents.

### CLI: yes, this is the main work

| Change | Why |
|---|---|
| A workflow chosen per goal | lets both workflows exist; TSR story DVDG-565 |
| The fix loop in the tick: failed verdict → resume the builder with the findings → push → resume the reviewer | removes the lead as relay: 69 worker-to-lead and 16 lead-to-coder messages on G-001 |
| Resume by session id when a worker is started again | keeps context until merge; today every `factory spawn` is a fresh session |
| One combined verdict accepted by the merge gate, and a merge without a judging agent | removes 13 QA and 8 judge sessions |
| Spec freeze: refuse spec or acceptance updates while a builder is live or a PR is open, unless it is a change request | 90 such updates on G-001 |
| Preflight before a goal starts | the missing git identity and toolchain |
| Owner reports from the database | removes most of the 79 lead and director messages |

All of these touch spawn, the gate or the tick, which the project treats as risky paths: full test suite, and a rejecting and an accepting test for each new refusal.

Without any CLI change only two switches are available: `review_autospawn on` and `coder_ci_handoff resume`. Their documentation should be read before turning them on; that was not done here.

### Database: small

- **`goals.workflow`**, one new column. A `workflows` table comes later with the designer (DVDG-567).
- **Probably one column on tasks** marking the spec as frozen. Change requests can be messages of a new kind.
- **Nothing for resume:** each agent row already keeps its session id.
- **Nothing for findings at first:** the verdict's summary text is enough, and a recent change (DVDG-569) already makes a failed verdict's summary a self-contained rework brief.

No restructuring is needed.

### Models: yes

| Role | Today | Recommended |
|---|---|---|
| Architect (new) | lead, pm, staff-engineer on Opus 5.5 | Fable 5.2 |
| Builder (`coder`) | Sonnet 5.5 | Opus 5.5 |
| Reviewer (with QA's job) | Opus 5.5; QA on Sonnet 5.5 | Opus 5.5 |

- The coder change is worth making in the current workflow too. On G-001 the reviewer on Opus rejected the coder on Sonnet 6 times and QA 3 times, four of them for one class of bug. That is an observation, not proof that Opus would have avoided them.
- It is a code change: the `MODELS` table in `bin/factory_cli.py`. Only the cleaner has a config override.
- Fable for the architect reverses the comment on that table, "Never Fable (owner rule)". Whether the factory's Claude Code accepts a Fable model id for an agent was not checked.

### Order

1. Now, no code: the four lessons; read the docs of the two switches and turn them on if they hold up.
2. A small PR: the coder on Opus 5.5.
3. The lean workflow (DVDG-565): architect role, rule skills, the CLI changes above, the two columns.
4. Run the reference goal (HM-5) on both workflows and compare.

Steps 1 and 2 improve the current approach but keep its shape. Step 3 is what removes the interactions.

## Q: Owner requirements for the workflows (2026-11-13), and where they are recorded

The owner's direction after reading the recommendation:

1. Several workflows: for simple, medium and huge tasks. They may differ; selection must be available.
2. For now they are hardcoded in the filesystem, the way the main workflow is.
3. The workflow is normally chosen from the complexity of the assigned task; the owner can tell the boss which one to use.
4. The owner tells the boss which Taskosaur task to pick up. An enriched task needs no architecture step.
5. The architect breaks a task down the way the `working-with-taskosaur` skill does, and one agent executes the children sequentially.
6. The reviewer checks each child independently once it is In Review. QA starts when all children of the story are In Review.
7. A child reviewed by the agent is marked in Taskosaur as reviewed by agent, so the Taskosaur app needs a change.
8. Tight integration with Taskosaur and its task decomposition.

Recorded in TSR:

- **TSK-590** (new, Taskosaur epic): the "Reviewed by agent" mark, set through MCP, shown on cards and in task details, separate from the owner's "Mark reviewed". Four open questions.
- **DVDG-565** (workflows), comment: the requirements above and seven questions for its grilling, with proposed starting answers (XS and S → simple, M → medium, L and XL → huge; a rejected child is fixed after the current child; one branch per story).
- **DVDG-545** (TSR integration), comment: Taskosaur becomes an input and a working surface, not only a mirror. This conflicts with DVDG-546, which denies every agent the TSR token; reading tasks and writing children would have to go through a factory CLI command that holds the token.

Nothing is implemented. No new Hivemill story was created for the integration; the existing one was extended by comment.

## Q: Owner constraint: extend Hivemill as safely as possible, so upstream changes do not affect the extensions

Recorded on DVDG-565 as a design rule: extend beside, do not rewrite inside. Upstream keeps changing `bin/factory_cli.py`, the role prompts and the tests, so every changed line there is a future merge conflict.

1. New code in new files: workflow engine, fix loop, TSR client and workflow definitions in their own package, loaded the way the CLI already loads the `scout/` modules (`_LazyScout`).
2. Few, small seams in `factory_cli.py`: one-line calls at goal creation, the tick, spawn and the merge gate that hand over only when a goal has a non-default workflow. The seams are listed in the feature doc.
3. The default path stays exactly as upstream; everything new is opt-in.
4. New role files and skills, no edits to upstream's prompts.
5. Additive database changes only: new tables, new nullable columns.
6. New config keys under their own prefix.
7. Own test files, plus one test that fails when a seam disappears after an upstream merge.
8. Existing role names are reused for agents where possible, so the guard, permission templates and sandbox need no edit.

This also applies backwards: commit `e623cab` edits `roles/coder.md` in place and shortens existing wording. Under this rule the pointer to `worktree-postinit-rules.md` belongs in a new skill or the project's own instructions.

Whether a lazily loaded package can take over at those four points without larger edits was not checked in the code.

## Q: Hivemill records no design for a task's implementation during the workflow; we need the TSR approach, with all implementation details in the tasks, planned by a higher thinking model

Mostly right, checked on G-001 (read-only):

- Hivemill does keep a goal plan: table `plans`, two versions, about 7,500 characters each.
- Each factory task has a `spec` and an `acceptance` text, but only the current version. T-0004's spec was updated 22 times and the update events carry no text, so the earlier versions are gone.
- The design for the hard part exists only as messages: the staff-engineer's designs are messages M62 (7,543 characters) and M125 (6,599 characters) to the lead. Decisions are messages as well.
- What was built and how it was checked is in the PR body and the one-line `factory done` summary.

So there is a plan and a spec, but no durable design per task, no history of how the spec changed, and the reasoning is spread over 253 messages. A new coder session gets the current spec and the findings, not the reasoning.

Rule recorded on DVDG-565 for the new workflows: the Taskosaur task is the single record of a piece of work, written by the planning model before any code.

1. A description complete enough for a fresh agent: goal, context, the design and its reasons, contract, files, edge cases and risks, acceptance criteria, how to verify, dependencies (the `working-with-taskosaur` template).
2. Tests designed up front for anything a user sees.
3. A design change is a visible edit plus a comment saying what changed and why; a builder that finds a gap asks, and does not redesign.
4. Each agent comments its own work on the task: builder, reviewer (with the "reviewed by agent" mark, TSK-590), QA.
5. Commits are linked to the task.
6. The factory database keeps the run state and points at the TSR task; it holds no second copy of the design.

Open: for a goal that starts as plain text to the boss (the reference goal, HM-5), the architect would create the TSR story and children first. Proposed yes; not decided.

## Q: How will Hivemill talk to Taskosaur, API or MCP, and who sets the agent marks?

Owner (2026-11-13): either channel, the design decides; the account Hivemill acts as will be allowed to set "Reviewed by agent" and "Tested by agent".

Design choice, recorded on DVDG-545 for its grilling: the REST API, called by the factory CLI, with no MCP client in Hivemill.

- Hivemill is Python standard library only. A REST call is a few lines of `urllib`; MCP would need a protocol client.
- The existing sync story already plans REST calls from the tick, so there is one channel, one token and one place for retries.
- The token stays with the CLI. Agents never read it; they call factory commands (for example `factory tsr show KEY`, `factory tsr child add`, `factory tsr mark reviewed KEY --result passed`) and the CLI makes the request.
- The client and the `tsr` commands live in their own module with one registration seam, following the "extend beside upstream" rule.

Proposed, not decided: the reviewer's mark is set by the orchestrator when the verdict is recorded, not by the reviewing agent's own command, so no agent can mark its own work even though Taskosaur itself does not block that (TSK-590, decision 3). Open: which factory roles may call which `tsr` command.

On the Taskosaur side (TSK-590) the REST endpoint for the marks is therefore required; the MCP tool serves Claude Code sessions.

## Q: A merged task is marked Done. What happens when another merge conflicts with the task in progress, and who resolves it?

Owner direction of 2026-11-13; the design below is proposed on DVDG-565 and not yet confirmed.

### Done

After the merge is verified on the base branch, the orchestrator (code, through the factory's TSR client) links the commit to the TSR task, writes the closing comment and moves the task to Done. With one branch per story, every child and the story go to Done together. In Review means built and waiting for review, QA and merge; Done means merged.

### What Hivemill already does (`docs/staleness.md`, `docs/verdict-carry-over.md`, `docs/refresh.md`)

- A head that is only behind the base branch and merges cleanly is refreshed mechanically (`factory refresh`); a passing verdict carries over a pure merge of the base branch.
- A head that conflicts gets `CONFLICT-ONLY`: a merge-only coder, then a delta reviewer and QA on the conflict hunks. It is not counted as an attempt.

The new flow keeps these and changes who resolves and when.

### Rules

1. Within one story there are no conflicts: one builder, one branch, children in sequence.
2. Prevent across stories: the architect lists the files and areas a story touches in the TSR story; before a second story of the same project starts, the orchestrator compares the lists, and overlapping stories run one after the other unless told otherwise.
3. Merges are serialised: one merge at a time per project; after each merge the next candidate is refreshed and its checks re-run before it may merge.
4. Detect early: after every merge to the base branch (another story, another goal, or the owner pulling upstream) the orchestrator test-merges every open story branch of the project. Clean and checks green → mechanical refresh, verdicts and marks stay. Clean but checks red (the texts merge, the behaviour breaks) → treated like a conflict. Conflict → rule 5.
5. The resolver is the builder of the story that has not merged yet. Its work must fit the new base, and its resumed session has the reasoning for its own change. It gets the conflicting files and the TSR task of the work that merged first, so it reads the other side's design instead of guessing.
6. When: at the next child boundary; if the story is already waiting for review, QA or merge, its builder session is resumed.
7. Never the resolver: the reviewer, QA, the orchestrator beyond a clean merge, and the builder of the work that already merged. If the right fix is in the merged code, the architect creates a follow-up task.
8. After a resolution: the same reviewer session re-reviews the conflict hunks and what depends on them; QA re-runs the story's tests. Only children whose files were in the conflict lose their "reviewed" and "tested" marks.
9. In TSR an affected child goes back to In Progress with a comment naming the merged task and the files, the two tasks are linked, and it returns to In Review after the resolution.
10. Escalation: when resolving would change the design of either side, or two resolution rounds fail, the architect decides (redesign, re-order, follow-up task).

### Consequences

- The later story pays for the conflict; frequent refreshes keep that cost small and early.
- Serialised merges cost one re-run of the checks per merge, which is cheaper than a red base branch that stops every story.
- Losing some review marks after a conflict is intended: a mark must describe the code that will merge.

Open: whether overlapping stories should default to running in sequence; and the rules assume one PR per story.

## Q: Explain the two open points: overlapping stories in sequence or in parallel, and one PR per story or per child

### Point 1: two stories that touch the same files

Example: story A adds worktree reuse and changes the spawn code in `bin/factory_cli.py`. Story B adds a settings page and changes `web/server.py`. They share no files and can run at the same time. Now story C changes the cleanup code in `bin/factory_cli.py`, close to what A is changing. A and C overlap.

- **In sequence (the proposed default):** C waits until A is merged, then starts from a base that already contains A. No conflict can happen, and C's builder sees A's final code. The cost is waiting: if A takes three hours, C starts three hours late.
- **In parallel:** A and C start together. Whichever merges second gets a conflict or a broken test, and its builder has to stop, read the other story's design and rework part of its code. Review marks on the affected children are lost and those children are reviewed again. The gain is that both stories are being built at once.

G-001 shows what parallel overlap costs: its T-0003 and T-0004 ran in parallel and both needed the same ownership check. One of them was stopped 53 minutes into an attempt and parked behind the other.

Recommendation: sequence by default, because the owner's first criterion is quality and a conflict resolved under time pressure is where quality slips. The architect or the owner can mark two overlapping stories as safe to run together when the overlap is trivial (both add a line to the same list, for example).

What decides it: how often stories in one project overlap. If most do, sequencing turns the factory into a single lane and the parallel option matters more.

### Point 2: how much goes into one pull request

A story has, say, five children.

- **One PR per story (assumed in the rules):** the builder works all five children on one branch. The reviewer reads each child as it reaches In Review, by looking at that child's commits on the branch. QA tests the whole branch when all five are In Review. Then one merge. Children 2 to 5 can build on child 1 without waiting for anything, the base branch only ever receives a complete, tested feature, and there is one merge to queue. The cost is a larger PR, and nothing from the story is on the base branch until the end.
- **One PR per child:** each child is merged as soon as it is reviewed. Smaller PRs, and other stories see the work sooner. But child 2 usually needs child 1's code, so either it waits for child 1's merge or its branch is stacked on child 1's branch and has to be re-based when child 1 changes in review. QA "after all children are In Review" then tests code that is already merged, so a QA failure means a fix on the base branch, not a held-back PR. And there are five merges to queue, each re-running the checks.

G-001 used one PR per factory task. It needed four follow-up factory tasks and PRs for things found after earlier ones had merged.

Recommendation: one PR per story. It matches the requirement that QA starts when all children are In Review, and it keeps the base branch free of half-finished features. For a huge story the architect can cut it into two or three stories that each merge on their own, which gives earlier merges without stacking.

Decided by the owner on 2026-11-13: overlapping stories run **in sequence** by default; the architect or the owner can mark an overlap as safe to run in parallel. One PR per story or per child is not answered yet.

Decided by the owner on 2026-11-13: **one PR per story.** The builder works all children on one branch; the reviewer reads each child from its commits; QA tests the branch when all children are In Review; one merge, after which all children and the story are Done. A huge story is cut into several stories that merge separately. Consequence: the builder commits per child, with the child's TSR key in the commit subject, so a child can be reviewed and its commits linked on their own.
