# MCP access (TSR, MTS) for Claude in WSL and in the factory

## Q: Does Claude in the factory (Claude in Ubuntu) have access to external MCPs hosted on this machine, like MTS or TSR?

Short answer: your own Claude in Ubuntu only has your claude.ai connectors. In the factory, only the **boss** agent can use MCP servers; all other agents get none, on purpose.

**Your Claude in Ubuntu** (`claude mcp list` there):

| Server | Status |
|---|---|
| claude.ai Claude Docs | ✔ connected |
| claude.ai M5 | ✔ connected |
| claude.ai Taskosaur Public | ✘ HTTP 404, the same failure as on Windows |

These are connectors from your claude.ai account, so they follow your login to any machine. Your **local** MCP servers (the Taskosaur stdio plugin, MTS, git) are configured only in your Windows Claude Code.

**Factory agents** (from the code):
- **Every role except boss** starts with `--strict-mcp-config --mcp-config '{"mcpServers":{}}'` (`bin/factory_cli.py:10411`). Their settings also set `ENABLE_CLAUDEAI_MCP_SERVERS=false`, so coders, reviewers, QA, judge and the rest have **no MCP servers at all**.
- **Boss** has no such restriction. The code comment says "the owner works in the boss pane with the claude.ai connectors". Boss sees your claude.ai connectors plus any MCP servers you add to Claude Code inside Ubuntu.
- The role plugins are deliberately text-only, with no MCP config, and tests enforce that.

So in practice: you talk to boss, and boss can use TSR or MTS for you. The workers can't reach them.

**Reaching MCP servers hosted on Windows:** WSL2 runs on its own virtual network by default, and inside Ubuntu `127.0.0.1` means Ubuntu itself, not Windows. Pick one:
1. Turn on WSL's mirrored networking: in `C:\Users\Dell\.wslconfig`, put `networkingMode=mirrored` under a `[wsl2]` section, then run `wsl --shutdown`. After that, Windows `localhost` ports are reachable from Ubuntu.
2. Run those MCP servers inside Ubuntu instead.

**Security issue:** `claude mcp list` prints the Taskosaur Public connector URL in full, and that URL contains a Taskosaur access token. Anything that runs that command or logs it can read the token, including a boss agent. Consider rotating it and using a connector setup that doesn't put the token in the URL.

---

## Q: let's do it using option #1

I created `C:\Users\Dell\.wslconfig`:
```
[wsl2]
networkingMode=mirrored
```
It takes effect after `wsl --shutdown`, which closes everything running in Ubuntu (herdr, Claude Code in Ubuntu, the VS Code WSL window). After the restart, `wslinfo --networking-mode` reports `mirrored`. (Done: confirmed `mirrored`.)

---

## Q: It's mirrored now. What to do next to enable the MCPs on Ubuntu? I have auth tokens for both MCPs via HTTP streaming

Mirrored networking works: Ubuntu now reaches Windows `localhost`.

| Endpoint (from Ubuntu) | Result | Meaning |
|---|---|---|
| Taskosaur `127.0.0.1:4000/api/health` | 200 | backend reachable |
| Taskosaur `127.0.0.1:4000/api/mcp` | 401 | MCP endpoint is there, needs your token |
| MTS `127.0.0.1:4801/api/mcp` | no connection | MTS wasn't running then |

Add them to Claude in Ubuntu yourself, so the tokens never pass through the chat. Start each line with a **space**: Ubuntu's default bash setting then keeps it out of `~/.bash_history`.

`--scope user` makes them available in every folder for Claude in Ubuntu, which should include the factory's **boss** (not verified that boss reads this same user config). The other roles stay MCP-free by design.

---

## Q: Check MTS one more time

MTS is reachable from Ubuntu — use **port 4800**, not 4801.

| Probe | Result |
|---|---|
| Windows: `localhost:4801/api/mcp` | 405 |
| Ubuntu: `127.0.0.1:4801/api/mcp` | timeout. The Vite front end listens only on IPv6 `::1`, which isn't shared with Ubuntu |
| Ubuntu: `127.0.0.1:4800/…` | reachable |

Port 4801 is MTS's Vite dev front end (`D:\_DEV\MeetingToSpec\apps\web\vite.config.ts`). Vite passes `/api/...` to the MTS server on 4800 (and strips `/api`). Ubuntu can reach the server on 4800 directly.

---

## Q: Yes, make the change for the MTS repo

I didn't change the MTS repo, because the change isn't needed: Ubuntu can already reach the MTS MCP server directly.

- `GET http://127.0.0.1:4800/mcp` → 405, and `POST` without a token → **401**. So the MCP endpoint is there and asks for your token.
- That's the address the MTS docs give for the main checkout (`D:\_DEV\MeetingToSpec\docs\mcp.md:46-53`), and their example uses the same `Authorization: Bearer` header.

**I got the path wrong earlier.** I suggested `…:4800/api/mcp`. The correct one is `…:4800/mcp`. The `/api` prefix only exists on the Vite side (4801), whose proxy strips it before forwarding to 4800. That's why the Windows config uses `localhost:4801/api/mcp`.

```
 claude mcp add -s user --transport http mts http://127.0.0.1:4800/mcp --header "Authorization: Bearer {MTS_TOKEN}"
```

If you still wanted 4801 from Ubuntu: one line in `vite.config.ts`, `server: { host: "127.0.0.1", ... }` (would need a TSR task under that repo's epic).

---

## Q: Can we do the same for TSR?

TSR needs no change either, and the docs confirm the token form.

- The backend serves MCP over Streamable HTTP at **`/api/mcp`**, on the same port as the API (`D:\_DEV\Taskosaur\backend\src\main.ts:53-61`, `tools/taskosaur-mcp/README.md:42-54`).
- It accepts `Authorization: Bearer <token>` or `Basic base64(email:password)`. A key in the URL path is "used exactly like `Authorization: Bearer <key>`", and the backend accepts `tsr_pat_…` tokens. The header form is better: the token doesn't show in `claude mcp list`.
- From Ubuntu: `127.0.0.1:4000/api/health` → 200, `/api/mcp` → 401 without a token. IPv4, so no IPv6 problem.

```
 claude mcp add -s user --transport http tsr http://127.0.0.1:4000/api/mcp --header "Authorization: Bearer {TSR_PAT}"
 claude mcp add -s user --transport http mts http://127.0.0.1:4800/mcp --header "Authorization: Bearer {MTS_TOKEN}"
claude mcp list
```

Notes:
- The claude.ai **Taskosaur Public** connector (ngrok URL with the token in its path) also loads in Ubuntu and keeps failing (404). Once local `tsr` works, you could remove it in claude.ai settings.
- The Taskosaur backend listens on `0.0.0.0:4000` (every interface): other devices on your network can reach its API and MCP endpoint (they still need a token).

---

## Q: Does Claude in WSL see the TSR skill? / How can we sync the skill to WSL?

It didn't: Ubuntu has its own `~/.claude`. I linked the skills instead of copying, so there's one source and edits on Windows show up in Ubuntu at once:

| In Ubuntu `~/.claude/skills/` | Points to |
|---|---|
| `working-with-taskosaur` | `C:\Users\Dell\.claude\skills\working-with-taskosaur` |
| `com-tsr` | `C:\Users\Dell\.claude\skills\com-tsr` |
| `mts-task` | `C:\Users\Dell\.claude\skills\mts-task` |

To link another skill later: `ln -s /mnt/c/Users/Dell/.claude/skills/<name> ~/.claude/skills/<name>`. I didn't link the whole folder (80+ `gsd-*` skills built around Windows). Restart Claude in Ubuntu to pick them up.

---

## Q: Let's make these skills OS-agnostic (Linux, Windows, macOS)

The three skills now work on Windows, Linux/WSL and macOS. A new **"Platform"** section in `working-with-taskosaur/SKILL.md`:
- the Taskosaur repo is found with `git worktree list` (first entry) instead of the fixed `D:\_DEV\Taskosaur`; worktrees are `{main checkout}/.claude/worktrees/C1…C4`;
- forward slashes in commands (they work on Windows too);
- a per-OS table: ports (`ss -ltnpH "sport = :P"` / `lsof -nP -iTCP:P -sTCP:LISTEN` / `Get-NetTCPConnection`), processes (`pgrep -af` / `pgrep -lf` / `Get-CimInstance Win32_Process`), env vars;
- the repo's `.bat` scripts only on Windows, plain `npm` everywhere else;
- Taskosaur tools over the stdio plugin or HTTP `/api/mcp`; `attach_file` falls back to `attach_file_content` over HTTP;
- git MCP only when it can reach the repo, else the git CLI.

`e2e-run.md`, `worktrees.md`, `committing.md`, `creating.md`, `updating.md`, `planning.md` and `com-tsr` were updated to use it. Linux commands tested in Ubuntu; macOS commands untested. Rules from the Windows global `CLAUDE.md` don't exist in Ubuntu until a `~/.claude/CLAUDE.md` is added there.
