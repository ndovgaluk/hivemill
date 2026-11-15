# Urgent stop

One switch that halts the whole factory: every agent is stopped, nothing new starts and nothing merges until the owner
starts it again (TSR task HM-44). Nothing is deleted.

## How to use it

| Where | Halt | Start again |
|---|---|---|
| Dashboard (bound to 127.0.0.1) | the red **Urgent stop** link in the page header → `/halt` → **Stop everything now** (optional reason) | the banner's **Start again** link → `/halt` → **Start again** |
| CLI (the owner only) | `factory halt --reason "..."` | `factory start` (`--no-up`: only clear the halt) |

The header link opens a confirmation page that says how many agents are queued, starting or running and what a halt
does; nothing happens on the first click. On a dashboard bound to another address the link is not shown and the page
shows the command instead. Both forms go through the Settings page's guard (loopback bind, same Origin, the page's form
token) and run the CLI, which refuses anyone but the owner.

## What a halt does

`factory halt`:

1. sets the config key `factory_halt` to `1` and records the event `halt` (entity `factory`) with the reason;
2. cancels every queued start and stops every live agent, HQ included (workers, leads, director, boss), with the forced
   stop path of `factory stop --now`;
3. prints one line per agent (`stopped`, `cancelled`, or `still closing: <why>`) and exits 1 while any is still closing.

While `factory_halt` is `1`:

- `spawn()` refuses every start, for every caller (`factory spawn`, `team`, `up`, `relaunch`, a director started on
  demand), with exit 3 and "the factory is halted by the owner (factory halt); start it again with factory start";
- `factory judge` refuses the same way (no merge, no reject);
- the tick only reaps panes that exited, retries the stops that did not close (at most once per `stop_timeout_s`) and
  exports state. It starts, dequeues, wakes, nudges and relaunches nobody, runs no review, judge or mechanical merge
  step, checks no drift and launches no `factory-workflow tick`;
- every dashboard page shows a red banner: "Factory halted since {time}: {reason}", the count of agents still closing,
  and a link to Start again.

Left as they are: goals, tasks and their states, pull requests, branches, worktrees, the dashboard and the tick timer.

## Start again

`factory start` sets `factory_halt` back to `0`, records the event `start`, then runs `factory up`: the boss, the
director and the leads of active goals come back. Goals and tasks keep the states they had; workers are started again
by the normal tick flow.

## When an agent does not close

`factory halt` exits 1 and names it (`still closing: close-failed`, `process-unknown`, ...). The halted tick retries it
at most once per `stop_timeout_s` (300 s by default); the banner counts it until it is closed. Check it as for any
failed stop (`docs/updating-persistent-agents.md`, `factory agents`): the pane may still be open in herdr, or a claude
process may still run its session. A `starting` agent is stopped by the tick once it is live.

## Notes

- `factory_halt` is set only through `factory halt` and `factory start` (or `factory config factory_halt` by the owner);
  a director or an agent is refused.
- A halt takes the tick's lock while it stops agents, so no tick can start one in between.
