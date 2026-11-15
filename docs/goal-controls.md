# Goal controls

The owner pauses, resumes or stops one goal from its page in the dashboard, or with `factory goal` (TSR story HM-42,
owner decisions of 2026-11-15). The factory-wide switch is the Urgent stop (`docs/urgent-stop.md`).

## The controls

| Action | Command | What it does |
|---|---|---|
| Pause | `factory goal pause G-001 [--reason ...]` | sets the goal's hold to `paused`, then stops every agent of the goal now (queued starts cancelled, live agents through the `factory stop --now` path). Pull requests, branches and worktrees stay. |
| Resume | `factory goal resume G-001 [--reason ...]` | clears the hold. The tick and the goal's lead start **fresh** agents from the task states; no old session is resumed. |
| Stop | `factory goal stop G-001 [--reason ...]` | as Pause with the hold `stopped`, then the goal is `cancelled`. Its open pull requests are listed and left open. A stopped goal is not resumed. |

Restart from scratch (a new goal with the same text, only while nothing of the goal is merged) is not built yet.

Who: the owner or the director; leads and workers are refused. Each action records an event on the goal
(`goal-pause`, `goal-resume`, `goal-stop`) with its reason. `factory goal pause|stop` exits 1 while an agent of the goal is
still closing; the tick keeps retrying the stop.

## What a hold does

While a goal is paused or stopped (`goals.hold`):

- `spawn()` refuses every start for the goal. A command (`factory spawn`, `team`, `relaunch`) exits 3 with "goal G-001 is
  paused by the owner; factory goal resume G-001 lets it start again".
- The tick skips the goal's starts (lead wake, dispatch, review, judge, relaunch) and goes on with the other goals. Each
  skipped start leaves one `spawn-held` event on the goal per agent and hour, so nothing is dropped silently.
- A story run of the workflow engine whose goal is held is not advanced: it starts nobody and records nothing until it
  is resumed.
- `factory up` leaves the goal's lead down.

## In the dashboard

On the goal page (`/goal/G-001`), under the header line, bound to 127.0.0.1:

- **Pause…** (an open goal) or **Resume…** (a paused one) opens its confirmation page, with an optional reason;
- **Stop…** opens a confirmation page (`/goal-control?goal=G-001&action=stop`) that lists the agents it stops and the
  open pull requests it leaves, with an optional reason;
- a paused or stopped goal shows "Paused by the owner since {time}: {reason}" in red;
- the result of the action, or the CLI's refusal, appears under the controls.

The forms use the Settings page's guard (loopback bind, same Origin, the page's form token) and run `factory goal ...` as
a subprocess. On another bind the page shows the commands instead.
