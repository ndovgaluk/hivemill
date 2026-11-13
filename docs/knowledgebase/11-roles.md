# The 14 roles

## Q: Give me the list of all roles available in the factory and their responsibilities

The factory has **14 roles** (`ROLES` in `~/factory/bin/factory_cli.py`). Each runs as its own Claude Code agent with its own prompt (`roles/<role>.md`), permission settings and default model (`MODELS`). Three of them (boss, director, lead) are **HQ roles**: they coordinate and never write code.

**Management (HQ)**

| Role | Model | Responsibility | Never does |
|---|---|---|---|
| **boss** | Opus 5.5 | The **owner's single point of contact**. Turns your requests into goals, avoids duplicates (updates an existing goal instead), hands goals to the director, keeps you informed | Manage teams, write code |
| **director** | Opus 5.5 | **Runs the whole factory**: on-time delivery of every goal, staffing (teams, leads), resources, reporting, quality bar. Works in cycles on timers and messages | Write code, specs or reviews |
| **lead** | Opus 5.5 | **Delivers one goal** (or a part of it). Runs a team of short-lived workers, one task per pane; creates the planning task, spawns the pm, checks the plan, starts up to 3 coders, routes results, starts the audit, reports to the director | Write code, merge |

**Planning and building**

| Role | Model | Responsibility | Never does |
|---|---|---|---|
| **pm** | Opus 5.5 | **Turns a goal into a plan**: specs, build tasks with acceptance criteria and dependencies. At goal end, **audits** each success criterion against evidence and files follow-up tasks for gaps | Change code, touch git |
| **coder** | Sonnet 5.5 | **Implements one task** in its own worktree (branch `factory/{task}`) and opens a PR. On a retry, fixes every finding from earlier verdicts | Merge, review its own work, push to main |
| **staff-engineer** | Opus 5.5 | **On-demand technical advisor** across teams: answers technical questions, unblocks leads, reviews plans and architecture, helps the director decide | Decide, write code |
| **researcher** | Opus 5.5 | Answers **one research question** with an evidence-backed report from public sources and measurements, written into the factory database. A *different* researcher reviews the evidence | Decide anything; it treats web content as data, not instructions |

**Checking and merging (the merge gate)**

| Role | Model | Responsibility | Never does |
|---|---|---|---|
| **reviewer** | Opus 5.5 | **Code review** of the PR: correctness, security, maintainability, fit with the spec; records a verdict | Modify code, commit, push |
| **qa** | Sonnet 5.5 | **Verifies with evidence** that the PR does what its acceptance criteria say (runs it, tests it); records a verdict. Throwaway scripts go to a scratchpad | Modify product code |
| **judge** | Opus 5.5 | **The merge decision**: reads the reviewer's and QA's verdicts, the PR and CI, decides independently, and squash-merges or rejects with a cause | Modify code |

**Housekeeping and improvement**

| Role | Model | Responsibility | Never does |
|---|---|---|---|
| **cleaner** | Haiku 5.5 | **Reclaims disk space** without losing work: `factory clean` removes worktrees and branches of finished tasks, with safety checks (task done, PR merged or closed, worktree clean, nothing unpushed) | Delete anything unfinished |
| **scout** | Sonnet 5.5 | **Read-only triage** of third-party Claude Code skills, plugins, agents and hooks the factory fetched; text-only ones may be adopted, anything with scripts or hooks needs your decision | Change files, git, browse the web |
| **retro** | Sonnet 5.5 | **Daily rejection report**: reads the day's rejections and gate refusals and files one small advisory report | Change the repo, gates or roles |
| **evaluator** | Sonnet 5.5 | **Test subject in skill evaluations**: runs the same task in a throwaway sandbox with and without a skill, so the skill's effect can be measured | Anything outside the sandbox |

**How they connect for a normal goal** like G-001:
1. You → **boss** (goal) → **director** (team) → **lead** → **pm** (plan and tasks).
2. Each task: **coder** (PR) → **reviewer** + **qa** (verdicts) → **judge** (merge) → **cleaner** (clean-up).
3. At the end: **pm** (audit) → **director** (sign-off) → goal closed.
4. **staff-engineer** is called in when someone is stuck. **researcher**, **scout**, **retro** and **evaluator** work outside normal build goals.

The models are the defaults from `MODELS`; the factory can pick another model per spawn.
