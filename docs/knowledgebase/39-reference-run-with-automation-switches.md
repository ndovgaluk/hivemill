# 39. Reference run 2: G-001's goal with the existing automation switches on

Prepared 2026-11-13 for TSR task HM-5. Nothing in this file has been executed. Each step says whether it was checked in the code or is not yet verified. Commands run in WSL as the owner (no agent identity set), unless a step says otherwise.

## Q: What is needed to pass the reference goal to the boss again, this time with the automation switches on?

Four things: a repository whose `main` is the code before G-001, the factory's project pointed at it, the switches turned on, and the goal text sent unchanged.

### Why a separate repository

Read in `bin/factory_cli.py` and `.github/workflows/tests.yml` on main at a617aa4:

- The judge, the refresh and the mechanical merger refuse a PR whose base is not `main` ("PR base is …, not main"). It is a literal in the code, not the project's base branch.
- CI runs only for PRs to `main` and pushes to `main` (`tests.yml`).

So the run cannot target the branch `baseline/pre-g-001` in the fork. It needs a repository whose `main` is that commit. The project keeps the id `hivemill`, so the goal text fits word for word.

### Step 1. Create the reference repository (once)

Not executed; creating a repository is yours to decide.

```
gh repo create ndovgaluk/hivemill-ref --private
git clone https://github.com/ndovgaluk/hivemill.git ~/src/hivemill-ref
cd ~/src/hivemill-ref
git remote set-url origin https://github.com/ndovgaluk/hivemill-ref.git
git checkout -B main origin/baseline/pre-g-001
git push -u origin main
```

- `--private` or `--public` is your choice. The fork is public already; a private repository has a monthly limit on CI minutes, and this project's CI runs many jobs per PR (G-001's PRs showed 21 checks).
- Only `main` is pushed. The commit is `8d616f6`, the parent of the first G-001 merge.

Then check that CI ran on that push and is green:

```
gh run list --repo ndovgaluk/hivemill-ref --workflow tests.yml --limit 3
```

**Not verified:** that the workflow passes in a new repository (it may need repository settings or secrets the fork has). The merge gate needs the check `unittest` green, and the mechanical merger needs a successful `tests.yml` run on the current `main`. If this is red, stop here.

### Step 2. Prepare the factory

Checked in the code: `factory project update <id> --repo PATH --gh OWNER/NAME` exists and needs the director role or the owner (`cmd_project`).

```
factory config worktree_reuse 0
factory clean
factory project update hivemill --repo ~/src/hivemill-ref --gh ndovgaluk/hivemill-ref
factory project list
```

- `worktree_reuse 0` and `factory clean` first: the pooled worktrees belong to the old repository and would fail the ownership check under the new one. G-001 also ran without reuse, which keeps the comparison fair.
- While the project points at the reference repository, the factory cannot work on its own code. No other Hivemill goal should run until step 6.

**Not verified:** that nothing else assumes the `hivemill` project lives in the factory's own folder.

### Step 3. Turn the switches on

On the Settings page, group **Automation** (HM-7), at `http://127.0.0.1:18625/settings`, or with `factory config <key> <value>`:

| Setting | Value | Why |
|---|---|---|
| Lead parking (`lead_parking`) | On (`1`) | needed by the next one |
| Start workers without the lead (`lead_less_dispatch`) | On (`1`) | the tick starts ready workers |
| Start review when a PR opens (`review_autospawn`) | On (`on`) | reviewer and QA start without the lead |
| PR check required before done (`prcheck_required`) | On (`1`) | needed by the hand-off |
| Coder hands off at PR open (`coder_ci_handoff`) | Resume (`resume`) | the same coder session continues on red CI |
| Risk tiers (`risk_tiers`) | On (`on`) | needed by the merger and the combined reviewer |
| Merge without a judge agent (`mech_merge`) | On (`on`) | lower-risk PRs merge without a judge |

- The dependencies in the "Why" column are from the docs pages (`lead-less-dispatch.md`, `prcheck.md`, `mech-merge.md`, `review-autospawn.md`).
- **Not verified:** the mechanical merger's runner. Its docs name a systemd unit `factory-mech-merge`; no such unit file is in `systemd/` or installed here. If the merger cannot run, a PR stays with the judge as before, so the run still completes.
- None of these switches has been used on this factory. The reference repository is disposable, which is why they go straight to On and not to Shadow.

### Step 4. Start from fresh HQ sessions

The boss and the director that ran G-001 are still live and remember how it was solved. For a fair run, restart both without their old session:

```
factory relaunch boss --fresh
factory relaunch director --fresh
```

**Limit that stays:** the factory database still holds G-001's plan, specs, messages and verdicts, and an agent that looks could read them. A fully clean run needs a separate factory home, which was not set up. Read the comparison with that in mind.

### Step 5. The message for the boss

Paste this, and nothing else, into the boss pane. It is the owner's text of the first run, word for word (TSR task HM-5).

```
New goal for project hivemill: add an opt-in config worktree_reuse (default off). When on, a new coder task reuses a free, clean worktree of the same project instead of creating one: reset to origin/{base} on the task's new branch, keep ignored files such as node_modules, remove untracked non-ignored files, and re-run the git config guard. Two tasks must never share a worktree (claim it in the DB). factory clean keeps up to N pooled worktrees per project. Success: off = identical behaviour to today; on = a second task in the same project reuses the first task's worktree with ignored files intact; tests for reuse, isolation (no leftover untracked files or git config), concurrency and clean-up, through the real CLI.
```

Note the time you send it. The goal's own start and end are in the database.

### Step 6. After the goal is done

Put the factory back:

```
factory project update hivemill --repo ~/factory --gh ndovgaluk/hivemill
factory config worktree_reuse 1
```

Leave the switches as they are or turn them off; that is your call once the numbers are in.

Then the run is measured the same way as the first one (file 37): wall time, messages by sender and recipient, agent sessions, verdicts, tokens and cost per role, size of the merged code, and whether the result meets the success criteria, including the isolation hole the first run found.

## What differs from the first run, besides the switches

- The factory's own code and role prompts have moved on since G-001 (for example the reviewer's failure summary is now written as a rework brief, DVDG-569).
- The models are unchanged: HQ roles and reviewer on Opus 5.5, coder and QA on Sonnet 5.5.
- So this run answers "what do the existing switches give on today's factory", not a strict one-variable experiment.
