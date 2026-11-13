# 40. Handover: workflow redesign, state on 2026-11-13 22:18

Written so a new session can continue without the old conversation. Read this first, then file 38 (design) and file 39 (reference run).

## Where things stand

### Reference run 2 (TSR task HM-5, runbook in file 39)

| Step | State |
|---|---|
| Seven automation switches on | done by the owner at 21:58, confirmed in the database |
| Reference repository | `ndovgaluk/hivemill-ref`, public, `main` = commit `8d616f6` (before G-001); local clone `~/src/hivemill-ref` with only `main` |
| CI on its `main` | still running at 22:18: push run 43414268162 and a manual run 43414256574. `go vet` fails in both. `unittest-shard (9)` failed in the manual run; the push run had not reached it |
| Factory prepared (`worktree_reuse 0`, `factory clean`, project re-pointed) | **not done** |
| Boss and director restarted fresh | **not done** |
| Prompt pasted to the boss | **not done** (the owner does this) |

What to decide when CI finishes:

- The baseline was already red when G-001 started: the same commit's test run failed upstream, and the lead reported "main's Go tests do not compile" in the first run; the first factory task fixed it. So a red `go` job is the original starting condition.
- `unittest-shard (9)` must be checked: if it fails in both runs, read its log (`gh run view --repo ndovgaluk/hivemill-ref --job <id> --log-failed`) and decide whether it fails because the repository is a different one (then the merge gate could never pass and the setup needs a fix) or for the same reason as the first run.
- If only original failures remain: run step 2 of file 39, then step 4, then tell the owner to paste the prompt.

The owner's go-ahead covers creating the repository and re-pointing the project ("Go ahead, create what you need").

### Taskosaur tasks, with an agent

TSK-592 → TSK-593 and TSK-594 → TSK-591; TSK-595 independent. Story TSK-590 holds the contract. All were written from the Taskosaur code (master at 84b5450).

### Hivemill design (TSR story DVDG-565, file 38)

Decided by the owner: three workflows chosen by size and complexity; their contents; limits by convergence (5 fix rounds, architect after 2 on the same kind of finding); one manager-level agent user for Taskosaur; "enriched" = description, acceptance criteria and e2e tests written; one PR per story; overlapping stories in sequence; merged = Done; Taskosaur task is the design record; estimate time and cost before execution; extend beside upstream.

Open for the owner:

1. **Go or Python for the workflow engine.** Upstream requires Go for all new code since 2026-11-11 and forbids new Python files. Recommended: Go.
2. Proposals not yet confirmed: a rejected child is fixed after the current child; how the boss names a workflow; a Taskosaur story is created first for a goal given as text; which roles may call which `factory tsr` command.

Not written yet: the Hivemill build tasks. Before writing them, read in full: `dispatch_tick`, `review_rerun_tick`, `coder_ci_resume_tick`, `cmd_up`, and how a factory task maps to a PR (candidate: one Taskosaur story = one factory task = one PR). Rule: no task without reading the code.

Also not written: a Taskosaur task to show estimates and actuals in the web app (TSK-595 covers storage, API and MCP only).

## Uncommitted work in the working clone (branch `hm-1-settings-page`)

- HM-7 (Automation group on the Settings page, In Review): `web/views/settings.py`, `web/server.py`, `tests/test_web_settings.py`, `docs/web-ui.md`.
- Knowledge files: `00-session-log.md`, `38-workflows-design.md`, `README.md`, new `39-…`, this file.
- `web/components.py` and `tests/test_web_detail.py` are changed by another session; do not commit them without asking.
- The branch is 6 commits ahead of its remote and 33 behind the installed `main`.

## Known problems to fix

- Commit `e623cab` edits upstream's `roles/coder.md` in place and shortens existing wording (against planning rule P8 and the "extend beside upstream" rule). It also blocks `/hm deploy`: the installed `main` changed the same lines. Fix: restore the three phrases and put the pointer to `worktree-postinit-rules.md` into a separate skill.
- `/hm deploy` (new): only `check` was run. `apply` and `revert` are untested.
- `/hm master-local-deploy`: only `check` was run.
- The mechanical merger's runner (a systemd unit `factory-mech-merge` named in its docs) is not installed; whether merging without a judge works here is unknown.
- The four factory lessons from the G-001 analysis (file 31) are still not recorded.

## Where to look

| What | Where |
|---|---|
| Session log, one line per turn | `00-session-log.md` |
| G-001 measured, lean flow proposal | `37-g-001-full-analysis-and-lean-flow.md` |
| Consolidated design, decisions, code findings, Go policy | `38-workflows-design.md` |
| Reference run 2 runbook and the boss prompt | `39-reference-run-with-automation-switches.md` |
| Draft workflow and agent definitions | `workflows/` at the repository root |
| Reference goal, prompt word for word | TSR task HM-5 |
