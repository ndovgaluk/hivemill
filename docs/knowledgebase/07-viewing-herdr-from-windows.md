# Watching the agents from Windows

## Q: How can I see the herdr terminals when working on Windows? Do I need a dedicated VM for Linux with a UI?

No, you don't need a VM or a Linux desktop. herdr is a **text-mode terminal app**, like tmux, not a graphical program. Any terminal shows it, including Windows Terminal with an Ubuntu tab.

**How you'd watch the agents:**

1. **Attach to herdr from an Ubuntu tab in Windows Terminal:**
   ```
   herdr
   ```
   According to its help, `herdr` alone "launches or attaches to the persistent session". The factory's herdr server runs in the background under systemd (`herdr-server` unit), and this command attaches your terminal to it. You see the agents' panes (boss, coder, reviewer, ...) live and can switch between them. Closing the tab only detaches; the agents keep running. `herdr status` shows whether the server is up.

2. **The factory's web UI in your Windows browser:**
   ```
   factory serve --bind 127.0.0.1 --port 18624
   ```
   (After the real install it runs as a service on **http://127.0.0.1:8765/**.) Requests to localhost reach WSL automatically. It's a read-only dashboard: goals, tasks, agents, PRs and costs. It's often more useful than watching raw panes.

3. **Inside VS Code:** in the WSL window, **Terminal → New Terminal** and run `herdr`. It shows the same session.

**When a dedicated VM makes sense:** not for viewing. Only if you want the factory to run 24/7 regardless of your Windows machine, or to keep it fully separate from your own environment. Even then you'd usually connect over SSH (herdr even has `herdr --remote <ssh-target>`), so no desktop UI would be needed.

---

## Q: (Windows Terminal ˅ menu screenshot)

That's the right menu. Click **Ubuntu** (`Ctrl+Shift+4`) to open a new Ubuntu tab. Then run `herdr`.

**What you'll see before the install:** no factory and no herdr server yet, so herdr starts a **new, empty session**, not agent panes. That's expected. Once the factory runs (`factory up`), the same command shows the agents' panes.

**To save clicks:** make Ubuntu the default tab. **Settings** (`Ctrl+,`) → **Startup → Default profile → Ubuntu → Save**.

---

## Q: (herdr settings → "agent integrations" screen with pi and claude "available")

I'd **press `Esc` and not install** anything there for now.

**Why:**
- Hivemill's docs and code don't mention herdr's "agent integrations" anywhere. The factory talks to herdr through its own CLI calls and doesn't rely on this feature.
- My inference, not checked: installing the **claude** integration probably adds hooks to your global Claude Code config (`~/.claude/settings.json`) so herdr gets status updates. The factory gives each agent role its own settings, with the worker-guard hook as the security check. An extra global hook from herdr would run in every agent too, including your own Claude Code sessions. It may be harmless, but nobody has tested it with the factory, and it would make problems harder to trace.
- **pi** shows as "available" because something on your PATH matches. The factory doesn't use it either.

If you want herdr's status indicators later, enable the integration after the factory is installed and running, and check `~/.claude/settings.json` before and after so you can see exactly what it added.

Don't press Enter on that screen: that's **install**, likely for the two marked `+` (pi and claude).

---

## Q: Does the factory have a herdr setup built in, or do I set the layout myself?

It's built in. You don't set up any layout yourself. The factory creates and arranges all herdr workspaces, tabs and panes on its own (`place()` in `bin/factory_cli.py`, around line 8788).

| herdr workspace | Created when | Tabs and panes inside |
|---|---|---|
| **HQ** | the first boss or director agent starts | a `boss` tab and a `director` tab, plus an `ops` tab for agents not tied to a goal |
| **One per goal**, labelled e.g. `G-001 <goal title>` | work on a goal starts | a `console` tab (a spare shell), plus one tab per team. Each team tab takes up to 3 agent panes, splitting right and then down; a 4th agent opens a new tab `team +1` |

- It finds what already exists before creating anything. The HQ workspace id is stored in the database, and goal workspaces are stored per goal. After a restart it reuses the same workspaces.
- It runs herdr commands with `--no-focus`, so new panes don't take over your screen while you're watching.
- The herdr server itself is started by the `herdr-server` systemd unit. You don't run `herdr server` by hand.
- Your job is just to attach and look: `herdr` in an Ubuntu tab, then switch between the workspaces in the `spaces` list on the left.
- With the alternative terminal backend `hc` (herdr-core), `place()` doesn't create panes at all. The default is herdr.

---

## Q: (agent pane: "Accessing workspace: ~/factory — Quick safety check")

The agents are waiting at Claude Code's **folder trust prompt** for `~/factory`. Until it's answered, the agent can't do anything.

`~/factory` is your own clone of your fork, so it's safe to trust:

1. Press **↓** to select **"Yes, I trust this folder"**, then **Enter**.
2. Check the **director** and **boss** tabs and answer the same prompt there if it shows.

Claude Code remembers the answer for that folder in your Ubuntu `~/.claude.json`, so agents started later in `~/factory` shouldn't ask again. Goal teams may work in other folders (worktrees) and could ask once more for a new path.

The boss's agents-list entry showed **📬4**: 4 unread messages, most likely from the director and scout. It processes them once past the prompt. After that, type `/mcp` in the boss pane to check that `tsr` and `mts` are connected.
