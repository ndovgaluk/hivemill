# 35. Worktree reuse and local-only files, the role prompt budget, the attempt limit, flow debugger times

Answers given on 2026-11-13. Read from the merged code in `~/factory` (branch `main`, G-001 done) and from the working clone; nothing here was tested with a real coder unless it says so.

## Q: With worktree reuse on, when is a new worktree created and initialised?

At coder spawn. `factory spawn coder` for a factory task without a worktree calls `prepare_worktree`:

1. With `worktree_reuse=1` it first tries to claim the oldest free pooled worktree of the same project.
2. If the pool has none, it runs `git worktree add` from `origin/<base>` into `worktrees/<goal>-<task>`. The first coder tasks of a project always get fresh worktrees.
3. The pool is filled later by `factory clean`: after a factory task is merged and its worktree is clean, the folder is kept as "free" instead of deleted, up to `worktree_pool_max` (default 2) per project.
4. A claimed worktree is reset before the coder starts: `git checkout -f -B factory/<task> origin/<base>`, `git reset --hard`, `git clean -f -f -d`. Ignored files stay (that is the point: `node_modules`, caches); untracked files that are not ignored are removed.

The reviewer and QA do not get their own worktree; they work in the coder's. `task_clones=1` wins over reuse. Full description: `docs/worktree-reuse.md`.

## Q: Where is it recorded that a worktree is free?

Only in the factory database, table `worktree_pool` (`path`, `project_id`, `state` = `free` or `claimed`, `task_id`, `reset_ok`, `claimed_at`, `released_at`). There is no marker file in the worktree.

- Who owns a worktree is also on the task (`tasks.worktree`, `tasks.branch`). A reused folder keeps the name of the first factory task that created it.
- Git's own bookkeeping stays under the project repository's `.git/worktrees/<name>`; the factory checks that a worktree's `.git` points there before touching it.
- A fresh worktree of a running factory task has no row; it is recorded only on the task.

## Q: How do `.env`, `.env.test` and `.tsr` (local, never committed) reach a worktree?

They don't. Nothing in the factory copies them.

- A fresh worktree contains only committed files.
- A reused worktree keeps whatever ignored files the previous coder left there: an earlier factory task's copy, not the owner's.
- Untracked files that are not ignored are deleted on every reuse.
- There is no setup command, copy list or per-project setting that runs when a worktree is created (the `projects` table has only the gate commands).

## Q: Can a coder read the main root folder, or only its worktree?

- Its own worktree: read and write.
- The main checkout (`~/factory` for the Hivemill project): read only. The worker guard refuses writes there.
- With the worker sandbox on, `~/factory` stays visible read-only, other tasks' worktrees and the rest of the owner's home are hidden. On this factory the sandbox is off (`sandbox_roles` is empty).
- Not checked: a project whose main checkout is elsewhere in the owner's home (expected to be hidden under the sandbox), and whether the guard lets a coder `cp` from the main checkout.

## Q: What was added so coders set up local-only files?

- `worktree-postinit-rules.md` in the repository root: find the main checkout with `git worktree list --porcelain`; for `.env`, `.env.test`, `.tsr` copy the main checkout's version into the worktree, only if `git check-ignore` passes; skip a file the main checkout lacks (normal, not an error); never commit or print the files, never invent values.
- `roles/coder.md`, step 1: "Root `worktree-postinit-rules.md` exists? Follow it first."
- Commit `e623cab` on branch `hm-1-settings-page`, pushed to the fork. Not on `main`, so the factory does not have it; it reaches only coders spawned after it lands in `~/factory`.

Still open:

- In the Hivemill repository only `.env.test` is git-ignored; `.env` and `.tsr` are not, so a coder would skip them and report to the lead.
- To fit the prompt budget (next question) three existing phrases of `coder.md` were shortened. `docs/planning-rules.md` P8 says existing wording is never compressed, so that part of the commit breaks a project rule. The clean alternative: restore the three phrases and put the pointer in a coder skill or in the project's committed `CLAUDE.md`.

## Q: Where does the 12k limit on role prompts come from?

From the project itself, enforced by `tests/test_repo_hygiene.py`:

- `ROLE_PROMPT_BUDGET_BYTES = 12000`: hard budget for `_common.md` plus any one role file.
- `ROLE_PROMPT_TARGET_BYTES = 11410`: a tighter fail-fast target, and the one that actually bites. `_common.md` + `coder.md` are at exactly 11410.

Reason given in the code: role prompts are loaded by every agent of that role on every start, so detail belongs in a per-role skill under `roles/plugins/<role>/`. Raising the number "is its own PR". The code does not say why 12000 was chosen. Planning rule P8: a task adding role-prompt text states the byte delta and headroom, moves the text into a skill when headroom < delta + 200 B, and never compresses existing wording.

## Q: Is there a limit on round trips between reviewer and coder for one factory task?

Yes, as a rule for the lead, not as a check in the code: three coder attempts on one factory task without a merge, then the lead stops and escalates to the director (`roles/lead.md`, the lead's `fix-loop` skill, `docs/planning-rules.md` L1 to L4).

- Retry briefs say "attempt N of 3" and list every open blocking finding.
- Before the third attempt the lead asks the staff-engineer for one remedy: continue, restructure or stop.
- After a third failure the director decides and can grant more attempts (it did on G-001's T-0004).
- Not counted as attempts: a coder that produced nothing, nit-only findings (the same verifier re-verdicts), evidence-only judge rejects, stale-base and merge-conflict handling.
- The CLI only increments `tasks.attempts`; no refusal on a high count was found (searched by name only). There is no config key for the number 3.

## Q: In the flow debugger, what are "Elapsed" 356h and the lead's 279h 21m?

Both are the debugger's sample data (demo goal G-009, 10 to 25 Oct, and its factory task T-0091), not G-001.

- "Elapsed" is wall-clock time from the goal's creation until now, or until the last event once it is finished.
- "Agent time" is the sum of all agents' session lengths.
- The lead's 279h 21m is one session that stayed open from 9h 36m to 288h 57m after the goal started: session lifetime, not busy time.
- On the task view the lead's whole session is counted, not only the part inside the task's window, so agent time (282h 01m) exceeds elapsed (13h 18m).

Two flaws in `web/flow.py` (`work_of` and the totals), not fixed: clip boss, director and lead sessions to the task window on the task view; and call it "session time", or derive busy time from token transcripts.

G-001 at 07:41 on 2026-11-13: elapsed 8h 06m, agent time 12h 10m.

## Q: What does `/hm master-local-deploy` do?

`/hm` is a local skill (`.claude/skills/hm`, not committed, copied to the Windows checkout). `SKILL.md` is a router; each command is a file under `commands/`, read only when asked for.

`master-local-deploy` runs `scripts/master-local-deploy.sh check|apply` inside WSL:

1. Refuses when `~/factory` is not on `main`, has changed tracked files, or cannot be fast-forwarded.
2. Warns when the working clone's local `main` has unpushed commits (they would not be deployed).
3. `apply`: backs up the database to `~/.local/state/factory/deploy-backups` (last 3 kept), fast-forwards to `origin/main`, compiles the CLI, runs `factory --version`, prints a rollback command.

"master" means `main` as pushed to the fork. Check mode was run (up to date at `a617aa4`); the update path was not.
