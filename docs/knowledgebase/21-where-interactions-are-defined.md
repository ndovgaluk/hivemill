# Where the interactions between agents are defined

## Q: Where is the process of interactions between agents defined?

In four layers, all in the repo (`~/factory`, or your dev copy `~/src/hivemill`). The **prompts and skills say what each agent should do**; the **CLI and the guard enforce what it can do**; the **docs explain it for humans**.

**1. Role prompts: who talks to whom, and when** (`roles/*.md`)

| File | Defines |
|---|---|
| `roles/_common.md` | Shared by every agent: the chain of command (workers → lead → director → boss → owner), "talk through the inbox" (`factory msg` / `factory inbox`, message kinds, terse style), who may call the staff-engineer, the rule that everything goes through the `factory` CLI |
| `roles/boss.md`, `director.md`, `lead.md` | The HQ flow: boss turns requests into goals and reports to you; director staffs and runs cycles; lead runs plan → build loop (coder → reviewer + QA → judge) → audit, with reporting duties |
| `roles/pm.md`, `coder.md`, `reviewer.md`, `qa.md`, `judge.md`, `cleaner.md`, … | Each worker's steps: what it reads, what it records (plan, PR, verdict, merge decision), whom it reports to, and what it must never do |

Each agent sees `_common.md` + its own role file (the repo keeps that pair under 12,000 bytes, `tests/test_repo_hygiene.py`). Changes reach only **newly spawned** agents.

**2. Role skills: the detailed procedures** (`roles/plugins/<role>/…/SKILL.md`, loaded per role)

| Role | Skills (procedures for specific interactions) |
|---|---|
| lead | `worker-brief` (what a spec must contain before a spawn), `spec-change` (stop → update → respawn), `fix-loop` (retries after FAIL/reject, escalate after 3), `audit-round`, `blocked-worker`, `pr-triage`, `park`, `research-flow` |
| director | `cycle-procedures`, `delivery`, `utilization`, `owner-decisions`, `close-goal`, `restriction-check` |
| pm | `plan-quality`, `acceptance-template`, `audit-checklist`, `audit-scope`, `research-plan`, `language-choice` |
| coder | `pre-pr-check`, `self-review`, `pr-description`, `ci-wait`, `stuck-and-finish`, `guard-change`, `go-change` |
| reviewer | `multi-angle-review`, `go-review` |
| researcher | `research-brief`, `source-evaluation`, `evidence-review`, `report-writing`, `benchmark-protocol`, … |
| staff-engineer | `systematic-debugging`, `codebase-design`, `differential-review`, … |

That's where you saw the lead load `factory-lead:worker-brief` and `spec-change`.

**3. The `factory` CLI: the rules that are enforced, not just asked for** (`bin/factory_cli.py`)
- **Messaging:** `cmd_msg` (line ~4086) refuses messages that break the rules, e.g. a worker messaging the staff-engineer (`ON_DEMAND_CALLERS = {lead, director, boss, owner}`, line 116: *"may not message …; ask your lead"*), or agents talking across orgs (only boss and director may, line ~4116).
- **The merge gate:** `cmd_verdict` (~4591) records reviewer/QA verdicts; `cmd_judge` (~5629) merges only when both pass and required checks are green.
- **Who starts whom:** `cmd_spawn` (~10649) decides which roles may spawn which workers, places them in herdr, gates on resources; `cmd_done` (~11213) is how a worker finishes (refused with uncommitted changes, as you saw with the coder).
- **The tick:** delivers the 📬 nudges, reaps finished agents, dequeues spawns.
- Goals only by the boss, sign-off only by director/owner, etc. are all checks in these commands.

**4. The guard and permissions: what an agent physically may run**
- `roles/hooks/worker-guard.py` (Go port in `go/`): blocks out-of-role Bash, e.g. the coder's push had to be exactly `git push origin HEAD:factory/t-0002`. Docs: `docs/worker-guard.md`.
- `roles/settings/<role>.json.in`: per-role allow/deny rules (the "Deny rule…" warnings come from these) and env (e.g. the dead herdr socket).

**5. Docs for humans** (`docs/`): `lifecycle.md` (goal/task lifecycle), `goal-lifecycle.md` (audit, sign-off, close), `verdict-gates.md` (merge gate), `planning-rules.md` (incl. guard-change rules), `spawn-queue.md` (resource gate), `worker-guard.md`, plus `docs/examples/` for real walkthroughs.

**Changing the process** means changing these files (prompt, skill, CLI check, guard rule) — through a goal and PR, never by editing `~/factory` directly. The citations in the prompts (`M255`, `M451`, `L-025`, …) are the message or lesson ids that caused each rule, so you can trace why a rule exists.
