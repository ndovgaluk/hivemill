# How the factory integrates with herdr

## Q: How is the integration with herdr done?

The factory **drives herdr from the outside**: it runs the `herdr` command-line tool as a subprocess, with herdr's API socket pinned. It never embeds herdr or opens the socket itself. The agents themselves don't use herdr at all.

**1. The connection**
- The **herdr server** runs on its own as the systemd unit `herdr-server` (the installer set it up), keeping one persistent session for the factory.
- Every factory call goes through one wrapper, `herdr(*args)` (`bin/factory_cli.py:1519`). It runs `herdr …` with `HERDR_SOCKET_PATH` set to the factory's socket: config `herdr_socket`, default `~/.config/herdr/herdr.sock` (line 1182). herdr answers in JSON, which the factory parses.
- The factory is the only one allowed to use it. **Agent shells get a deliberately dead socket** (`DEAD_SOCKET = /proc/nonexistent/worker-no-herdr.sock`, line 878), so an agent that runs `herdr` by hand can't reach or control the live server. That stops one agent from typing into another's pane or closing it.

**2. What the factory uses herdr for**

| Purpose | herdr commands | Where it happens |
|---|---|---|
| **Layout**: HQ workspace, one workspace per goal, team tabs, splitting panes (up to 3 per tab) | `workspace create/list`, `tab create/rename/list`, `pane split/list` | `place()`, when an agent is spawned |
| **Starting an agent**: export its environment, `cd` to its folder (e.g. the worktree), launch `claude` with its role settings and model | `pane run` | spawn |
| **The 📬 nudge and kick-off prompts**: typing "Run factory inbox…" or the agent's first instructions into its pane | `agent prompt` (and `send-keys` Enter for Cursor, whose prompts wait for Enter) | tick, spawn |
| **Status**: is the agent working, idle or done, and what is its process doing | `agent list`, `pane process-info`, `agent read`/`pane read` (screen text) | tick: confirming starts, spotting stuck or finished agents |
| **Labels**: tab titles and metadata you see in herdr (e.g. `coder-t-0002`) | `pane/workspace report-metadata`, `tab rename` | spawn, relaunch |
| **Clean-up**: closing a finished agent's pane, reusing idle shells | `pane close` | reaping, `factory clean` |
| **Waiting** for an agent to finish a prompt | `agent wait` | relaunch flows |

**3. Where the herdr state lives**
- The **database** is the source of truth: each agent row stores its `pane_id` (e.g. `w3:p4`), and the config stores the HQ workspace id.
- herdr is only the terminal host. If a pane disappears, the tick sees it through `agent list` and marks the agent lost or done; it never assumes herdr's view is complete.

**4. The alternative backend.** Config `terminal_backend` can choose **`hc`** (herdr-core). It takes the agent's status from what the agent reports (an OSC 7501 status code) instead of reading the screen, uses its own socket (`HC_SOCKET`), and builds no workspace/tab layout. This install runs on the default: `factory res` showed `terminal backend: herdr (config=auto; effective=auto→herdr)`.

**From your side:** you attach to the same session with `herdr` in an Ubuntu tab. That's an ordinary client on the same server, so you see the panes live and can type into them, which is how you talk to the boss.

## Q: What does the sign next to the boss in the herdr sidebar mean? (2026-11-14)

It's a mailbox badge: 📬 plus a number. **📬4 means the boss has 4 unread factory messages.**

**Where it comes from:** `bin/factory_cli.py`, in the tick's sidebar step:
- Every minute the tick labels each live agent's herdr pane as `{role}·{task, team, goal or hq}`, here `boss·hq`.
- For the **boss only**, it counts the boss's messages with no read time (`messages` where the recipient is the boss and `read_at IS NULL`). If there are any, it appends ` 📬{n}`.
- The code comment gives the reason: *"badge instead of a nudge: never types into the owner's input"*. Other agents get nudged by text typed into their pane when mail waits. The boss pane is where you type, so it gets a quiet badge instead.
- The label is sent with a 3-minute lifetime and refreshed every tick, so it tracks the count within about a minute.

**What clears it:** the boss reading its mail (`factory inbox` run by the boss). The badge disappears on the next tick.

**To see what's waiting without marking anything read**, run as owner:

```
factory inbox --agent boss --peek
```

(Not run when this was answered, so the content of those 4 messages wasn't seen.)

**Other badge in the same sidebar step:** the HQ and goal workspace labels get the agent count and free memory, and `{status} · done/total tasks` per goal.

## Q: Why does it take so long for the boss to read all messages? (2026-11-14)

The boss reads mail only when it runs `factory inbox` itself: when you talk to it, or when the tick wakes it. The tick wakes it only when **all** of these hold (`bin/factory_cli.py` tick step 3, `_boss_wake_qualifying`):

- the boss pane is idle and you aren't typing in it;
- the message is an **escalation or request** (reports, plain msgs, decisions and alerts never wake it);
- it is at least **15 min** old (`boss_wake_after_s` = 900);
- the boss wasn't woken in the last **30 min** (`boss_wake_cooldown_s` = 1800).

So other kinds sit until you speak to the boss, and even urgent ones wait 15–30 min.

To speed it up: `factory config boss_wake_after_s 300` and `factory config boss_wake_cooldown_s 600`, or just tell the boss "read your inbox".
