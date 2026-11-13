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
