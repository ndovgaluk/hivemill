# How agents communicate

## Q: How do they communicate between each other?

Agents never talk to each other directly. Everything goes through the factory's **SQLite database**, using the `factory` CLI. The tick then "rings the bell" in the right terminal pane.

**1. Messages: the inbox** (`roles/_common.md`, section 2)
- **Send:** `factory msg <to> "<subject>" "<body>" --kind … [--goal G] [--task T]`. Each message is a row in the database with an id like **M26**; those are the M-numbers you see in the panes.
- **`<to>`** can be an agent name (`coder-t-0002`), a role (`director`, `boss`), a team's lead (`lead:g-001-a`), or `owner`, which is delivered to the boss.
- **`--kind`** is one of `msg`, `request`, `report`, `escalation`, `decision` or `alert`. That's the tag in the panes: "1 unread factory message(s) **[decision]**".
- **Read:** `factory inbox`, with `--show M####` for a long message or `--peek` to read without marking it as read.

**2. Notification: the tick's nudge**
- Agents don't poll. Every minute the tick checks for unread mail and **types a prompt into the agent's herdr pane**: `📬 1 unread factory message(s) [decision]. Run factory inbox and act on them.`
- The agent wakes up, runs `factory inbox` and acts. Nudges to the same agent are at least 120 s apart (`nudge_cooldown_s`).

**3. Chain of command:** workers → their lead → director → boss → owner (you).
- Nobody skips a level, and only the boss messages you.
- Workers can't message the staff-engineer (`factory msg` refuses them); they ask their lead.

What happened with T-0002 followed exactly this path:
1. The coder reported its blockers to the lead as **M26**.
2. The lead escalated to the director.
3. The coder received **[decision]** messages (**M25**, then **M28**) telling it to stop and keep its edits.

**4. Shared state instead of messages:** most coordination is simply the database and GitHub, with no message at all:
- the pm writes the **plan and tasks** → the lead and coders read them (`factory task show`);
- the reviewer and QA record **verdicts** → the judge reads them;
- the coder opens a **PR** → reviewer, QA and judge read it with `gh pr view`/`gh pr diff`.
- Every action also lands in an append-only **event log** (the `events` table), which is how we found that `pm-t-0001` wrote the plan.

**Style rule:** messages between agents are terse (facts, IDs, commands, results, next step). Anything a human reads, like the boss's reports to you, specs and PR descriptions, is in full English.

**To read the conversations yourself:** the web UI (http://127.0.0.1:8765/) shows messages per goal; `factory inbox --peek` shows the owner's inbox without marking anything as read.


---

## Q: If the boss receive instruction from me to stop the processin of specific goal, how would other agents will know that they need to stop? What's the nature of communication betwwen boss and other agents?

(Reply of 2026-11-13, as written.)

Nothing stops by itself: the boss passes your instruction down as a message, and each level acts on it with its own commands. There is no "stop goal" command, and no role prompt describes stopping a goal.

Relevant insights before this answer: only the WSL quoting one (applied to how I ran the searches).

### How agents talk

- **One channel:** rows in the factory database, sent with `factory msg <to> "<subject>" "<body>" --kind … --goal G`. Agents have no direct calls and no shared chat.
- **Kinds:** `request`, `report`, `escalation`, `decision`, plus `alert` sent by the tick.
- **Delivery is a nudge, not an interrupt:** once a minute the tick sees unread mail and types "📬 N unread factory message(s)… Run factory inbox" into the receiver's pane. The agent reads it when it next takes input.
- **The boss's role:** its prompt has it hand goals, updates and your answers to the director, and says it does not manage teams. Your decisions go down as `--kind decision`, quoted verbatim, so they are recorded permanently.
- **Workers** (pm, coder, reviewer, qa, judge) don't watch the goal or their factory task for changes.

### What a stop looks like

The role prompts don't describe this procedure, so the chain below is what the commands and permissions allow, not something I watched happen.

1. You tell the boss "stop G-001".
2. The boss sends the director a `decision` message with your words and `--goal G-001`. It may also set the status itself: `factory goal status G-001 cancelled` (or `blocked`) is allowed for boss, director and lead.
3. The tick nudges the director, which reads its inbox and tells the goal's lead, or stops workers itself.
4. The lead (for its own team) or the director (for any worker) runs `factory stop <agent> --reason "…"` for each running worker. This is the only real stop:
   - It sends the worker a `STOP` decision message, presses Esc in its pane, waits up to 30 s and nudges it to read its inbox.
   - If the worker is still alive after `stop_timeout_s` (default 300 s), the tick closes the pane and marks the agent `stopped`. `--now` does that at once.
5. The director closes the team with `factory team close <team>`, which ends the lead.

### What does not stop anything

- **Changing the goal's status alone.** `goal_status` (`\\wsl$\Ubuntu\home\dell\src\hivemill\bin\factory_cli.py:2960`) writes the new status and an event. It sends no message and stops no agent.
- **A message alone to a busy worker.** It reads mail only when it next looks; `factory stop` is what interrupts it.
- **`factory stop` on a boss, director or lead.** It is refused; a lead ends when its team is closed.

### Not verified

- Whether `spawn` or the tick refuses new workers on a goal with status `cancelled` or `blocked`. My search of the CLI found no such check near spawn, but it was not exhaustive.
- What `factory stop` leaves behind beyond the agent row: the stop doc only says a `stopped` agent is protected from `factory clean`. I did not check what happens to its worktree, branch or open PR, so assume closing PRs and cancelling the factory tasks is a separate step.

### Practical advice

Tell the boss exactly what you mean: "Stop G-001 now: stop every running worker, start no new ones, leave the PRs open, mark the goal cancelled" (or "pause" with status `blocked` to resume later). Then check with `factory agents` and `factory goal show G-001`. As owner you can also run `factory stop <agent>` yourself.

Notes updated: the full answer is in `\\wsl$\Ubuntu\home\dell\src\hivemill\.local-docs\14-agent-communication.md`, and one new entry plus one open question are in `\\wsl$\Ubuntu\home\dell\src\hivemill\.local-docs\INSIGHTS.md` (checker passes: 2 entries).

LSP: not used, the code read is Python (no language server installed for it); located with Grep.

Skipped: tracing the spawn path for a goal-status check, and checking what a stop leaves behind; risk: a "cancelled" goal may still get new workers if the lead keeps spawning, so confirm with `factory agents` after a stop.

---

## Q: so there's a polling process that checks the database every minute? for inbox messages and basing on the message type it does tha ction?

(Reply of 2026-11-13, as written.)

Half right: there is a once-a-minute process, but it does not carry out what a message says.

Relevant insights: "Changing a goal's status stops nobody" (same theme: nothing acts on its own); the WSL quoting one (applied).

**The polling part: yes.** `factory tick` is started every minute by a systemd timer. It is a plain Python run, not an AI agent. Each run it reads the database and, among other things, looks for agents with unread messages.

**The "does the action" part: no.** For a message, the tick only delivers a nudge. It types a line such as "📬 1 unread factory message(s) [report]. Run factory inbox and act on them." into the receiver's pane. The receiving agent then runs `factory inbox`, reads the text and decides what to do under its role prompt. The tick never interprets a message's body.

**Where the message kind matters:**

- **Boss pane:** only `escalation` and `request` messages wake the boss, and only when all of these hold (`docs\boss-mail.md`):
  - one such message is at least 15 minutes old;
  - the pane is idle with nothing half-typed;
  - no wake was sent in the last 30 minutes.

  Reports, alerts and decisions never wake it. It sees them when you next type, because a hook runs `factory inbox` on each of your messages.
- **Director and leads:** they keep the `📬` nudges for unread mail; the nudge text lists the kinds.
- **A `STOP` decision:** special only because `factory stop` sets a flag on the agent row at the same time. The worker must read the message before `factory done` works.

**What the tick does act on by itself** is database state, not message content:

- closing the panes of finished agents;
- starting queued spawns when resources allow;
- the hard fallback for a stop that timed out;
- the director's periodic cycle prompt;
- waking parked leads;
- exporting state.

So a message waits up to about a minute for the nudge, plus however long the receiving agent takes to finish what it is doing and read its inbox.

This is from `CLAUDE.md`, the boss-mail and stopping docs and your earlier note on how agents get work; I did not re-read the tick's message step in the code this turn. The answer is appended to `\\wsl$\Ubuntu\home\dell\src\hivemill\.local-docs\14-agent-communication.md`.

LSP: not used, no code was read this turn (docs and notes only).

Skipped: re-reading the tick's message step in the code; risk: wake thresholds are the documented defaults (900 s / 1800 s), and your install's config may differ.

---

## Q: so what's the purpose of messages and inbox then? If the state of factory is stored elsewhere?

(Reply of 2026-11-13, as written.)

Messages are how one agent gets another to act, and how decisions and their reasons are put on record. The state tables say what is true; a message says "you, look at this now, and here is why".

Relevant insights: "Changing a goal's status stops nobody" is the same point from the other side: writing state does not make anyone act, a message does.

**What messages do that state cannot:**

- **They wake someone up.** No agent watches the factory task list. A change in the database is invisible until a message lands in someone's inbox and the tick nudges that pane. The inbox is each agent's to-do trigger.
- **They are addressed.** A factory task's status belongs to nobody in particular. A message goes to one agent or role (`director`, `lead:<team>`, `owner`), so it is clear who has to act.
- **They carry judgment, not just facts.** A worker's `report` says what it did and what it is unsure about. A `request` asks for something. An `escalation` says "I am stuck, here are the options". None of that fits a status field.
- **They record decisions.** Your answers go down as `decision` messages quoted verbatim, each with an id (`M23`). Specs, lessons and role rules then cite those ids ("spec v2: M23", "(M664)"), so anyone can see who decided what and when.
- **They let the tick talk.** The tick's alerts ("agent vanished", token limit warnings, CI turned red) are messages too: the mechanical part of the factory telling an agent that something needs a decision.

**How the two fit together:**

| | State (goals, factory tasks, verdicts, agents) | Messages |
|---|---|---|
| Answers | What is true now? | Who should do what next, and why? |
| Changed by | CLI commands with role checks | `factory msg`, `factory done`, the tick |
| Read when | An agent looks it up while working | An agent is nudged, or checks its inbox |
| If lost | The factory would not know where it is | Work would stall, because nobody is told to act |
| After a restart | Tells where to continue | Unread ones are still waiting; read ones stay as history |

**A worked example** from your G-001: the pm finished the plan (state: factory tasks created). Nothing happened until its `done` report reached the lead's inbox. The lead was nudged, read it, ran `factory task ready` (state) and spawned a coder. State told the lead what was ready; the message told it to look.

**"Read" and "unread"** is therefore a to-do marker, not storage. Unread means "someone still owes this a reaction". That is why losing the unread flag on a restart would matter little: the things that must not be lost are in the state tables, and anything half-handled shows up again as a `lost` agent or an open factory task.

This is my summary of how the pieces relate, built from the role prompts, the docs and the code read earlier today; the repo does not state it in these words.

LSP: not used, no code was read this turn.

Skipped: nothing was checked anew this turn; risk: none, this is an explanation of earlier findings.
