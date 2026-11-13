# How an agent knows it has (new or changed) work

## Q: How does an agent know that it needs to pick up a new task, or do something with a task that has been changed?

Agents **never watch the task list**. Nothing polls tasks for changes. Work reaches an agent in exactly three ways: it is **started for a task**, it gets a **message** (and the tick types a nudge into its pane), or a **timer** prompts it. Who reacts depends on the role.

**1. Workers are started for one task, with the task in their first prompt**
- A worker (pm, coder, reviewer, qa, judge, cleaner) is never "assigned" a task while idle. The lead **spawns** it for a specific task: `factory spawn coder --task T-0002`. Its kick-off prompt says exactly what you saw: *"You are coder-t-0002 … Your task is T-0002: read it with `factory task show T-0002` … Your team is g-001-a."*
- When a worker really starts, the CLI moves the task to `in_progress` itself (`task_auto_start`, `bin/factory_cli.py:3199`; that was the `task-auto-start` event in the log).
- One worker = one task. When it finishes (`factory done`), the CLI **sends its summary to the lead as a `report` message** (`cmd_done`, line ~11213) and the next tick closes its pane. A new task means a **new** worker.

**2. Changed tasks: the lead restarts the worker, nobody "notices"**
- A worker doesn't watch its task for edits, so a spec change while it runs would be missed. The rule (lead skill `spec-change`, `roles/lead.md`): **`factory stop` the worker → `factory task update` the spec → respawn**, never "send the change by message".
- That's what you saw: decision M23 arrived, the lead stopped `coder-t-0002` (`stop-requested … spec v2: M23 …`) and started it again on the new spec; the coder's earlier edits stayed in its worktree.
- Rework after a failed review/QA works the same way: the lead spawns a **fresh coder for the same task** with the findings in its prompt (fix-loop skill); it continues on the same branch and PR.

**3. The lead finds new tasks when it's woken**
- The lead's loop (`roles/lead.md`) is: on each wake, check `factory task ready --goal G` (tasks whose dependencies are done) and spawn workers for them, at most 3 at a time.
- What wakes it: **messages** — a worker's `done` report, a decision from the director, a verdict, etc. The tick sees unread mail and types *"📬 1 unread factory message(s) [report]. Run factory inbox and act on them."* into its pane (that's how the lead knew T-0002's coder was blocked, M26).
- With `lead_parking=1` a lead with nothing to do can **park** (its pane closes to save resources); the tick then **restarts it** when mail arrives (`tick_wake_leads`, line 16441) with a *"WAKE (…): resume note … unread: N"* prompt, and messages it when a parked team's PR turns green or red in CI (`tick_ci_wake`). Your install has `lead_parking=0`, so leads stay up and just get nudged.

**4. HQ roles run on messages plus a timer**
- **Director:** besides messages, the tick sends a periodic *"⏱ Director cycle: run your cycle checklist (survey, resources, unblock, report)."* every `director_cycle_s` seconds (line ~15353). That's when it checks all goals, staffing and stuck work.
- **Boss:** woken by your typing in its pane and by messages (e.g. a goal finished, a decision needed).

**So, the chain for a typical change:**
1. The pm adds or edits tasks in the DB → nothing happens by itself.
2. A message (pm `done` report, director decision, …) lands in the lead's inbox → the tick nudges the lead.
3. The lead runs `factory inbox`, then `factory task ready`, then stops/respawns or spawns the right worker.
4. The worker reads its task fresh from the DB at start, does it, reports `done` → back to step 2.

**If you change something yourself** (e.g. edit a task or want a change of direction), tell the **boss** in its pane: it passes it down the chain as a message, which is what wakes the right agent. Editing a task in the DB alone won't make anyone act.

---

## Q: When Reviewer sends message to the coder to fix code after review, is the coder agent getting recreated from scratch in new session or the same agent that was making the fix with it's context is resued?

(Reply of 2026-11-13, as written.)

A new coder is created from scratch, in a new session with no memory of the first one. Also, the reviewer does not message the coder at all.

Relevant insights: no relevant insights beyond the WSL quoting one (applied).

**What actually happens after a failed review:**

1. **The reviewer records a verdict**, it does not write to the coder. It posts its review as a PR comment and runs `factory verdict <T> --fail` with every blocking finding in the summary (`roles\reviewer.md`).
2. **The first coder is already gone.** A worker finishes with `factory done` when it hands over its PR, and its pane is closed. There is nobody left to send a message to.
3. **The lead reads the verdicts and writes a retry brief** (lead skill `fix-loop`): "attempt N of 3", every open blocking finding with its source (reviewer, QA or judge), and that this coder owns the factory task now.
4. **The lead spawns a coder again:** `factory spawn coder --task T --prompt -`. A normal spawn starts Claude with a newly generated session id (`bin\factory_cli.py:10425`), not a resume of the old one.

**What the new coder has to work from**, since it has no conversation history:

- the factory task with its spec, acceptance criteria and all earlier verdicts (`factory task show T`; the coder prompt says "on a retry, fix every finding listed");
- the lead's retry brief in its first prompt;
- the same branch, the same worktree and the same PR, with everything the first coder committed and pushed. It pushes to the existing PR.

**What is the same and what is not:**

| | Retry coder |
|---|---|
| Agent name | Same (`coder-t-0003`): the name comes from the factory task |
| Session and context | New; nothing carried over |
| Branch, worktree, PR | Same |
| Model | The role default, unless the lead picks another for that spawn |

**Limits around it:**

- At most 3 attempts per factory task. After the second failure the lead asks the staff-engineer why the attempts are not converging, and a third failure goes to the director.
- If the findings are only nits, no coder is respawned: the lead respawns the reviewer or QA to re-verdict.
- Reviewer and QA are respawned fresh in the same way for the re-check.

**Seen on your factory:** `factory task show T-0003` printed `attempts: 3` earlier, and `factory agents` showed `coder-t-0003` started at 04:32:33, long after the first coder for that factory task. That matches a fresh spawn under the same name. I could not read its session ids from the database to compare them (`sqlite3` is not installed in WSL).

**Why it is built this way** is not stated in what I read; my reading is that a fresh coder with the written findings is cheaper and less anchored on its earlier mistakes than a long resumed conversation, and that it lets any worker be lost and replaced. The cost is the one you asked about: reasoning that was not written into the code, the PR or the factory task is lost between attempts.

LSP: not used, the code read is Python (no language server installed for it); located with Grep.

Skipped: comparing the two session ids in the database, and reading the code that builds the coder's first prompt; risk: none for the answer, the spawn code and the lead's skill agree.

---

## Q: I still don't understand what actually makes the agent to get wake up and start working, whether it's a timer or some kind of event. What actually triggers the agent to start.

(Reply of 2026-11-13, as written.)

An agent starts working when text is typed into its terminal pane and Enter is pressed. That is the only trigger. What differs is who does the typing, and the main typist is a timer.

Relevant insights: no relevant insights beyond the WSL quoting one (applied).

**What an agent is, mechanically:** a Claude Code program sitting in a terminal pane, exactly like the one you type into. It does nothing until a prompt is submitted. When it finishes answering, it sits idle again. It cannot be "called"; it can only be typed at.

**Who types into the pane:**

| Typist | When | What it types |
|---|---|---|
| `factory spawn` | Once, when the agent is created | The kickoff prompt: "You are coder-t-0003… Your task is T-0003…" |
| The tick | Every minute, if it finds a reason in the database | A nudge: "📬 1 unread factory message(s)… Run factory inbox", or "⏱ Director cycle: run your cycle checklist", or "WAKE (…)" for a parked lead |
| You | Whenever you type | Anything (normally only in the boss pane) |
| `factory stop` | When someone stops a worker | Presses Esc, then a nudge to read the STOP message |

The factory does the typing through herdr, the terminal manager that owns the panes (`herdr agent send-keys <name> Enter` and similar calls in `bin\factory_cli.py`).

**So is it a timer or an event? A timer that checks for conditions.**

- The timer is systemd's `factory-tick.timer`: it runs `factory tick` 90 seconds after boot and then 60 seconds after each run finishes.
- Each run, the tick looks in the database for reasons to nudge someone: unread messages, the director's cycle being due, a parked lead with mail.
- If it finds one, it types the nudge. If not, it types nothing and the agent stays idle.
- There is no event system. Sending a message with `factory msg` only writes a row; nothing pushes it to the receiver. The receiver finds out at the next tick, so the wait is up to about a minute.

**One chain, end to end** (a coder finishing its work):

1. The coder runs `factory done`. That writes a `report` message for the lead into the database. Nothing else happens yet.
2. Within a minute the tick runs, sees the lead has 1 unread message, and types the 📬 line into the lead's pane.
3. The lead's Claude Code receives that as a prompt, so it starts a turn: it runs `factory inbox`, reads the report and decides to spawn a reviewer.
4. `factory spawn reviewer --task T` opens a new pane, starts Claude Code there and types the kickoff prompt. The reviewer starts working.
5. The lead's turn ends. It is idle until the next nudge.

**Two things that can look like self-waking but are not:**

- **A long turn.** A coder waiting for CI is not asleep: it is still inside one turn, running `gh pr checks` in a loop. Nobody wakes it; it has not stopped.
- **The boss.** The tick is deliberately careful with the boss pane because you type there, so most mail does not nudge it. It reads its inbox when you send it something (a hook runs `factory inbox` on each of your messages).

Checked this turn: the timer file and the lines in the CLI that send keys and build the nudge texts. Not checked: the exact herdr call that types the nudge text itself (I saw the Enter and Esc key sends, not the text send).

LSP: not used, the code read is Python (no language server installed for it); located with Grep.

Skipped: reading the tick's nudge step line by line; risk: none for the picture above, the timer file and nudge texts are quoted from the repo.

---

## Q: Yes, all right, but who actually creates the new session and new agent in Hereditor? (herdr)

(Reply of 2026-11-13, as written.)

The `factory` command-line program creates it: its `spawn` code asks herdr for a pane, starts Claude Code in that pane with a new session id, and types the first prompt. herdr never decides to create an agent by itself, and neither does Claude.

Relevant insights: no relevant insights beyond the WSL quoting one (not needed this turn).

**Who runs that command** depends on the agent being created:

| New agent | Who runs the command | Command |
|---|---|---|
| Worker (pm, coder, reviewer, qa, judge) | The goal's lead, from inside its own pane | `factory spawn coder --task T-0003` |
| Lead | The director, when it staffs a goal | `factory team new …` (which spawns the lead itself) |
| Boss, director, and leads after a reboot | systemd at boot, or you | `factory up` |
| Any of them, when the machine was too busy at the time | The tick, a minute or more later | The spawn was queued; the tick starts it when the resource gate opens |

So the chain of "who" is: you type to the boss → the director staffs a team → the lead spawns workers. Each of those is an AI agent running an ordinary shell command; the command does the actual creating.

**What the spawn code does, in order** (`bin\factory_cli.py`, the `spawn` function and the start step after it):

1. **Checks:** the role is allowed to spawn, the factory task has a spec, no agent with that name is already live, and the resource gate (RAM, load, number of Claude processes) is open. If the gate is closed, it writes a `queued` row and stops here.
2. **Prepares the workplace:** for a coder, a git worktree and branch for the factory task.
3. **Gets a pane from herdr:** it creates a workspace or tab for the goal if needed (`herdr workspace create`, `herdr tab create`) or splits an existing pane (`herdr pane split`).
4. **Writes the agent's files:** the role prompt to `run/<name>.prompt.md` and the role's permission settings.
5. **Starts Claude Code in the pane** with the role's model, settings, prompt file and plugins, and a freshly generated session id (`--session-id <new uuid>`). A resumed boss, director or lead gets `--resume <old id>` instead.
6. **Records the agent** in the database (name, role, pane, session id, status live) and labels the pane in herdr.
7. **Types the kickoff prompt** into the pane (`herdr agent prompt <name> …`) and also stores it as a message. From here the agent is working.

**Division of labour:**

- **herdr** only provides terminal panes and a way to type into them and list them.
- **Claude Code** is the program running inside the pane; the session belongs to it.
- **The factory CLI** is the one that creates, names, records and later closes them.

**A note on my earlier line reference:** in the previous answer I cited `factory_cli.py:10425` for the new session id. The file in the WSL clone has changed since (that line now holds something else, about 20 lines moved), so use the function name, not the line number.

Read this turn: the herdr calls in the CLI and the part of the spawn start step that builds the Claude command line. Steps 1 and 2 are from earlier reading and the docs, not re-read now.

LSP: not used, the code read is Python (no language server installed for it); located with Grep.

Skipped: reading the whole spawn function top to bottom; risk: the order of steps 4 to 6 is approximate.

---

## Q: Alright, but what triggers the CLI tool to create a new agent?

(Reply of 2026-11-13, as written.)

On your install, an AI agent decides to run it. There is no rule engine behind most spawns: the lead (an AI) reads its instructions and the current state during a turn, concludes "this factory task is ready, it needs a coder", and runs `factory spawn coder --task T` as a shell command.

Relevant insights: no relevant insights beyond the WSL quoting one (applied).

**The full chain for one worker:**

1. Something types into the lead's pane (the tick's 📬 nudge after a worker's report, for example). That starts a turn.
2. The lead follows its role prompt (`roles\lead.md`, "Build loop"), which is plain text telling it what to do:
   - for each factory task in `factory task ready --goal G`: spawn a coder;
   - when the coder reports done: spawn a reviewer and a QA;
   - both pass: spawn a judge;
   - any fail: spawn a fresh coder with the findings;
   - at most 3 live workers for the team.
3. The lead runs the commands that the situation calls for. Each `factory spawn …` is the trigger for one new agent.

So the "trigger" is a decision made by a language model that was told the procedure in words. That is why it adapts (it can hold a spawn back, ask the staff-engineer first, or write a custom brief), and also why it can be slow or get it wrong.

**The same pattern one level up:**

| New agent | Decided by | Following |
|---|---|---|
| Worker | The lead | `roles\lead.md` build loop and its skills (fix-loop, audit-round, …) |
| Lead | The director, after the boss's "new goal" message | Its staffing instructions; `factory team new` |
| Staff-engineer | A lead, the director or the boss messaging it | It is spawned on demand when a message is sent to it |

**Spawns that are mechanical, with no AI decision:**

| Trigger | What starts | On your install |
|---|---|---|
| Boot (`factory-up.service` runs `factory up`) | Boss, director, active leads | On (units enabled) |
| The tick draining the spawn queue | A spawn that an agent asked for earlier while the resource gate was closed | On (always) |
| The tick, `review_autospawn=on` | Reviewer and QA as soon as a coder's PR opens, without waiting for the lead | Off (`review_autospawn = off`) |
| The tick, `lead_less_dispatch=1` | Workers for ready factory tasks when the lead is parked | Off (`lead_less_dispatch = 0`) |

The first two only carry out or repeat a decision that was already made. The last two would make the tick itself the decider for some spawns, but both are off here, so today every new worker on your factory starts because the lead chose to run the command.

**Putting the three answers together:**

- **What creates an agent:** the `factory spawn` code.
- **What triggers that code:** an agent (usually the lead) running the command during its turn.
- **What triggers that agent's turn:** text typed into its pane, usually the tick's nudge about a new message.
- **What triggers the message:** another agent finishing something (`factory done`, a verdict, a decision).

So the factory moves in a loop: finished work writes a message, the timer delivers a nudge, the nudged agent decides and spawns the next worker.

Checked this turn: `roles\lead.md`, the docs for the two automatic modes and the spawn queue, and the live config values with `factory config`.

LSP: not used, no code was read this turn (role prompt, docs and config only).

Skipped: how the director decides on staffing (its prompt and skills were not read this turn); risk: the "Lead" row is from earlier notes, not re-checked.
