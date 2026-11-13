# Who creates what: boss, director, lead, pm

## Q: Who actually creates the tasks, the boss or the director?

Neither. The **pm** writes the build tasks, and the **lead** sets the pm up and checks its work. Boss and director stay above the goal level.

**Who does what** (from `roles/lead.md` and `roles/pm.md`):

| Role | What it creates | For G-001 |
|---|---|---|
| **Boss** | **Goals.** It turns your request into a goal with intent and success criteria. The only role that runs `factory goal new` | Done: G-001 |
| **Director** | **Teams.** It staffs a goal with a team and starts its lead. Writes no tasks | Done: team `g-001-a`, `lead-g-001-a` |
| **Lead** | **One planning task** ("Plan G-001", role pm). Then it spawns a pm on it, reviews the plan and pushes back on tasks that are too big (the aim is under half a day each), overlapping, without testable acceptance criteria, or blind to risk | |
| **PM** | **The plan and all build tasks.** `factory plan G-001 …`, then one `factory task add --role coder …` per task with a spec, dependencies (`--after T-x`) and acceptance criteria | |
| **Coder, reviewer, QA, judge** | Nothing. They work on the tasks they're given | |

**Later in the goal:**
- **Fixes after a rejection:** the lead handles them through its fix loop.
- **Audit at the end:** the lead creates an "Audit G-001" task and spawns the pm again. If the pm finds gaps, it files **follow-up tasks** (`--follow-up-of T-x`).
- **Research goals** add researcher tasks, including a review by a *different* researcher.

In short: the boss decides **what**, the director decides **who**, and the pm works out **how**, as tasks, with the lead holding it to quality.

---

## Q: Who wrote this plan? (the lead's pane output)

The **pm** wrote it: the agent **`pm-t-0001`**, which worked on planning task T-0001. The lead set the pm up, reviewed the plan and added to it. The factory's event log confirms the authorship:

| Time | Actor | Action |
|---|---|---|
| 23:39:13 | **pm-t-0001** | created T-0002 (and T-0003–T-0005), then edited them twice |
| 23:42:37 | **pm-t-0001** | finished: *"G-001 plan v2 filed. Build tasks, sequential: T-0002 …"* |
| 23:43:42 | lead-g-001-a | updated T-0002: added the standard worker rules (test-count rule and allowed commands) word for word to the coder specs |
| 23:43:49–55 | lead-g-001-a | started `coder-t-0002` on T-0002 (Sonnet 5.5) |

**Where the plan's shape came from:**
- The **lead** wrote planning task T-0001. Its spec asked the pm to cover all 6 success criteria and to decide the `task_clones=1` interaction and the Go-port question.
- The **director's** brief (message M15) suggested the same 4-part split (config + DB claim, spawn reuse, clean pool, CLI tests). The lead noted that this already matched T-0001.
- The **pm** made the actual plan, the build tasks with acceptance criteria, and the design decisions: clones win over reuse, a worktree goes back to the pool only on `factory clean`, and the Go CLI only gets the config keys.
- The **boss** wrote the goal and its success criteria; the **director** staffed the team.

**A change afterwards:** at 23:45:35 the lead asked `coder-t-0002` to **stop**, reason *"spec v2: M23 adds PR-body …"*. That's the `[decision]` message and the `spec-change` skill: a decision came in and the spec of T-0002 changed, so the coder is restarted on the new spec rather than continuing on the old one. Normal flow, not an error.

How to inspect this yourself: `factory goal show G`, `factory task list --goal G`, `factory task show T`, `factory agents`, or the `events` table in `~/factory/db/factory.db` (columns `id, ts, actor, entity, entity_id, action, detail`).

---

## Q: Does the lead do any PM work, or does it assign tasks to the PM?

No. The lead **delegates** the pm work: it creates a planning task, assigns it to a **pm** it spawns, and supervises. Its role file (`~/factory/roles/lead.md`) says: *"You orchestrate, route results and report; never write code or merge."*

**Planning:**
- The lead creates the task *"Plan G-xxx"* (role pm) and spawns a pm on it.
- **The pm writes** the plan and all build tasks with their acceptance criteria.
- **The lead pushes back** on tasks that are too big (the aim is under half a day each), overlap, lack testable acceptance criteria, or ignore risk.

**Audit at the end:** the lead creates the audit task and spawns the pm again. The pm does the audit; the lead doesn't close the goal itself.

**What the lead does change in tasks itself:** only orchestration edits, never the plan's content.

| Lead's own task edits | Why |
|---|---|
| **Completing specs before a spawn** (worker-brief skill) | Workers don't share the lead's context, so every spec must stand alone. In G-001 this is when it added the standard worker rules (test-count rule, allowed commands) to the coder specs |
| **Spec changes on a running task** (spec-change skill) | Always `factory stop` → `factory task update` → respawn, never by message. That's the coder restart you saw (decision M23) |
| **Status and `[SCn]` tags** | Keeping the task list honest ("drift alerts are yours") |
| **Retries** (fix-loop skill) | After a failed review or QA, it spawns a fresh coder with the findings; after 3 attempts without a merge, it escalates to the director |

**What the lead does all day:**
- runs the build loop: coder → reviewer + QA → judge, at most 3 workers at once for its team;
- checks other goals' PRs for the same files before spawning;
- reports to the director (plan ready, each merge, anything blocked) with honest ETAs and risks.

In short: **pm = content** (what each task says and whether the goal is really met); **lead = flow** (who works on what, when, and making sure the specs are complete).
