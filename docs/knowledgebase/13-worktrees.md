# Worktrees: where agents change code

## Q: If the agents make changes in the factory's code, which folder will they be changing?

Not in `~/factory` itself, and not in your dev copy `~/src/hivemill`. Each coder gets its **own git worktree** under `~/factory/worktrees/` (`prepare_worktree()` in `bin/factory_cli.py:9164`).

**How a change flows:**

| Step | Where |
|---|---|
| A coder starts a task, e.g. T-12 of goal G-3 | A fresh worktree at **`~/factory/worktrees/G-3-T-12/`**, on branch **`factory/t-12`**, branched from `origin/main` of the project's repo |
| The coder edits, tests, commits, pushes | Only inside that worktree; it pushes the branch to your fork and opens a PR |
| Reviewer and QA check it | The same worktree, read-only, or the PR. They never create branches |
| The judge merges | On GitHub, into your fork's `main` |
| The live factory updates | The tick fast-forwards `~/factory` to the new `main` |

**Folder by folder:**
- **`~/factory`** is the running factory. Boss, director and scout start there, but they don't write code. Its sensitive parts (`bin/`, `roles/`, `db/`, `run/settings/`) are blocked by the deny rules, plus the worker guard. It changes only through the tick's fast-forward after a merge.
- **`~/factory/worktrees/…`** holds one folder per coder task. That's where the edits happen.
- **`~/src/hivemill`** is your own dev copy. The factory never touches it. You take in the factory's merged work with `git pull` there.

**Which repo the worktrees come from** is the project's `--repo` path. The code says "every worktree shares `~/factory/.git`", so for the factory to work on itself, the project is registered with `--repo ~/factory`.

**Setting:** `task_clones=1` gives each task a standalone `git clone --shared` instead of a worktree, for extra isolation (`docs/git-hardening.md`). The default `0` uses worktrees.

---

## Q: Will the coder create a new worktree for every new task, or reuse an existing one, to save time on initialization like "npm install"?

The coder gets a **new worktree for each new task**. It's reused only by the **same** task, for example when the coder is relaunched or reworks after a rejected review.

**What the code does** (`bin/factory_cli.py`):
- **Per task, not per coder.** The path is `~/factory/worktrees/{goal}-{task}`. A coder has no worktree of its own that moves from task to task.
- **Reuse within a task.** If the task already has a worktree on disk, it's reused and switched back to the task's branch (line 9172). Nothing is set up again for a rework round.
- **Clean-up after merge.** `factory clean`, run by the cleaner role or the director, removes worktrees and branches of tasks that are merged or cancelled and clean (line 12311).
- **No dependency setup step.** `prepare_worktree()` only does `git fetch` and `git worktree add`, with no install step. Whatever the project needs (`npm install` and so on), the coder runs itself inside the new worktree.

**What that costs:**
- **Hivemill itself: nothing.** Python standard library only, so a fresh worktree is ready right after the checkout.
- **A Node project like Taskosaur: an `npm install` per task.** With a warm npm cache (`~/.npm`) it mostly avoids downloads, but it still unpacks `node_modules` each time — tens of seconds to minutes for a monorepo (estimate, not measured).

**Ways to cut it:**
1. **In the project:** use **pnpm**, which links packages from a shared store instead of copying them.
2. **In the factory:** a goal like "keep a pool of prepared worktrees per project and reset one to `origin/main` for each new task". That became **G-001**.

---

## Q: Can we use pnpm for Taskosaur and MTS? Should we make a change for the switch?

You can, but I'd **not switch yet**. Measure first.

| | Taskosaur | MTS |
|---|---|---|
| Today | npm workspaces (`tools/taskosaur-mcp`, `frontend`, `backend`), `package-lock.json` | npm workspaces (`packages/*`, `apps/*`), `package-lock.json` |
| Files that mention npm commands | **80** | **21** |
| CI and Docker to change | `.github/workflows/backend-ci.yml`, `Dockerfile.dev`, `Dockerfile.prod` | none |
| Electron app | `desktop/` | `apps/desktop/` |
| Other | Already has a **stale `pnpm-lock.yaml`** (2026-10-31) next to the current `package-lock.json` (2026-11-07) | — |

The TSR skill and the repos' `CLAUDE.md` files also contain `npm run … --workspace=…` commands.

**Risks:**
- **Strict `node_modules`.** By default pnpm only lets a package see dependencies it declares. Nest, Prisma (`prisma generate`), Next and Electron packaging often depend on npm's flat layout. The safer variant is pnpm with `node-linker=hoisted` in `.npmrc`: a flat layout like npm's, still installed quickly from pnpm's shared store (my understanding; untested on these repos).
- **It only helps where the factory works.** These repos weren't registered with the factory, and you develop them on Windows.

**What I'd do instead:**
1. **Measure:** in a throwaway copy of each repo in WSL, time `npm ci` against `pnpm install` with `node-linker=hoisted`, warm cache for both. If the gain is small, stop.
2. **Clean up Taskosaur's stale `pnpm-lock.yaml`** either way.
3. **Only if step 1 shows a real gain:** one Taskosaur task (size M: scripts, CI, two Dockerfiles, desktop build, docs and skills) and a smaller one for MTS.

---

## Q: Can we add a setting for the coding agents to reuse existing worktrees?

Yes. It's a change to the factory itself, and a good **first goal for the factory to build on itself**.

**What the setting would do** (proposed design):
- New config key **`worktree_reuse`**, default `0` (today's behaviour), alongside `task_clones`.
- With `1`, a new coder task takes a **free worktree of the same project** from a small pool instead of `git worktree add`. It resets that worktree to `origin/<base>` on a new `factory/<task>` branch and keeps the ignored files, so `node_modules` stays and the next `npm install` only installs what changed.
- `factory clean` keeps pooled worktrees, up to a per-project limit.

**The tricky parts:**
- **Isolation between tasks:** leftover untracked files, stashes or git config must not leak. `git clean` of untracked-but-not-ignored files, and the existing `git_config_guard` on every reuse.
- **Two coders must never get the same worktree:** a database claim, not a folder check.
- **Clean-up rules** and a cap on the pool size.
- **Risky code** (`DEFAULT_CONFIG`, spawn/worktree code): CI runs the full suite; guard-style tests that reject and accept through the real CLI.

Goal text given to the boss (became G-001):
> New goal for project hivemill: add an opt-in config `worktree_reuse` (default off). When on, a new coder task reuses a free, clean worktree of the same project instead of creating one: reset to origin/{base} on the task's new branch, keep ignored files such as node_modules, remove untracked non-ignored files, and re-run the git config guard. Two tasks must never share a worktree (claim it in the DB). `factory clean` keeps up to N pooled worktrees per project. Success: off = identical behaviour to today; on = a second task in the same project reuses the first task's worktree with ignored files intact; tests for reuse, isolation (no leftover untracked files or git config), concurrency and clean-up, through the real CLI.
