# The installation, projects and how changes take effect

## Q: What's next to set up herdr and run the factory? Do we run a factory per project or can it work with multiple projects?

**One factory can serve several projects.** You install it once and register each repository with `factory project add`. The database has a `projects` table, every goal belongs to one project (`goals.project_id`), and each project can have its own base branch, auto-merge setting and required CI checks (`docs/SETUP.md`, step 5). When you give the boss a request, it becomes a goal in one project.

**Next steps, in order:**
1. **Dry run of the installer** (changes nothing), set to clone **your fork**:
   ```
   cd ~/src/hivemill
   python3 plugins/hivemill/scripts/install.py --dry-run --repo-url https://github.com/ndovgaluk/hivemill.git --max-agents 6
   ```
2. **Real install** (`--yes`). It clones into `~/factory`, links the `factory` command, creates the database, installs the systemd units (`herdr-server`, `factory-up`, the per-minute `factory-tick` timer) and runs a smoke test. That also covers the herdr setup. `~/factory` is the live copy the agents work on; `~/src/hivemill` stays your dev copy.
3. **Register your projects:** `factory project add <id> --name "<name>" --repo ~/src/<repo> --gh ndovgaluk/<repo>`. Each project needs a clone inside Ubuntu, a GitHub repo the factory can push to, and a build/tests that run on Linux.
4. **Start it:** `factory up` starts boss and director. Attach with `herdr`, open the boss's pane, describe what you want built. Web UI: `factory serve --bind 127.0.0.1`.

**Watch out for:**
- **Port clashes.** With mirrored networking, Windows and Ubuntu share ports. If agents start a Taskosaur dev stack on 4000/4001 or MTS on 4800/4801 in Ubuntu, it collides with the stacks on Windows — and agents' tests could hit your real Windows instances.
- **Usage.** Up to 6 Claude agents at once draw on your Claude Max limits.
- **MCP:** only the boss gets TSR and MTS.

---

## Q: (the dry-run output)

| Step | What happens | Comment |
|---|---|---|
| 1–3 | Checks prerequisites, tools, logins | Passed in `--check` earlier |
| 4 clone | Clones **your fork** into `~/factory` and checks out tag **`v0.4.0`**, the latest release | Clones into a temporary folder and renames it at the end, so a failed clone leaves nothing half-done |
| 5 link | `factory` command into `~/.local/bin` | |
| 6–7 | Creates the DB, keeps the web UI on `127.0.0.1` only, caps live agents at 6 | The web UI has no login, so localhost-only matters |
| 8 project | **Empty**, since no `--project-*` options | Register projects afterwards |
| 9 services | Installs the systemd units and **starts them right away** | `factory-up` **spawns boss and director immediately**, so Claude usage starts with the install |
| 10 smoke | Version check, boss and director live or queued, web UI responds | |

Port 8765 was free on Windows. Undo: `systemctl --user stop factory-up factory-tick.timer factory-serve herdr-server`; `~/factory` can be deleted afterwards. If the installer exits with code 3, it needs something from you (it prints the command); rerun with `--resume`.

---

## Q: What's the purpose of installation?

The installation turns the code into a **running factory**. The source code (`~/src/hivemill`) is for reading, changing and testing; the install creates the separate, live system that actually does work.

| Piece | Why it's needed |
|---|---|
| **`~/factory`**: a clean copy at a release (v0.4.0) | The agents work from this copy, and the factory improves itself through PRs here. Keeping it apart from `~/src/hivemill` means your edits never break the running factory, and its agents never touch your dev copy |
| **`factory` command** | So you, timers and the agents can run `factory goal …`, `factory agents` and so on from anywhere |
| **Database** (`~/factory/db/factory.db`) | The factory's memory: projects, goals, tasks, messages between agents, review verdicts, an event log. Agents coordinate only through it |
| **Settings** (agent cap 6, web UI on localhost only) | Limits how many Claude agents run at once and keeps the unauthenticated web UI private |
| **systemd services** | Keep it running without you: the herdr server hosts the agent terminals; the **tick** runs every minute to start queued agents, restart stuck ones, nudge idle ones and export state; `factory-up` brings boss and director back after a reboot; `factory-serve` is the web dashboard |
| **Smoke test** | Proves it all came up |

**What you get after it:** you open the boss's pane in herdr and describe what you want. The boss turns it into a goal; the director staffs a team (lead, coder, QA, reviewer); they plan, write code on branches and open PRs; a separate reviewer and QA check each PR, and a judge merges only when both pass and CI is green. Without the install, nothing would run agents, keep them alive, or carry work from request to merged PR.

---

## Q: If I need to change factory code, do I need to install it again?

No reinstall. Code changes reach the running factory through git.

1. Change the code in your **dev copy** `~/src/hivemill`, on a branch, and run the tests.
2. Push to your fork and merge the PR into the fork's `main` — or give the factory the change as a goal.
3. **The tick updates `~/factory` by itself:** the CHANGELOG says "the tick fast-forwards `~/factory` main … within a minute". (Documented behaviour; not traced in code.)

| What changed | When it applies |
|---|---|
| CLI and tick code (`bin/factory_cli.py`) | Next `factory` call; the tick runs every minute |
| Role prompts (`roles/*.md`) | **Only for newly spawned agents** |
| Role settings and hooks | Rendered again on every spawn and relaunch |
| Go worker guard | Rebuilt by `factory up` and the tick when `go/` changes, used only when `guard_impl=go` |
| Web UI (`web/`) | Probably needs `systemctl --user restart factory-serve` (inference) |
| Database schema | Migrated automatically on the next `factory` command |

Don't edit `~/factory` directly: the tick fast-forwards it, so local edits block the update or get mixed in. After install, `~/factory` was confirmed on `main` tracking `origin/main`, so auto-updates work.

---

## Q: (real install) → RESULT FAIL step=smoke

Steps 1–9 went through. The smoke test failed: `scout` was live, but **boss and director weren't started**.

Cause: a startup race. At the same second, the **tick** and **`factory-up`** started; `factory-up` saw the tick's lock, logged `another tick/up is running; skipping`, and exited. The tick only starts other agents; starting boss and director is `factory up`'s job. Fix: `factory up` by hand (spawned director and boss), then `install.py --yes --resume …` → `RESULT PASS url=http://127.0.0.1:8765/ version=0.4.0`.

| Agent | Model | herdr pane |
|---|---|---|
| boss | claude-opus-5-5 | w2:p4 |
| director | claude-opus-5-5 | w2:p3 |
| scout | claude-sonnet-5-5 | w2:p2 |

This race is a real installer bug and a good small goal for the factory itself.

---

## Q: Registering hivemill as a project, and the CI gate

```
factory project add hivemill --name "Hivemill" --repo ~/factory --gh ndovgaluk/hivemill
```
`--repo ~/factory` because the code says "every worktree shares `~/factory/.git`".

Before the first goal, the CI gate needed fixing: `required_checks` was **empty** (the judge would merge on verdicts alone) and the fork showed **no workflows** (GitHub keeps Actions off on new forks). Order matters: enable Actions first (fork → Actions → "I understand my workflows, go ahead and enable them"), then set the check — otherwise every merge blocks waiting for a check that never reports.

After enabling: workflows `tests`, `install`, `release` active; `tests` runs on PRs into `main`, pushes to `main`, manual runs; its aggregate job **`unittest`** (line 527) waits for all shards and guard jobs. Set **per project** so other projects can name their own checks:
```
factory project update hivemill --required-checks unittest
```
The fork is public, so Actions minutes are free.
