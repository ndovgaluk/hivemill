# 41. Workflow engine in Go: code facts and the build plan

Written 2026-11-14 for TSR story DVDG-565, after the owner chose Go for the engine. The facts come from two read-only code readings of the installed factory (`main` at `a617aa4`) by subagents, spot-checked by the session at the lines marked "checked". `F` = `bin/factory_cli.py`.

## Facts the plan rests on

| Fact | Where |
|---|---|
| A factory task owns one branch `factory/{task id}`, one worktree `{goal}-{task}` and one PR; review, CI restart, verdicts, judge and merge are all per task | `prepare_worktree` F:9625-9705; `cmd_verdict` F:4921; candidates F:17887, 18169, 15471 |
| Two tasks cannot share a branch or PR cleanly; there is no parent-task column | report 1, section 2 |
| The tick runs with owner rights and needs no lead or director alive | `cmd_tick` calls only `refuse_worker`; `factory-tick.service` sets no agent identity |
| The owner passes every role check | `require_role`, F:1132 |
| `factory spawn {role} --goal --task --name --cwd --prompt --model` exists; there is no `--resume` flag (checked) | F:19899-19908; `cmd_spawn` F:11169 |
| `factory task add` needs role pm, lead or director, or the owner (checked) | `cmd_task` F:3852 |
| A coder also gets the skills folder `roles/plugins/goals/{goal id}` when it exists (checked) | `GOAL_PLUGINS` F:56, 10936 |
| With `review_autospawn=on` the tick starts reviewer and QA (or one combined agent for tiers T0 and T1) on an open PR; a PASS verdict must name the PR head | F:18046-18111; F:4933-4946 |
| The merge gate needs a reviewer PASS and a QA PASS on the current head, green checks, and more | `_judge_gate_and_merge` F:6087-6327 |
| `tick_mech_merge` is the pattern for a tick step that launches a detached program (checked) | F:6606-6617 |
| `build_guard_go(src, lib, tick, go, name, pkg)` builds any Go command of the repo into `~/.local/lib/factory/{name}` with a stamp (checked) | F:2810 |
| Go: module `factory/go`, Go 1.27, one dependency `modernc.org/sqlite` (pure Go, no cgo); `factorydb.Open` opens `factory.db` read-write, never creates it, requires `user_version` 2 | `go/go.mod`; `go/internal/factorydb/factorydb.go:51-81` |
| A new table or column in `factory.db` means bumping `SCHEMA_VERSION`, the Go `SchemaVersion`, a hash pin and golden files | F:396-399; `tests/test_db_layout.py:87-90` |
| A new key in `DEFAULT_CONFIG` means regenerating `go/internal/cli/defaults_gen.go` and golden outputs | `go/internal/cli/cli_test.go:412-428` |
| "No new Python files" is enforced by prompts only; the check `go/cmd/no-new-python` is wired into no CI job | report 2, section 5 |
| No Go code uses `net/http` yet; token files are checked as regular, mode 0600, owned by the user | report 2, section 7; `_token_file_ok` F:10135-10142 |
| Taskosaur: a personal access token starts with `tsr_pat_` and is sent as `Authorization: Bearer …`; routes `GET /tasks/key/:key`, `GET /tasks?parentTaskId=`, `PATCH /tasks/:id/status`, `PATCH /tasks/:id/agent-check` (`kind` REVIEW or QA, `result` PASSED, FAILED or null, `agentName`, `ref`), `POST /task-comments` (`taskId`, `content`), `POST /task-commits` | Taskosaur `backend/src`, `master` at `22ad34c` (checked) |

## Design chosen from these facts (the session's, for the owner to confirm in the grilling task DVDG-566)

1. **One Taskosaur story is one factory task with one PR.** Its children exist only in Taskosaur. The existing review, merge gate and merger run unchanged at the end of the story, on the one PR.
2. **The engine is a separate Go program**, `go/cmd/workflow` with `go/internal/workflow`, built to `factory-workflow`, started by one new tick step and reachable as `factory wf …`.
3. **The engine keeps its state in its own database file**, `db/workflow.db`, and only reads `factory.db` (it writes events through the exported `identity.Env.EventAs`). So `factory.db` gets no new table or column, and upstream's schema version, hash pin and schema goldens stay untouched.
4. **Four seams in upstream's `bin/factory_cli.py`:** one config key `workflow_engine` (off by default), the build call in `guard_tick`, the tick step, the `wf` command. Everything else is new files.
5. **Per-child review is done by the engine**, not by the factory's PR review: when a child is In Review in Taskosaur the engine starts a reviewer on the story's worktree for that child's commits, records the result as the Taskosaur mark, and sends findings to the builder. Each child review is a fresh reviewer session in this first version, because `factory spawn` cannot resume one.
6. **Builder and reviewer rules live in skills**, in the per-goal skills folder for the builder and in the kickoff text for the reviewer; upstream's role prompts are not edited.

## Tasks created under DVDG-565

See the story's "Execution order". Not written yet, listed there as later work: the architect step (readiness check, design, split), QA for the huge workflow before the PR, the merge queue and conflict rules, and estimation.

## Q: Please explain each of the five questions for the grilling. (2026-11-14)

Each is a choice about how the new workflow behaves. For each: the situation, the options, what is proposed and why, and what the choice costs.

### 1. A child is rejected while the builder is already ahead: when is it fixed?

Situation: a story has children A, B, C, D. The builder finished A and is half-way through B when the reviewer rejects A.

| Option | What happens | Cost |
|---|---|---|
| At once | The builder drops B, fixes A, returns to B | B is left half-done on the branch; the builder switches context twice |
| After the child in hand, before the next (proposed) | The builder finishes B, fixes A, then starts C | A waits a little; nothing is left half-done |
| At the end | A is fixed after D | C and D may be built on A's mistake and need rework |

Proposed: the middle one. It never interrupts work in progress and never lets a known fault sit under two more children.

### 2. A goal given as plain text: is a Taskosaur story created first?

Situation: the owner tells the boss "add an option X to the CLI" as free text, with no Taskosaur task, as with the reference goal.

The rule already decided is that the Taskosaur task is the single record of the design and the work. A text goal has no task to hold that record.

| Option | What happens | Cost |
|---|---|---|
| A story is created first (proposed) | The request becomes a Taskosaur story with children, written from the code, then the run starts from it | A planning step before any code; needs the architect step, which is not built yet |
| Run straight from the text | The builder works from the sentence | No design is recorded, no children to review one by one: the problem seen in G-001 |

Proposed: create the story first. Until the architect step exists, the first version only accepts a story that already exists and is enriched; a text goal is refused with a message.

### 3. Which roles may call which Taskosaur command?

Situation: factory agents cannot use the Taskosaur connection the owner's sessions use; they get a few `factory wf tsr` commands, and the engine holds the one access token. The question is how much each agent may do.

| Action | Builder | Reviewer | QA | Architect | Boss | Engine only |
|---|---|---|---|---|---|---|
| Read a task and its children | yes | yes | yes | yes | yes | |
| Add a comment | yes | yes | yes | yes | | |
| Move a child to In Progress or In Review | yes | | | | | |
| Set the "reviewed" or "tested" mark | | | | | | yes |
| Move to Done, link commits | | | | | | yes |

Proposed: as in the table. The marks and Done are set by the engine from what the agents reported, so an agent cannot mark its own work as reviewed or finished by mistake. The alternative, letting agents do everything, is simpler to build and gives up that check.

### 4. The final review of the whole PR repeats part of the per-child reviews: acceptable?

Situation: each child is reviewed on its own commits while the story is being built. At the end one PR is opened, and the factory's existing gate reviews and tests that PR again before merging.

| Option | What happens | Cost |
|---|---|---|
| Keep the existing final review and merge gate (proposed) | Per-child reviews catch problems early; the final review looks at the whole and the tests run on the result | Some code is read twice; one more reviewer session per story |
| Trust the per-child reviews and merge without a final review | Faster at the end | The rule for what may merge would be new code in the most sensitive place, and nobody looks at how the children fit together |

Proposed: keep the final review for the first version. Quality is the first criterion, it adds no CI wait (CI runs once either way), and it leaves upstream's merge rules untouched. It can be slimmed later with evidence from real runs.

### 5. Each child review is a fresh reviewer session: acceptable?

Situation: the earlier design said one reviewer per story, "resumed for each child", so it remembers the story and its earlier findings. The factory's `spawn` command cannot resume a session; only one internal path (restarting a coder on red CI) can.

| Option | What happens | Cost |
|---|---|---|
| A fresh reviewer per child and per round (proposed) | Each review starts clean and reads the child's task and commits | The reviewer re-reads context each time (about 45,000 tokens per start, measured earlier); it does not remember its earlier findings, so the engine hands them over in the kickoff |
| One reviewer resumed across the story | Keeps its memory of the story | Needs a fifth change in upstream's main file (a resume option on `spawn`), and a long-lived session grows more expensive per request |

Proposed: fresh sessions now. A fresh reader is also a stricter check, and resources are not a criterion. Resuming can be added later as its own small task if runs show reviewers missing things they had seen before.

### Owner decisions on the five questions (2026-11-14)

| # | Decision | Effect |
|---|---|---|
| 1 | "Agree, middle solution": a rejected child is fixed after the child in hand, before the next | As HM-25 specifies |
| 2 | A plain-text goal gets a story first; the owner must be able to attach pictures or other artifacts to the request, and to pass the id of a story created before | Existing story: `factory wf start --story {key}` (HM-24). Agents can list and download attachments: added to HM-23. Attaching files to a newly created story: requirement for the architect step, no task yet |
| 3 | Roles and commands as listed in HM-23 | No change |
| 4 | The final PR-level review stays | No change |
| 5 | Both reviewer modes; a fresh reviewer per child is the default; keeping one reviewer's context is an option on the UI | HM-25: config key `workflow_reviewer_session` (`fresh`, `keep`), a Settings row, and `--resume` on `factory spawn` (a fifth seam) |

The grilling task DVDG-566 is Done; HM-22 is unblocked.

## Q: The builder should survive for the whole story, so for each task it knows what was implemented before: one working agent for all three tasks of a story, without resetting it. (2026-11-14, owner requirement)

That is how the engine is specified. HM-24 starts one builder per story and that one session works every child in order; nothing restarts it between children, so at child 3 it still has children 1 and 2 in its context. This differs from the current workflow, where each factory task gets its own new coder (in G-002: one coder per task, released after `factory done`).

Two things can still interrupt that one session, and the tasks now cover both:

| Case | What happens |
|---|---|
| The session ends early (crash, reaped, stopped) | The engine resumes the same session by its id and mails it the pending instruction; at most three times per run, then the run is blocked for the owner (added to HM-25, which adds the resume option to `factory spawn`) |
| Review findings arrive while it works | They come as mail to the same session; it fixes them after the child in hand (HM-25) |
| CI is red on the final PR | Upstream's existing restart resumes the same session when `coder_ci_handoff` is `resume`, which is the value set on this factory |

The engine never starts a fresh builder on its own; that needs the owner's word (`factory wf resume --goal … --fresh-builder`), and the new builder is then told which children are done and in which commits.

Limit to know: one session's context window is finite. On a long story Claude Code compacts the conversation by itself, so the builder keeps a summary of the early children, not every detail. The Taskosaur comments it wrote on each child and the commits remain the exact record, and it can re-read them. Not measured yet how many children fit before the first compaction.

## Q: Are we ready to start? Is anything else required? (2026-11-14 03:10)

The tasks are ready: HM-22 is unblocked and each task holds what an implementer needs. Checked at 03:10:

| Item | State | Needed before |
|---|---|---|
| Design decisions | all taken; grilling DVDG-566 Done | nothing |
| Go toolchain in WSL | `~/.local/go/bin/go`, version 1.27.3 | nothing |
| C compiler | none; `go test -race` cannot run locally, CI runs it | nothing (optional: `sudo apt install gcc`) |
| Fork `main` in CI | red: the last two runs on `main` failed (`a617aa4`, `64d6ee9`); the fix (TSR task HM-9) is In Review and not on `main` | the first engine PR: a branch cut from a red `main` cannot show a green required check |
| Who builds | not decided. The factory cannot: its project `hivemill` points at the reference repository until G-002 is closed. So a Claude session builds HM-22 onward | starting |
| Where | not decided. The working clone's branch `hm-1-settings-page` carries the settings page and flow debugger work and another session is active in it. The engine needs its own branch and folder cut from `main` | starting |
| Taskosaur account for the factory | not created: no agent user with the MANAGER role, no token, no files under `~/.config/factory` | a real run (HM-24 onward in practice); not for building, the tests use a stub |
| Existing switches | `review_autospawn`, `coder_ci_handoff`, `risk_tiers`, `mech_merge` are on | nothing |

Reference run at 03:09: factory task T-0013 merged (3 h 46 m after the goal started, three coder attempts); T-0014 to T-0016 not started yet.

Also seen: the other session committed HM-16, HM-17, HM-18 and HM-19 as `8facfa7`, so the Waiting lane is no longer uncommitted.

### Taskosaur access for the factory (2026-11-14)

The owner supplied a personal access token. It is stored in `~/.config/factory/tsr-token`, with the base address in `~/.config/factory/tsr-url` (both mode 0600). Checked with read requests only: a task was read by key, and the account is an agent user with the global role SUPER_ADMIN, the same account the Taskosaur MCP server uses. That is wider than the "manager-level agent user" decided earlier; a separate narrower account is a later option for the owner. The token is written nowhere else.

### Owner requirement, 2026-11-14: several stories "as batch"

"Add an option for the boss to accept sequence of stories (for instance if request/prompt contains 'as batch') that should be implemented sequentially and run full PR checks / full e2e tests only after these stories were implemented as batch. These stories will need to be handled by one agent sequentially if they were passed as a batch."

Design: a batch is one run. One goal, one factory task, one branch, one builder session across all stories; children of story 1, then of story 2, in order; each child is still reviewed on its own commits; the PR, the full CI and the existing final review and QA happen once, after the last story; after the merge every child and every story goes to Done, each story with its own closing comment.

Where it lands: new TSR task HM-33 (after HM-26, before HM-27); the state database gets `run_stories` and `children.story_key` already in HM-22; the boss's and builder's wording for batches is added to HM-31. "Full e2e tests" means what the repository's CI and the existing final QA run for a PR; the engine adds no test suite of its own.

Coding order now: HM-22, HM-23, HM-24 (after HM-31), HM-25, HM-26, HM-33, HM-27.

Owner decision, 2026-11-14, narrowing the batch: "Process as batch only if tasks from Taskosaur are passed. Not as free form tasks that need to be analyzed, decomposed, enriched. Batch will be supported only for prepared beforehand Taskosaur tasks." A batch therefore takes Taskosaur keys only, every item must already be prepared (the enriched check), the engine never enriches or splits a batch item, and the boss refuses a batch that contains free text. Recorded on HM-33 and HM-31.

## Q: "This is insane to run e2e tests for so long" (2026-11-14, about PR 10's CI)

Measured on the third run of PR 10 (run 43470388608): about 22 minutes from start to the last job, every job green. The run is as long as its longest job, because the jobs run side by side:

| Job | Minutes |
|---|---|
| guard-equiv | 21.8 |
| guard-diff | 17.4 |
| guard-equiv-rest | 15.4 |
| guard-unittest-shard (3) | 14.8 |
| unittest-shard (7) | 13.9 |
| the other test shards | 8 to 11 |

What these are: not browser end-to-end tests. They are the factory's own Python tests, most of which start the real CLI as a subprocess against a throwaway home, plus the "guard" jobs, which check that the Python and Go versions of the worker guard decide every case the same way.

Why PR 10 got the longest form: it touches "risky paths" (role permission templates, the CI workflow), and for those upstream's CI runs the full suite and every guard job. The three runs it needed were this session's doing: two fixes that should have been found locally first.

What it means for the engine work:

- A PR that changes only Go code under `go/` and new files is not on the risky list (`ci/ci_tier.py`): it gets the Go job (about 10 minutes here) and the tests its files affect, not the full suite.
- A PR that adds a key to `DEFAULT_CONFIG` or edits the tick in `bin/factory_cli.py` is risky and gets the full run. HM-22 and HM-25 do that; the other engine tasks do not have to.
- All engine tasks on one branch with one PR means one full run in total, which is the same idea the engine itself applies to stories and batches.

Ways to shorten a full run, none done: more test shards (the split is a number in the workflow), skipping the guard jobs when no guard file changed (they are already skipped for most paths, but role settings count as guard paths), or larger runners. Each is a change to upstream's workflow file and a merge risk; not proposed for now.

## Q: Can these tests run in parallel? We have 6 cores with 12 threads on the machine. Why can't they? (2026-11-14)

They already run in parallel, and they did not run on the owner's machine.

- Where: the 22-minute run was on GitHub's hosted runners. Each job gets its own virtual machine there (for a public repository, 4 virtual CPUs each). The owner's 6 cores played no part.
- How parallel: the workflow starts about 20 jobs side by side: ten test shards, the guard jobs, the Go job. The run lasts as long as its slowest job, which was `guard-equiv` at 21.8 minutes; the test shards took 8 to 14 minutes each.
- Why one job is still slow: inside a job the tests run one after another. Python's built-in test runner has no parallel mode, and most tests start the real CLI as a separate process against their own throwaway home, which is slow per test. Upstream's answer to that is sharding (more jobs), not threads.

What would make it faster, none done:

| Option | Effect | Cost |
|---|---|---|
| Split the slowest jobs further (`guard-equiv` is already split once into `guard-equiv` and `guard-equiv-rest`) and raise the shard count from 10 | The run approaches the next slowest job, roughly 10 to 14 minutes | Edits upstream's workflow file and the tests that pin its shape (`tests/test_shard.py`, `tests/test_ci_guard_shard.py`); merge risk |
| Use the owner's machine as a self-hosted runner | 12 threads, no queueing | The fork is public: a self-hosted runner on a public repository runs whatever a pull request contains on that machine. Not recommended |
| Run the shards locally in parallel before pushing (`python3 ci/shard.py run --shard N --total 10` for N = 1 to 10 at once, inside WSL) | Finds failures in minutes instead of after a 22-minute round on GitHub; would have saved two of the three runs of PR 10 | The factory keeps a limit on concurrent full test runs on the box (test slots) so agents are not starved; a parallel local run competes with a running goal. Time on this machine not measured |

Recommendation: the third option as a habit for risky changes, when no goal is running; leave upstream's workflow alone for now.

## Q: Because we are rewriting into Go, can we skip the Python tests? (2026-11-14)

Not as a rule, for two reasons, but most of the engine work should not need the full Python suite anyway.

1. The factory is not rewritten yet. Upstream is moving it to Go in stages and Python is still what runs: the CLI, the tick, spawn, the merge gate. Only four read-only commands have a Go version that the Python side may hand over to. The engine is new Go code that stands on that Python: it starts agents with `factory spawn`, relies on the Python review automation and the Python merge gate. The Python tests are what says those still work.
2. The engine needs five small changes inside the Python CLI (the switch, the build call, the tick step, the `wf` command, the resume option). Those are exactly the changes the Python tests exist to protect, and upstream's CI classes them as risky.

What can be skipped, and already is by upstream's own rules:

- The engine's logic is tested in Go only; no Python test is written for it.
- CI picks tests by the files a pull request changes (`ci/ci_tier.py`, `ci/affected.py`). A change that only adds Go files gets the Go job; whether it also falls back to the full Python suite is not verified: the reading of `ci/affected.py` suggests a Go file that no test names may select the full suite. To be checked on the first push of the engine branch.
- The required check is one summary job (`unittest`), so tests cannot be dropped for a pull request without editing upstream's workflow.

Practical consequence: keep the five Python seams in as few pushes as possible (they come in HM-22 and HM-25), and expect one full run per push that touches them. With one branch and one pull request for the engine, that is a small number of full runs in total.

## Q: Or make the Python tests run in parallel? (2026-11-14)

They can be made more parallel in two places; neither is done yet.

| Where | How | Expected effect | What it touches |
|---|---|---|---|
| On GitHub | Raise the number of test shards from 10 (each shard is one job on its own machine; the split is `ci/shard.py` with timings in `ci/shard_timings.json`) | The slowest test shard was 13.9 minutes; with 20 shards roughly half. But a run that also has the guard jobs stays at about 22 minutes, because `guard-equiv` alone took 21.8; that job would need its own split | Upstream's workflow file and the tests that pin its shape (`tests/test_shard.py`, `tests/test_ci_guard_shard.py`); every upstream merge of that file then needs care |
| On the owner's machine | A script that starts all shards at once inside WSL (`python3 ci/shard.py run --shard N --total T`, one process per shard, 10 to 12 of them on the 12 threads) and prints the failures | A full local check in a few minutes instead of a 22-minute round on GitHub; not measured | Nothing upstream: a new local script. To verify first: whether a shard run takes one of the factory's test slots (the limit that keeps agents from being starved), and that it is not run while a goal is working |

Not possible without rewriting the tests: threads inside one test process. The tests start real CLI subprocesses and use the standard library runner, which runs one test at a time.

Recommendation: build the local script first (no upstream risk, helps every risky change); change the shard count on GitHub only if runs without guard jobs turn out to be the common slow case.

## Owner decision, 2026-11-14: tests that pass locally do not wait for GitHub's CI

"if we run the tests locally and they pass we should not wait in future for the CI in GitHub to get green. I don't want to have 20 minutes delays to wait for the GitHub CI to get completed."

Found in the code (`bin/factory_cli.py` of the installed factory): upstream already has a local gate mode. A project with a non-empty `gate_cmd` is cleared for merge by a local run recorded in `gate_runs` for the exact PR head (`local_gate_problems`), and the required GitHub check is not demanded. But `checks_ok` still requires every GitHub check that exists on the PR to be finished and green, so with the fork's CI running on every PR, local mode alone would still wait.

TSR task HM-34 covers it: a command that runs all test shards and the Go checks in parallel on the owner's machine; local mode for the fork's projects; the smallest change so that neither the first review nor the merge waits for GitHub; GitHub's run kept on pushes to `main` as a safety net; a failed local run or a finished failed GitHub check still blocks. Step 1 of the task is reading the parts not read yet (the gate runner, and what review start and coder restart do in local mode).

Effect on the engine story: none on its tasks. The engine reuses the project's gate, so once HM-34 is in, a story's or batch's single pull request is cleared by the local run.

## Q: Is there a UI for it on the Settings page, or do we need a new UI setting? (2026-11-14, about the local gate)

There is none, and a new one is needed. The Settings page (`web/views/settings.py`) shows factory config keys only: the worktree reuse group and the seven Automation switches. The local gate is not a config key; it is a property of each factory project (`gate_cmd` and `required_checks`, changed with `factory project update`), so the page can neither show nor change it today.

Added to TSR task HM-34: a "Merge gate" group with one row per project and the choice "GitHub CI" or "Local test run", saved through the CLI like the other settings, restoring the previous values when switched back, and showing the last local run (when, pass or fail, how long). If the task ends up adding a config key for "do not wait for unfinished GitHub checks", that key gets a row in the same group.

## Q: What is left before the next step (the first real story run)?

Answered 2026-11-14 17:23, from the factory database (read-only), the unit file and the engine guide.

Ready:

- The engine code is in the fork's `main` (`8c8f973`) and already in the installed factory, which fast-forwards itself; `workflow_engine` is not set, so it is off.
- Taskosaur access files exist in `~/.config/factory/` (`tsr-url`, `tsr-token`, mode 0600).
- Go is where the factory looks for it (`~/.local/go/bin/go`); the tick builds `factory-workflow` on its first run after the switch is on.
- The gate switches of the reference run are on (`coder_ci_handoff` resume, `prcheck_required` 1).

Left, in order:

1. G-002 must finish. At 17:20 its last factory task T-0020 was on coder attempt 3 of 3 (rewrite of the pull request body and one nit), pull request 7 on the reference repository.
2. Measure G-002, then `factory project update hivemill --repo ~/factory --gh ndovgaluk/hivemill` and `factory config worktree_reuse 1`. The project still points at `~/src/hivemill-ref`.
3. `factory config workflow_engine on`, wait one tick, check `factory wf version`.
4. Check the boss has the skill `factory-boss:story-run` (it was relaunched at 17:00, after the update; not verified that the skill loaded).
5. Choose the story for the first run: small, prepared (each child has a description, an `## Acceptance criteria` list and its tests field; the story has a size or complexity).
6. Housekeeping, not blocking: the working clone `~/src/hivemill` has 13 uncommitted files and its branch is 41 commits behind `main`; the worktree `~/src/hivemill-flowui` is a stale copy.

Not blocking the first run: HM-34 (the run still waits about 22 minutes for CI at its single pull request), TSK-604 (commit links of Hivemill tasks open the wrong repository), HM-29.

## Q: Do we still need the Taskosaur story TSK-586 (support for external automation clients)?

Answered 2026-11-14. Mostly no; one of its three children is still worth having.

TSK-586 was written on 2026-11-13 for the earlier design, DVDG-545: Hivemill mirrors its goals and factory tasks into Taskosaur. The engine works the other way round: it reads stories prepared in Taskosaur and writes back statuses, comments, review marks and commit links. It never creates a task.

| Child | For | Needed by the engine? |
|---|---|---|
| TSK-587 idempotent comments (`externalKey` on `POST /task-comments`) | a retried comment is not posted twice | Yes, useful: the engine retries a POST after a network error or a 5xx, so a comment can appear twice. The engine would need a small change to send the key. |
| TSK-588 external links on a task | a task shows a link to the factory goal or task | No. Nice to have only. |
| TSK-589 idempotent task creation and lookup by external key | one TSR task per factory task with no duplicates | No. The engine creates no tasks. |

Commit links are already safe to repeat: `TaskCommitsService.link()` is an upsert on (task, sha), read in the Taskosaur code on 2026-11-14.

Open: whether the mirroring of DVDG-545 is still wanted for goals that do not start from a Taskosaur story. If not, TSK-588, TSK-589 and the rest of DVDG-545 can go to the backlog. Nothing was changed in TSR.
