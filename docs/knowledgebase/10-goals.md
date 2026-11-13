# Goals

## Q: Explain what a goal is in the context of the factory

A **goal** is one piece of work you ask the factory for, stated as an outcome: "what should be true when it's done", not "which files to change". Everything the agents do hangs off a goal.

**What a goal holds** (from `factory goal new` in `docs/examples/01-goal-to-merged-pr.md`):

| Field | Example | Purpose |
|---|---|---|
| id | `G-001` | Generated |
| title | "Launch the public landing page" | Short name |
| project | `acme-web` | **Exactly one project**, meaning one repo |
| intent | "Ship a simple landing page for the Acme web shop." | The why, in a sentence or two |
| success criteria | "1. Hero section is live. 2. Pricing table is live. 3. Contact form delivers messages." | How "done" is checked at the end |
| priority | `2` | Ordering against other goals |
| token limit (optional) | `--token-limit N` | Cost cap: past it, no new coder or pm agents start on this goal |

**You don't create goals by hand.** You describe what you want to the boss in plain English, and **only the boss** runs `factory goal new`. It turns your words into the fields above and asks you if something is unclear.

**What happens to a goal:**
1. **Staffing:** the director gives it a team and a lead. The goal gets its own herdr workspace.
2. **Planning:** the pm breaks it into **tasks** (`T-1262` style). Each task has acceptance criteria, and most become one PR. That's why the commits in this repo are titled `T-1262: …`.
3. **Building:** a coder takes each task, writes code on a `factory/<task-id>` branch and opens a PR.
4. **Checking:** a separate reviewer and QA give verdicts, and the judge merges only if both pass and CI is green. A rejected PR goes back with a stated cause.
5. **Audit:** when all tasks are done, the pm checks each success criterion against evidence (at most 2 audit rounds; a third goes to the director). Gaps become follow-up tasks; merged tasks are never reopened.
6. **Sign-off and close:** the director signs off the audit, then the goal is closed. You (the owner) can force-close, but that's logged as an override.

**Goal vs task:** you think in goals; the factory thinks in tasks. One goal → a plan → several tasks → several PRs.

**Writing good goals:**
- One outcome per goal. "Add CSV export" and "redesign the dashboard" are two goals.
- Make success criteria checkable: "`factory serve` shows token cost per goal on /goals", not "better cost visibility".
- Mention constraints up front: what must not change, deadlines, a token budget.
- If you only want a report rather than a code change, say so; the docs describe a research path (`docs/research-team.md`).

---

## Q: G-001 was created

G-001 is live, and the factory has already taken it up.

**What the boss made of the request:** "Opt-in worktree reuse for coder tasks (worktree_reuse)", in project `hivemill`, priority 2, status active. It turned one paragraph into **6 success criteria**:
1. **Off by default:** identical to today, and existing tests unchanged.
2. **On:** a second task reuses the first task's freed worktree, with `node_modules` still there.
3. **Isolation:** no leftover files, changes or git config, and the guard runs again.
4. **Concurrency:** an atomic claim in the database.
5. **Clean-up:** at most N pooled worktrees, never one that's in use.
6. **Tests** through the real CLI against real git repos, everything green and merged.

It also wrote down the **why** (stop throwing away dependency state on every task), which the pm's audit will check against.

**Already moving:** the director staffed team **`g-001-a`** and started its **lead** (`lead-g-001-a`, Opus 5.5, herdr pane `w3:p2`). The lead has a pm plan the tasks, then starts coders.

**Where to watch:** herdr (a new workspace for G-001 in the `spaces` list), **http://127.0.0.1:8765/goals**, or `factory goal show G-001` and `factory agents`.

---

## Q: (coder-t-0002 pane: started T-0002)

The plan the pm wrote for G-001 (the `T-0001` planning task is done, so build tasks start at T-0002):

| Task | Status (then) | What | Covers success criteria |
|---|---|---|---|
| **T-0002** | in progress (`coder-t-0002`, Sonnet 5.5) | `worktree_reuse` + `worktree_pool_max` config and the DB claim | 1, 4 |
| T-0003 | to do | spawn claims a pooled worktree and resets it | 2, 3, 4, 6 |
| T-0004 | to do | `factory clean` releases merged worktrees, keeps the pool | 4, 5, 1, 6 |
| T-0005 | to do | end-to-end reuse lifecycle test + docs | 6, 2, 5 |

Every task is tagged with the success criteria it covers (`[SC1][SC4]` …), which is what the pm's audit checks at the end.

What the coder did first: set T-0002 to `in_progress`, fetched `origin/main`, read how `task_clones`, `flags.json` and the DB schema/migrations work to follow the existing patterns. It runs in its own worktree under `~/factory/worktrees/`. The deny rules cover `~/factory/bin`, `tests`, `web`, `.git` and so on, but not `worktrees/`, so it can edit its own copy and nothing else.

Next: the coder opens a PR on the fork → CI `unittest` runs → reviewer and QA agents start → the judge merges if everything passes → T-0003 starts.
