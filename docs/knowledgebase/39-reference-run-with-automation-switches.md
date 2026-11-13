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

## Q: The boss created G-002 and asked four things back. How should the owner answer? (2026-11-13 23:30)

The boss's reply after the prompt: it created G-002 as a fresh build on `hivemill-ref` (not a port of G-001's PRs), said the team will use what G-001 taught (forged-`.git` safety in `factory clean`, no new Python files, the unreliable local pre-PR check), and asked: (1) were tonight's settings changes the owner's, and should `prcheck_required` go back to 0 for G-002; (2) what is the next goal; (3) adopt the C-0079 code-simplifier plugin?

Answers recommended to the owner:

| Boss's question | Answer | Why |
|---|---|---|
| Fresh build or port G-001's PRs | Fresh build | The run exists to measure an independent second build; a port measures nothing |
| Were the settings changes the owner's | Yes, all seven | The owner set them on the Settings page at 21:58 |
| `prcheck_required` back to 0 | Yes, set it to 0 for G-002 | Measured in the G-001 records, see below |
| Next goal, C-0079 plugin | Decide after G-002 | Not needed for this run |

Evidence on the pre-PR check, from the factory database (G-001 window): 9 recorded `factory prcheck` results, all 9 with `ok: false`. Failed parts: `affected` (the 120 s local budget of `ci/affected.py` under load; coder-t-0006 reported "rc=4, 178 tests OK", CI passed) and `body` (PR body word limit). One coder (coder-t-0007) went 66 minutes without a push while both full-suite slots were busy; the lead judged this "likely its prcheck/affected run". With `prcheck_required=1` the same check becomes a hard gate, so the same failure would stop a coder instead of being reported. It is a quality gate that CI already covers, not one of the hand-over automations the run is meant to measure. The other six switches stay on.

Effect on the comparison (not avoidable now): the second run is not a clean-room repeat. The boss and the team know G-001's outcome and lessons, so part of any speed-up comes from that knowledge, not from the switches. The result file must say so. This was the "possible contamination" noted in file 40.

Not checked: whether a `prcheck` with `ok: true` ever happened without leaving an event; whether the 120 s budget is configurable.

### Correction, 2026-11-13 23:58: keep `prcheck_required` at 1

The recommendation in the section above ("set it to 0 for G-002") was wrong and is withdrawn. It was made from the G-001 records without reading the gate code. Read since (`bin/factory_cli.py` of the installed factory, the done gate around `ci_handoff_active`, and `docs/prcheck.md`, "CI handoff"):

- The coder hand-off lives inside the pre-PR gate. With `coder_ci_handoff` on, `review_autospawn=on`, `prcheck_required=1` and the task `in_review`, `factory done` runs only the cheap parts (fresh, identity, PR body, public text) and **skips the affected-tests part**; a pending or red CI head is accepted.
- The failures recorded in G-001 were mostly that affected-tests part (its run under load). G-001 ran with the hand-off off, so it is not evidence for this run.
- With `prcheck_required=0` the gate function returns before the hand-off branch. Not traced: what `factory done` then does about CI. The coder's kickoff would still say "do not wait for CI", so the setting and the instruction could disagree.

So: all seven switches stay on. Remaining risk: the PR body check (word limits) is now a hard stop at `factory done`; a coder fixes it by editing the PR body. A coder may still choose to run the full `factory prcheck` itself and wait on the affected run; that is a delay, not a gate.

## Q: The boss says the director lists eight settings plus `worktree_pool_max`; are `worktree_reuse=1` and `worktree_pool_max=4` the owner's? (2026-11-13 23:45)

Read from the factory database at 23:42:

| Setting | Value now | Last change | Whose |
|---|---|---|---|
| `worktree_reuse` | 0 | set to 0 at 22:52:07 | The assistant's setup script, as owner, on the owner's go-ahead: the factory's own reuse feature is off during the run so worktrees are created the same way as in G-001 |
| `worktree_pool_max` | 4 | set at 21:58:03 | Same minute as the seven switches the owner saved on the Settings page; has no effect while `worktree_reuse` is 0. Not checked: whether the Settings page wrote it or a command did |

So the director's list is out of date on one point: `worktree_reuse` is 0, not 1, and must stay 0 until the run is measured. Both values are owner-side and stay.

The boss's schedule for G-002: four build tasks T-0013 to T-0016 strictly one after another (all edit `bin/factory_cli.py`), 4 to 5 hours per PR cycle because schema and default-config changes make CI run the full suite, target close 23:00 on 2026-11-14. That is about 24 hours against 8 h 55 m for G-001. It is an estimate, not a measurement; not acted on, because the run is the measurement. If it holds, the finding is that the hand-over switches do not help when the plan is serial and each PR waits on a full CI run.

## Q: We can wait 24 h, but what is the purpose of that run? The idea was to minimise execution time, not extend it. If I asked you to implement the task it would take a couple of hours at most. (2026-11-13 23:50)

The run is a measurement, not the improvement. Its one question: how much of the slowness do upstream's existing switches remove on their own, so that only the rest has to be built. It was never expected to be the fast flow.

The boss's plan already answers most of it, before any code is merged: four PRs strictly in sequence, each with its own full CI run, review and QA. The switches remove waiting at hand-overs (lead parked, tick starts workers and reviews, no judge agent); they do not change that shape. If the 24-hour estimate holds, the switches are not the fix.

The owner's comparison is the right one. One capable agent building the whole story on one branch with one PR and one CI cycle is the "simple/medium workflow" already decided (one builder, children in sequence, one PR per story, review per child, QA at the end). The difference between "a couple of hours" and "a day" is the structure, not the model's speed: the factory splits one feature into four merge cycles and puts three roles between each.

What the run still gives: real numbers for the comparison table (messages, sessions, cost, rounds), proof whether the hand-over switches work at all on this install (they will be reused inside the new workflows), and the cost of full CI per PR. None of that blocks the next step.

Recommendation given: let the run finish in the background, and do not wait for it. Start the Hivemill build tasks for the new workflow now. Blocking decision for that: Go or Python for the workflow engine. The estimate of 24 hours is the boss's, not measured; "a couple of hours" for a direct implementation is the owner's estimate and plausible, also not measured.

## Q: So there is no active block right now? The workflow is in idle state? (2026-11-14 00:09)

Correct, and it is the intended state, not a stall. Read at 00:09 from the flow API (`/api/flow/goal/G-002.json`) and the database: no node is `live`; coder, PM and lead are `done` with their agents exited; the review gate is `idle`, judge and merged are `pending`. Factory task T-0013 is `in_review`; T-0014 to T-0016 are `todo`.

The goal is waiting for CI on PR 1 of `hivemill-ref` (head `b079f83`). The coder handed off at PR open and exited (the hand-off switch), the lead woke for 31 seconds to note "CI pending" and parked again at 00:05:06 (lead parking), and both panes were closed at 00:05:45. No agent runs and no tokens are spent while CI runs. At green the tick starts the reviewer and QA (review autospawn); at red it restarts the coder (attempt 2 of 3 is already used).

In the first run this wait looked different: the coder stayed live waiting for CI and the lead stayed live watching. Here the wait costs nothing, which is what these switches are for; it does not make CI faster.

The diagram has no state for "waiting for CI": every box is grey or green, so the page looks stopped. A possible improvement (not built, not requested): show the review gate as "waiting for CI" with the PR's check count.

## Q: "Needs you: alert M302: unknown writer rebuilt flow bundle in live ~/factory; prcheck hang on T-0013" (2026-11-14 00:15)

The first half was caused by the assistant session, not by a factory agent. At 23:56:12 it copied three rebuilt bundle files (`web/static/flow/flow.css`, `flow.js`, `manifest.json`) into the installed factory to show a diagram change (TSR task HM-11), believing that checkout served the dashboard. The tick checks `git status` of the installed checkout every minute and at 23:56:39 mailed the director (M302): three modified paths, "the tick does not repair this: restore or commit them by hand after finding who wrote there". The copy was undone at about 23:58 with `git checkout -- web/static/flow`; at 00:15 `git status` there is clean, at commit `a617aa4`. Nothing else in the installed factory was touched, and the run's agents never used those files.

The second half ("prcheck hang on T-0013") is the director's open check from the owner's earlier message, already answered by the director itself: `factory done` took about 30 s on attempt 1 and 10 s on attempt 2, no hang.

Lesson (written to INSIGHTS as well): the installed factory watches its own checkout; any file written there raises an owner alert within a minute. The dashboard on port 18625 is served from the working clone, so UI changes are shown there, never by writing into the installed factory.

## Q: There is no QA and Review as separate blocks? Only the review gate? (2026-11-14 00:40)

Yes, by design of the diagram (DVDG-551): the "Review gate" box stands for the reviewer and QA together, because they start at the same moment on the same PR, work in parallel, and the judge needs both verdicts. `web/flow.py` maps both roles to the node `gate` (`_LANE_NODE`: lanes `reviewer` and `qa` point to `Node.GATE`); its time and cost are the sum of both. They are separate in the Timeline (one lane each, "Reviewer" and "QA") and in the Sequence list (each verdict is its own row). Splitting the box into two is possible but changes the layout and the arrows; not built.

## Q: Can we track how long the waiting took? (2026-11-14 00:40)

Yes, built in TSR task HM-13. The Waiting box now carries two figures: the wait going on now (`current_s`, shown while the box is active) and every wait so far (`work_s`: all the time since the first agent session of the goal in which no agent of the goal was running; shown on the box when it is idle, in its tooltip, and in the "Where the time went" list as "Waiting"). At 00:35 for G-002 the total was 1341 s (22 min 21 s) out of about 72 minutes elapsed. Limits: it does not say what each past wait was for, and a session whose end was never recorded counts as zero length, which overstates waiting.
