# Stopping the factory in the middle of a goal

## Q: What will happen if I stop the factory half way through the goal?

(Reply of 2026-11-13, as written.)

The goal survives and continues after a restart; what you lose is the unfinished thinking of the workers that were running. There is no "stop the factory" command, so it depends on what you actually stop.

Relevant insights: "Changing a goal's status stops nobody" (a goal's state lives in the database, apart from the agents); the WSL quoting one (applied).

### What is kept

- **The database:** goals, plans, factory tasks and their status, messages, verdicts and the event log. It is a file, so it does not depend on anything running.
- **Work on disk:** each worker's worktree, including edits it had not committed yet.
- **Work on GitHub:** pushed branches, open PRs, and CI runs, which keep running on GitHub's servers whether or not your machine is on.

### What is lost or interrupted

- **Running workers** (pm, coder, reviewer, qa, judge) are not resumed. After a restart the tick sees that their panes are gone, marks them `lost` and sends the director an "agent vanished… respawn or reassign" alert.
- **A worker's conversation:** whatever it had figured out but not written to files, a commit or the factory task is gone. A respawned coder starts fresh on the same factory task, branch and worktree and reads what is there. Expect some repeated work, more if it was stopped mid-edit.
- **Time:** nothing moves while the factory is down. No nudges, no spawns, no merges.

### What comes back by itself

On your install the boot units are enabled (`factory-up.service`, `factory-tick.timer`, `herdr-server.service`; linger is on; checked 04:53).

- **Boss, director and each active team's lead** are resumed by `factory up` with their previous sessions, so they keep their conversation history.
- **The tick** starts again and nudges them about unread mail.
- **Workers:** the director gets the "vanished" alerts and has them respawned. Nothing to do by hand, according to the setup doc.

### It depends on what "stop" means

| You do | Effect |
|---|---|
| Close the herdr window or the terminal | Nothing stops if the herdr server runs as a service (it does here): agents keep running in the background |
| Shut down or restart Windows, or `wsl --shutdown` | Everything stops at once, mid-action. On the next start: as described above |
| Stop only the tick (`systemctl --user stop factory-tick.timer`) | Agents that are running keep working, but nobody is nudged, nothing new is spawned, finished panes are not closed. The factory drifts to a halt |
| Stop one goal, keep the factory | Ask the boss, or `factory stop <agent>` per worker (see [14-agent-communication.md](14-agent-communication.md)) |

### Risks of a hard stop

- **A half-finished action:** a worker killed in the middle of a merge of `main`, a rebase or a push leaves its worktree in that state. The respawned worker has to notice and clean up. I did not test how well it does.
- **The judge mid-merge:** if it stops between merging the PR and recording the result, the database and GitHub can disagree for a while. I did not check how the factory reconciles that.
- **WSL does not start with Windows by itself** (my assumption about your setup, not checked): the boot units run when the WSL machine starts, which normally happens when you open Ubuntu or something calls `wsl`. Until then the factory stays down.

### If you want a clean stop

1. Tell the boss to stop starting new work and let the running workers finish (or stop them with a reason).
2. Wait until `factory agents` shows only boss, director and leads.
3. Then shut down. After the restart, open Ubuntu, check `factory agents` and tell the boss to continue.

**Not verified:** I read the docs (`docs\operations.md`, `docs\SETUP.md`) and the tick's "lost" step in the code (`bin\factory_cli.py:15071`), and checked that the units are enabled. I did not stop anything or watch a real recovery on this install.

LSP: not used, the code read is Python (no language server installed for it); located with Grep.

Skipped: testing a real stop and restart, and reading how the judge recovers from an interrupted merge; risk: a hard stop during a git operation or a merge may need a manual look afterwards.

---

## Q: Ok, but if the coder has started implementation the message is marked as read and after restart, how would the factory know from where to continue processing?

(Reply of 2026-11-13, as written.)

The inbox is not where progress is kept, so a message being marked read loses nothing. The factory continues from the state recorded in the database and from what is on disk and on GitHub.

Relevant insights: "Changing a goal's status stops nobody" (state and agents are separate things); the WSL quoting one (not needed, nothing was run).

**Two corrections to the picture first:**

- **A coder does not get its work as an inbox message.** It is started for one factory task, and the task id is in its first prompt. It reads the spec from the database (`factory task show T`), not from mail.
- **"Read" only hides a message from the unread list.** The message stays in the database (`factory inbox --all`, `factory inbox --show M…`), and decisions are deliberately sent as `decision` messages so they stay on record.

**What tells the factory where it was:**

| Recorded state | Where | What it says after a restart |
|---|---|---|
| Factory task status and assignee | database | T-0003 is `in_progress`, held by `coder-t-0003` |
| Agent rows | database | that agent's pane is gone, so the tick marks it `lost` |
| Verdicts and attempt count | database | which reviews passed or failed, which attempt this is |
| Event log | database | everything that happened, in order |
| Branch, commits, PR, CI result | git and GitHub | how far the code itself got |
| Worktree | disk | edits that were not committed yet |

**How it picks up again:**

1. **The tick notices the gap.** On its first run it finds a live agent row with no pane, marks it `lost`, and sends the director a new alert: "agent coder-t-0003 vanished… Task T-0003. Decide: respawn or reassign." That alert is a fresh unread message, so the restart itself creates the trigger.
2. **The HQ roles come back with their memory.** Boss, director and the lead are resumed in their previous sessions, so they still know what they were doing.
3. **The lead triages the factory task** (skill `fix-loop`, step 1): it runs `factory task show T` and looks at the worktree and the branch.
   - Nothing produced (clean worktree, no new commits): respawn a coder for the same factory task. This does not count as an attempt.
   - Partial or unpushed work: describe it in the next coder's prompt, or ask that coder to push it first.
4. **The new coder starts from the artefacts.** It reads the spec and verdicts, finds the existing branch, worktree and PR, and continues from the code as it stands.

**What "from where to continue" does not cover:** the lost coder's own plan. If it was halfway through a change, the new coder sees half-edited files and has to work out the intent from the spec and the diff. The factory resumes at the level of factory tasks and commits, not at the level of a worker's train of thought.

**Not verified:** the exact path from the director's alert to the lead acting (whether the director forwards it, or the lead finds the lost worker itself on its next wake), and I have not watched a real restart on your install. Steps 1 and 3 are from the tick code and the lead's skill, read earlier today.

LSP: not used, no code was read this turn (earlier findings and docs only).

Skipped: a live restart test; risk: half-edited, uncommitted files are the weak point after a hard stop, so the first respawned coder's PR is worth a closer look.
