# Who runs `factory project add`

## Q: Who runs "factory project add"? Or should I tell the boss to add the project and give it the location in the file system?

Either works: **you (the owner), the boss or the director** may add projects. The CLI enforces it: `cmd_project` (`bin/factory_cli.py:2836`) calls `require_role(con, "boss", "director")` for `add` and `update`, and you count as the owner, who passes every role check. Workers can't (coder/qa only inside a throwaway test home, `docs/worker-guard.md`). The boss's own instructions say "a new repo or area needs `factory project add` first", so it knows to do this.

**Option A: you run it yourself (recommended)**
From a **plain Ubuntu terminal**, not from inside an agent's herdr pane:
```
factory project add taskosaur --name "Taskosaur" --repo ~/src/Taskosaur --gh ndovgaluk/Taskosaur --base master --required-checks "<CI job>"
factory project list
```
Why "plain terminal": `docs/SETUP.md` says commands run as yourself count as the owner, but inside an agent's pane the identity guard treats you as that agent, and `project add` is refused.
Why I'd do it yourself:
- It's one command, done in seconds, with exactly the values you choose.
- You already know the facts it needs (repo path, GitHub repo, base branch, which CI job must be green), which the boss would have to ask you for anyway.
- The repo must **already be cloned** in Ubuntu: `project add` only records the path, it doesn't clone. I haven't checked whether the boss's guard rules let it clone repos, so doing the clone yourself avoids that question.

**Option B: tell the boss**
Fine too, as long as you give it everything:
> Register project `taskosaur`: repo at `~/src/Taskosaur` (already cloned), GitHub `ndovgaluk/Taskosaur`, base branch `master`, required check `<CI job>`. Then create a goal for it: …

It runs `factory project add` with those values (it may confirm details first).

**Changing a project later** (`factory project update`):
- `--required-checks` → owner, boss or director.
- `--repo` (location), `--gh`, `--gate-cmd`/`--gate-count-cmd`/`--gate-timeout-s` → **director or owner only** (line 2859: "the gate command and the repo location steer the host"). The boss can't move a project.

**Before registering Taskosaur or MTS**, remember the caveats in `20-multiple-projects.md` (shared ports/databases with Windows via mirrored networking, `.env` secrets, npm install per task).
