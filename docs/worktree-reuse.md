# Worktree reuse (`worktree_reuse`)

By default every coder task gets a freshly created git worktree (`worktrees/<goal>-<task>`), and `factory clean` deletes it once the task is merged. That throws away ignored build and dependency state (`node_modules`, caches) on every task. With `worktree_reuse=1` the factory keeps a small pool of finished worktrees per project and hands one to the next coder task instead.

## Config keys

| key | default | meaning |
|---|---|---|
| `worktree_reuse` | `0` | `1` = a new coder task claims a free pooled worktree of its project; `0` = off, behaviour identical to before. Anything else is refused (exit 2). |
| `worktree_pool_max` | `2` | Free pooled worktrees `factory clean` keeps **per project**. Integer 0..50; anything else is refused (exit 2). |

Set with `factory config worktree_reuse 1` and `factory config worktree_pool_max <n>` (director or owner).

## Lifecycle: claim, release, trim

The state lives in the DB table `worktree_pool` (`path`, `project_id`, `state` = `free` or `claimed`, `task_id`, `reset_ok`, `claimed_at`, `released_at`), never in a filesystem marker.

1. **Release.** `factory clean` finds a merged, finished task whose worktree is clean (no tracked changes, no unpushed commits, no live pane or agent). With the flag on it does not delete the directory: it detaches HEAD at `origin/<base>`, removes untracked non-ignored files, deletes the task branch, inserts a `free` row and clears `tasks.worktree`. Output marks it `pooled`; event `worktree-pooled`.
2. **Claim.** `factory spawn coder` for a task without a worktree takes the oldest free row of the same project. The claim is one `UPDATE ... WHERE state='free'` inside `BEGIN IMMEDIATE`, so two spawns started at the same time can never get the same row. The row becomes `claimed` for that task and `tasks.worktree`/`tasks.branch` are set; event `worktree-claimed`.
3. **Reset** (see below), then `reset_ok=1`; event `worktree-reused`.
4. **Trim.** After pooling, `factory clean` removes free rows beyond `worktree_pool_max` per project, oldest `released_at` first (event `worktree-pool-trimmed`). **Claimed worktrees are never removed by trim**, and clean never deletes a worktree that is claimed by a task that is not done. This holds even when the pool is over `worktree_pool_max`: `factory clean` refuses to remove a claimed worktree, and the pool simply stays above the cap until the claim is released.

A reused directory keeps the name of the first task that created it (for example `worktrees/G-001-T-0001` serving T-0002); only `tasks.worktree` says who owns it.

## Reset steps

Before the coder starts, the claimed worktree is made to look like a fresh `git worktree add`:

1. The ownership check (below) must pass.
2. Per-worktree leftovers are removed: `config.worktree`, `MERGE_HEAD`, `CHERRY_PICK_HEAD`, `REVERT_HEAD`, `BISECT_*`, `rebase-merge`, `rebase-apply`, `sequencer`, and refs under `refs/worktree` and `refs/bisect`.
3. The git config guard runs on the worktree. If it refuses, the claim is rolled back and spawn exits 4 (`git-config-refused`), the same as for a fresh worktree.
4. `git checkout -f -B factory/<task> origin/<base>`, `git reset --hard`, `git clean -f -f -d` (no `-x`, so **ignored files stay**).
5. The pre-push public-text hook is (re)installed.

Result: HEAD is on the task branch at `origin/<base>`, `git status --porcelain --untracked-files=all` is empty, ignored files such as `node_modules/` are still there.

## Interaction with `task_clones`

`task_clones=1` wins. A coder task that would get a per-task clone gets the clone; the pool is not consulted and `worktree_reuse` is ignored for it. See [git-hardening.md](git-hardening.md#per-task-clones).

## Failure fallback and stale-claim recovery

- **Fallback.** A free row whose directory is gone is deleted (`worktree-reuse-failed`) and the next row is tried. A worktree that cannot be reset is removed (or kept and alerted if the ownership check fails) and spawn goes on to the next row, and finally to a fresh worktree. A reuse failure never fails the spawn by itself; only a refused git config does.
- **Crash during spawn.** A claim with `reset_ok=0` whose spawn died before the reset finished is redone on the next spawn of that task (the guard runs before the fetch).
- **Stale claims.** `factory clean` judges every `claimed` row: a missing path is dropped (`worktree-pool-stale`); a claim whose task is `done` or `cancelled` and no longer records the path, with a clean worktree and no live agent or pane, is released to the pool. Anything else is kept with a reason (`stale claim kept: ...`).

## Ownership check

Pool functions touch a worktree only after `worktree_owns_gitdir` confirms its `.git` points at that project repo's own `.git/worktrees/<name>`. A worktree or clone whose `.git` points elsewhere, is a symlink, or carries `commondir`/`gitdir` redirects is **kept, never deleted**, and the director is alerted (`worktree-reuse-refused`, `gitdir mismatch`).

## Turning it off

```
factory config worktree_reuse 0
factory clean
```

With the flag off `factory clean` removes every free pooled worktree and its row (claimed ones stay until their task is finished), and the next coder spawn creates a fresh `worktrees/<goal>-<task>`.

## Tests

`tests/test_worktree_reuse_spawn.py` class `Lifecycle` drives the whole sequence through the real CLI and real git: fresh worktree, pool, reuse with `node_modules` intact, a concurrent task getting a fresh worktree, cap trimming, and turning the flag off.

## Known limits

- **TOCTOU.** A worker running as the same uid can swap a worktree's `.git` between the ownership check and the git call that follows. Accepted residual (director M128); the check narrows, but cannot close, this window.
- **`core.worktree`.** A per-worktree config entry `core.worktree` that redirects the work tree elsewhere is not checked (T-0006 review M175).
- **Variants in the pooled reset** (T-0003 review M191): `git_config_guard` and the pre-push hook install run through `wt/.git` rather than the pinned git dir, so a swap during the reset can affect them; a swap mid-reset can leave the pooled worktree on the task branch, so the fresh-worktree fallback fails with "already checked out"; and the claim loop has no iteration cap if the ownership answer flips between iterations.
- **Go.** `spawn` and `clean` are not ported to Go; only the two config keys are mirrored there.
