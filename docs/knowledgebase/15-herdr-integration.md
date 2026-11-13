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
