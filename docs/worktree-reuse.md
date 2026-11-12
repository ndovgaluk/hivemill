# Worktree reuse: `factory clean` side

Config: `worktree_reuse` (0/1, default 0) and `worktree_pool_max` (free pooled worktrees kept per project, default 2).

With `worktree_reuse=1`, `factory clean` keeps a worktree it would otherwise remove, as a free pooled worktree:

- Gate: `clean_verdict` runs first, unchanged (merged, clean, no untracked files, no live agent or pane, nothing unpushed).
- Admission: a linked worktree (not a clone), not locked, whose HEAD tree has no `.gitmodules`, while the project has fewer than `worktree_pool_max` free rows.
- Release: detach at `origin/<base>`, `reset --hard`, `clean -f -d` (ignored files such as `node_modules` stay), delete the task branch, insert a `worktree_pool` row (`state='free'`), set `tasks.worktree` to NULL, event `worktree-pooled`. Row action `pooled`. Any git failure falls back to removal.
- Trim: free rows beyond the cap (0 when reuse is off) are removed, oldest `released_at` then `path` first, unless a live pane or agent sits in the dir. Claimed rows are never trimmed. Event `worktree-pool-trimmed`.
- Stale claims: a claimed row whose path is gone is dropped; one whose task is done/cancelled but no longer records the path is released to the pool when the dir is clean and unused, else kept with `stale claim kept: <why>`. Event `worktree-pool-stale`.
- Pooled dirs are not reported as orphans. The `total:` line gains `, N pooled` only when the flag is on or the pool table has rows.
