# The TSR skill's `goal` parameter, and reading errors in agent panes

## Q: Update the TSR skill: add a lazily loaded reference to create a request for the HM boss. Parameter "goal", e.g. `/working-with-taskosaur goal Do that…`; the agent prints the goal as text best understood by the factory's boss.

Done. `working-with-taskosaur` has a new **read-only** parameter `goal`, like `viewplan`.

**Usage:**
```
/working-with-taskosaur goal DVDG-540
/working-with-taskosaur goal DVDG-540 DVDG-544
/working-with-taskosaur goal add a model_coder config override so coders can run on another model
```

**What the agent does** (new file `references/hivemill-goal.md`, loaded only when `goal` is used):
1. Reads the named TSR tasks (description, comments, a story's children, attachments when unclear); free text is used as is.
2. Picks the HM project (one goal per repo; `hivemill` = `~/factory`; a repo not yet registered → it gives you the `factory project add` command).
3. Decides how many goals (one outcome per goal; a TSR story with children is usually one goal, since the factory's pm re-plans).
4. Prints **one copy-paste block** for the boss pane:
   - `New goal for project {id}; TSR {KEY}: {title}`
   - **Intent** (what and why), **Success criteria** (3–8 checkable outcomes, from the TSR acceptance criteria), **Constraints**, **Out of scope**, **Priority**, **Depends on**;
   - with TSR keys: where to read them (tsr tools) and the **TSR sync paragraph** (In Progress on start, merge comments + commit links, In Review on close, a TSR message to you). Once HM's built-in sync (DVDG-545) is live, that paragraph becomes "Create the goal with --tsr {KEY}".
5. Below the block, 2–4 lines: what to check before pasting (e.g. `/mcp` in the boss pane shows `tsr`), and open questions it couldn't settle.

It changes nothing: no status moves, comments, time entries or code. Wired into `SKILL.md`: argument hint, description, parameters table, reference triggers, typical chains, section index. Ubuntu sees it at once through the skill symlink.

---

## Q: (coder-t-0003 pane: "worker-guard: blocked … factory res against the live home", "4 actions not run · permission denied", "API Error: Connection lost mid-response")

Normal; nothing to do.
- **Guard blocks** ("permission denied", "workers may not run broad factory reads (`factory res`) against the live home; use `factory task show` …"): the worker guard stopping a coder from reading factory-wide state. By design workers may only read their own task/goal; for experiments they use a temp FACTORY_HOME. The agent adapts (it moved to scratch copies).
- **"API Error: Connection lost mid-response"**: a transient network/API drop between Claude Code and the Claude API. The partial answer may be cut, but the session keeps going — the pane shows it continued ("Made 2 scratchpad edits, ran 3 shell commands"). If an agent ever stays stuck, the tick's stuck-agent handling relaunches it, and the lead sees it in its loop.
- Progress: coder-t-0003 (T-0003, spawn reuses a pooled worktree) is running, which means T-0002 went through; it found a fixture bug (`.gitignore` existed only on the old branch, so `node_modules` was untracked and got cleaned) and fixed its test setup — exactly the isolation case G-001 is about.

---

## Q: (coder-t-0003 pane: self-review subagent, `factory prcheck`, "merged count 7276 >= 7259", PR #3)

Healthy progress on T-0003:
- **Self-review**: the coder loaded its `self-review` skill and started a background subagent to review its own diff before handing over (a coder-side quality step; the real review comes later from the separate reviewer agent).
- **Test-count rule** (the coder rule C5 / QA rule Q1): it merges its branch with current `origin/main` in memory (`git merge-tree --write-tree origin/main HEAD`) and counts `def test_`: **7276 on the merged tree ≥ 7259 on main**, so the PR adds 17 tests and removes none. The "exit code 1: No matches found" is the last grep finding no *removed* tests, which is the good outcome.
- **`factory prcheck --pr …/pull/3`**: the factory's own pre-handover check of the PR (mergeable state, checks, rules); the only earlier FAIL was "no PR yet", fixed now that PR #3 exists. It runs 1–2 minutes.
- Next: when the self-review reports, the coder runs `factory done`; the lead then spawns reviewer and QA on PR #3.

---

## Q: Implement the charting diagram first, to understand the process and how much time each step takes; the worktree-reuse goal takes too long.

Built DVDG-544 directly (not through the factory): branch `dvdg-544-task-flow`, commit `9843bd9`, **PR #4** on the fork.
- `/task/{id}` now opens with a **Flow** diagram: Planned → Coding → Review / QA → Judge → Merged; each stage done / current / pending / skipped with **the time spent in it** (an open stage counts until now); a dashed loop back to Coding with "rejected N× · M attempts"; the current stage **pulses** and its arrow moves while an agent of the task is live; hover or keyboard focus shows a tooltip with the stage's notes; a table under it repeats everything (touch has no hover).
- Notes are facts only (status changes, agent starts/ends, verdict kind + commit, rejection causes, message subjects), not verdict summaries or message bodies: the dashboard has no login and its privacy rule forbids them. Showing them would be your decision.
- Tests: 150 (6 new) + 426 more pass; `affected.py --quick` 209 OK (budget ran out on the busy box, rest to CI).
- **Preview on live data:** a second server from the branch on **http://127.0.0.1:18625/** (read-only). Stop it with `pkill -f "port 18625"`.
- **What it showed:** T-0002 finished (Planned 1h 19m, Review/QA 7m 14s, Judge 50s, rejected once, 2 attempts); T-0003 and T-0004 **waited 1h 24m in Planned** (queued behind T-0002) and were coding ~28 min — that's where G-001's time went.
- To ship: CI green on PR #4 → merge → the tick fast-forwards `~/factory` → `systemctl --user restart factory-serve` for the normal dashboard (8765).

---

## Q: On each step of the diagram we should see the instructions given from one agent to another (Boss → Director → Lead …), rendered as Markdown like in Taskosaur.

Done on the same PR #4 (commit `65f2fa2`):
- New first stage **Goal (HQ)** with the chain that led to the task: goal-level messages up to the task's creation (boss → director "new goal", factory kickoff → lead, director → lead "brief", reports back) and the time from goal to task.
- Each message sits on the stage of the worker it instructs (e.g. the factory's kickoff to the coder → Coding), notes oldest first so the chain reads top to bottom.
- Every message, the task's spec + acceptance (the plan's instructions to the worker) and every verdict **opens to its full text rendered as Markdown** (headings, lists, quotes, code blocks, tables, links) by a new small safe renderer `web/html.md()` (all HTML escaped first).
- **Security switch:** the dashboard has no login and its rule was "never show message text". Text appears only with `factory config serve_show_text 1` **and** while the server listens on `127.0.0.1` (yours does); on a LAN address it stays hidden. Off by default.
- Tests: 155 + 534 pass (fixed along the way: the feature-flag registry entry and order, the test's flag list, a documentation IP instead of a private one).
- Look: **http://127.0.0.1:18626/task/T-0003** (snapshot of live data with text on; restart the script for a fresh snapshot), **http://127.0.0.1:18625/** (live, text off).
- After merge: `factory config serve_show_text 1`, then `systemctl --user restart factory-serve`.

---

## Q: Show the diagram for the goal as well (on /goal/G-001); clicking an arrow should highlight the instructions from one agent to another, clicking a block the agent's work; and pulse the current step.

Done on PR #4 (commit `317a56f`).
- **Goal page** `/goal/{id}`: one box per role that worked on the goal (Owner, Boss, Director, System = the factory's kickoffs, Lead, PM, Coders, Reviewer, QA, Judge) with agent count and time alive; one arc per pair of roles that messaged each other, labelled "N→ M←".
- **Click to highlight** (both pages, plain links + CSS `:target`, no JavaScript): an **arc** highlights the list of messages between the two roles; a **box** highlights that role's block (its agents, status, time, and with `serve_show_text` each agent's own summary of its work). On the task page: a **box** highlights the stage, the **arrow** into a stage highlights the **instructions that stage received**, the **rejection loop** highlights the review stage.
- **Pulse:** the current task stage always pulses; stronger, with a moving arrow, while an agent works on it. On the goal page, roles with a live agent pulse.
- What G-001 showed: Boss ⇄ Director 2/7 messages, Director ⇄ Lead 14/23, Lead ⇄ Coders 7/10, the factory's kickoffs System → Coders 11, Reviewer 4, QA 3; Lead (2h 35m) and Coders pulsing. Boss and Director show 0 agents because HQ agents aren't tied to one goal (their messages are).
- Tests: 158 + 534 pass. Previews: http://127.0.0.1:18626/goal/G-001 (fresh snapshot, text on), 18625 (live, text off).

---

## Q: (pasted analysis) Judge shown green though it never ran; Planned 2h 07m on T-0003 — bugs in the stage times?

Yes, two real bugs, fixed on PR #4 (commit `452197c`), each with a regression test that fails without the fix:
1. **Respawn overwrote the first start** (upstream `task_lifecycle`): a respawned coder reuses its agent row, so `agents.started` became the second start. T-0003's "Planned" swallowed its first 31 min of coding (2h 07m instead of ~1h 24m) and Coding showed no time. Now the first start is the earliest of the agent row and the task's `task-auto-start` event (written once).
2. **Judge opened at any pass**: a reviewer FAIL + QA PASS on the same commit made Judge green, with time counting from the QA pass. Now Judge counts only when the latest reviewer and QA verdicts both pass the same commit, or the judge itself acted (judge verdict / `judge-*` event).

Corrected live numbers: T-0002 Planned 7m 30s, **Coding 1h 05m** (was unknown), Review 7m 14s, Judge 50s; T-0003 **Planned 1h 24m** (was 2h 07m; mostly waiting for T-0002 to merge), **Coding 31m 08s** (was unknown), Review current, **Judge pending** (was green); T-0004 Planned 1h 24m, Coding 44m 21s, Review current.
Tests: 160 + 534 pass. The real slowdown behind G-001 stays the same: T-0002's churn (six spec versions, the missing git identity) while T-0003/T-0004 waited for it.

---

## Q: (same pasted analysis again) Planned 2h 07m / Judge green on T-0003

Both were already fixed (`452197c`). Re-checking the numbers found two more bugs, now fixed on PR #4 with regression tests:
3. **Goal and spec overlapped** (`69eedc8`): the Goal (HQ) box ran to the task's creation, and the spec part of Planned runs from the PM's start to the same point, so the PM's 3m 41s counted twice. Goal now ends where the PM starts: **55s** on all G-001 tasks (23:35:24 → 23:36:19).
4. **A stage left without a verdict kept counting** (`e61e4f9`): T-0003 went back to review at 02:23:33, got no verdict, and at 02:38:46 the lead sent it back to **todo** (it must wait for T-0004's shared helper). Review kept growing (1h 27m). Now an open stage stops at the first status change away from it: Review = **26m 07s** (10m 54s + 15m 13s).

Planned's 1h 24m = PM spec 3m 41s + waiting 1h 20m 29s (23:40:00 → 01:00:29), so it is right. Known limit: T-0003's second wait (since 02:38) isn't added to Planned yet.
