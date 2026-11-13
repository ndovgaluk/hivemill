# 40. Handover: workflow redesign, state on 2026-11-13 23:30

Written so a new session can continue without the old conversation. Read this first, then file 39 (reference run) and file 38 (design).

## Reference run 2 (TSR task HM-5, runbook in file 39)

Everything is set up; the run has **not started**. It starts when the owner pastes the prompt (HM-5, word for word) into the boss pane.

| Item | State |
|---|---|
| Seven automation switches | on since 21:58 |
| Reference repository | `ndovgaluk/hivemill-ref`, public, `main` = commit `8d616f6` (before G-001); clone `~/src/hivemill-ref`, only `main` |
| CI on its `main` | all green except `go` (`not enough arguments in call to goldenEnv`); the summary job `unittest` fails only because of it. Same break the first run started with. It must stay: do not fix or push anything to `hivemill-ref` |
| Factory | `worktree_reuse` 0; project `hivemill` → `~/src/hivemill-ref`, GitHub `ndovgaluk/hivemill-ref`; boss and director relaunched fresh at 22:52 |
| `factory clean` | not run on purpose (pool empty; G-001's eight worktrees kept) |
| At 23:15 | no new goal in the database yet |

### When the owner says the goal is done (or asks for status)

1. Read the state read-only from `~/factory/db/factory.db` (goal, tasks, messages, verdicts, events, agents), as for G-001. From Windows run a script file: `wsl -d Ubuntu -u dell -- bash /mnt/c/.../script.sh`.
2. Measure the run the same way as the first (file 37, sections 1 and 2): wall time, messages by sender and recipient, sessions started, verdicts, spec updates, tokens and cost per role from the session transcripts under `~/.claude/projects/-home-dell-factory*`, size of the merged code in `hivemill-ref`. Compare with the table in HM-5. Check quality too: the success criteria, and whether the isolation hole the first run found was handled.
3. Point the factory back, as the owner (no agent identity): `factory project update hivemill --repo ~/factory --gh ndovgaluk/hivemill` and `factory config worktree_reuse 1`. The switches stay as the owner decides.
4. Write the result into a new knowledge file and a comment on HM-5; message the owner in Taskosaur; the owner asked for a WirePusher notification as well when their attention is needed (the `wire` parameter of the Taskosaur skill).

Not verified: the mechanical merger's runner is not installed as a systemd unit; `red_main_freeze` and `judge_wait_main_run` are 0. The database still holds G-001's plan and messages (possible contamination).

## Taskosaur side

TSK-590 (story), TSK-592, TSK-593, TSK-594, TSK-591, TSK-595 are Done and committed in the Taskosaur repository by another agent (not pushed). `set_agent_check` is live in the MCP server. Not done: the Playwright spec `agent-check-marks` was written but not run; no task yet for showing estimates in the web app.

## Hivemill design (TSR story DVDG-565, file 38)

Decided by the owner: three workflows chosen by size and complexity, and their contents; limits by convergence; one manager-level agent user in Taskosaur; "enriched" = description, acceptance criteria and e2e tests written; one PR per story; overlapping stories in sequence; merged = Done; the Taskosaur task is the design record; estimate time and cost before execution; extend beside upstream; no task written without reading the code.

Open for the owner:

1. Go or Python for the workflow engine (upstream requires Go for new code since 2026-11-11; recommended: Go).
2. Four proposals not yet confirmed (file 38, section 11, rows 4 to 7).

Not written: the Hivemill build tasks. Read first, in full: `dispatch_tick`, `review_rerun_tick`, `coder_ci_resume_tick`, `cmd_up`, and how a factory task maps to a PR. The second reference run will show how much the existing switches already give; write the tasks after it.

## Working clone (`~/src/hivemill`, branch `hm-1-settings-page`)

- Committed, not pushed (9 commits ahead of its remote): HM-7 `1731401`, HM-8 `cce0124`, notes `707e583`. HM-7, HM-8 and HM-4 are Done.
- Uncommitted: `docs/knowledgebase/00-session-log.md` and this file.
- The branch is 33 commits behind the installed `main`.

## Known problems

- Commit `e623cab` edits upstream's `roles/coder.md` in place (against planning rule P8 and "extend beside upstream") and blocks `/hm deploy`. Fix: restore the three phrases, put the pointer to `worktree-postinit-rules.md` into a separate skill.
- `/hm deploy` and `/hm master-local-deploy`: only `check` was run.
- The fork's `main` is red in CI since the morning merges; another agent was asked to fix it. Its fix was not found on the fork, in the working clone or in the installed factory at 23:20.
- The four factory lessons from the G-001 analysis (file 31) are not recorded.
- Commit links on HM tasks point at the Taskosaur repository (the Dev project's repository URL), so they do not open.

## Where to look

| What | Where |
|---|---|
| Session log, one line per turn | `00-session-log.md` |
| G-001 measured, lean flow proposal | `37-g-001-full-analysis-and-lean-flow.md` |
| Design, decisions, code findings, Go policy, estimation | `38-workflows-design.md` |
| Reference run 2 runbook and the boss prompt | `39-reference-run-with-automation-switches.md` |
| Draft workflow and agent definitions | `workflows/` at the repository root |
| Reference goal, prompt word for word | TSR task HM-5 |
