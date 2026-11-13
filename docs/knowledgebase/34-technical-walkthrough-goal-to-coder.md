# Technical walk-through: from talking to the boss to the first coder

## Q: So just to clarify, so each agent when it finishes execution, it triggers some action that runs the command line CLI, which in its turn decides what to do, whether to send a message to a particular session, like summary of execution or create a new session. Is this correct? I just need a detailed explanation of what happens on each stage. So, for instance, when I start interaction with the boss, I give him details of the goal. Then, what happens, not like on the flow level but on technical level, the database record got created. The polling starts and so on. Please explain in details the flow of interaction between agents and nature of their communication, what's the difference between message and what's their purpose in the code, and basically state management. And how technically the agent actually is knows about the CLI that it needs to be called.

(Reply of 2026-11-13, as written.)

Not quite: the CLI decides nothing. The agent decides, and it uses the CLI as its hands. An agent does not "finish and trigger an action"; during its turn it runs `factory …` shell commands itself, the same way it would run `git`. Each command does one fixed thing: write a row, check a rule, or open a pane.

Relevant insights: "Changing a goal's status stops nobody" (writing state makes nobody act; a message plus a nudge does).

### The three parts

| Part | What it is | Does it decide? |
|---|---|---|
| Agent | Claude Code running in a herdr terminal pane, with a role prompt | Yes: it reads, thinks and chooses which commands to run |
| `factory` CLI | One Python program. Every agent, the tick and you run the same program | No: each subcommand checks who is calling, then reads or writes the database, and sometimes opens or closes a pane |
| Database | One SQLite file, `~/factory/db/factory.db` | No: it only stores |

The tick is not a fourth part: it is the same CLI (`factory tick`) started by a systemd timer about every minute.

### How an agent knows about the CLI

Nothing is wired in; it is told in text and given permission.

- **System prompt.** `factory spawn` writes the shared rules plus the role's rules (`roles\_common.md` + `roles\<role>.md`) to `run/<name>.prompt.md` and starts Claude Code with `--append-system-prompt-file` pointing at it. The shared rules open with: "Every goal, plan, task, message, verdict, report and decision is read and written through the `factory` CLI… That is the only source of truth", followed by the exact commands (`factory inbox`, `factory msg <to> …`). The role file lists that role's commands (for the lead: `factory spawn coder --task T`, and so on).
- **First prompt.** The kickoff typed into the pane is: "You are `coder-t-0002`, the factory coder. Run `factory whoami` and `factory inbox` first. Your task is T-0002: read it with `factory task show T-0002`…"
- **Identity.** The pane's environment carries `FACTORY_AGENT` (its name) and `FACTORY_ROLE`. The CLI reads them to know who is calling, and refuses commands that role may not run (a worker cannot run `goal status`, only the boss creates goals).
- **Reachability and permission.** `factory` is on the PATH (`~/.local/bin/factory`), and the role's settings file allows `Bash(factory:*)` while denying things like editing the database file directly.
- **Role skills** (`roles\plugins\<role>\`) hold longer procedures, such as the lead's fix-loop.

### What is stored where

| Table | Holds | Example of who writes it |
|---|---|---|
| `goals`, `plans`, `tasks`, `teams` | The work and its status | `factory goal new`, `factory task add`, `factory task update` |
| `agents` | One row per agent: name, role, pane, session id, status | `factory spawn`, `factory done`, the tick |
| `verdicts`, `audits`, `signoffs` | Review results and goal-end checks | `factory verdict`, `factory goal audit` |
| `messages` | sender, recipient, kind, subject, body, goal, task, created, `read_at` | `factory msg`, `factory done`, `factory spawn` (kickoff), the tick (alerts) |
| `events` | Append-only log: time, actor, entity, action, detail | Almost every command, as a side effect |

- **State** (the first three rows) answers "what is true now".
- **A message** is a row addressed to one recipient with an empty `read_at`. It answers "who has to react". In the code it is one `INSERT` (the `send` function); `factory inbox` prints the recipient's rows where `read_at` is empty and then fills `read_at`. Nothing else happens when a message is sent.
- **An event** is history for people and reports. Agents are not driven by it.

### What really happened for G-001, from your database

Times are from the `events` and `messages` tables of your factory (12 November, evening).

| Time | Who | Command run (what it wrote) |
|---|---|---|
| — | You | Type the goal into the boss pane. This is a prompt, so the boss starts a turn |
| 23:35:24 | boss | `factory goal new …` → a row in `goals` (G-001), event `goal new` |
| 23:35:31 | boss | `factory goal edit G-001 --success …` → updates the row |
| 23:35:31 | boss | `factory msg director "new goal G-001" …` → message M13 (`request`, unread). The boss's turn ends |
| 23:35:41 | director | Read M13. The tick had typed "📬 1 unread…" into its pane; it ran `factory inbox`, which printed M13 and set `read_at` |
| 23:35:47 | director | `factory team new …` → a row in `teams` (g-001-a); the goal becomes `active` |
| 23:35:51–53 | (same command) | `team new` spawns the lead: herdr pane `w3:p2`, Claude Code started, a row in `agents`, kickoff typed in and stored as M14 |
| 23:35:56 | lead | Its kickoff told it to run `factory inbox`: reads M14 |
| 23:35:58 | director | `factory msg lead-g-001-a "brief G-001"` → M15; then a report to the boss, M16 |
| 23:36:19 | lead | `factory task add … --role pm "Plan G-001"` → a row in `tasks` (T-0001) |
| 23:36:24–30 | lead | `factory spawn pm --task T-0001` → T-0001 becomes `in_progress`, pane `w3:p3`, agent row `pm-t-0001`, kickoff M17 |
| 23:38:55–23:42:27 | pm | `factory plan G-001 …`, then `factory task add` four times (T-0002…T-0005) and updates → rows in `plans` and `tasks` |
| 23:42:37 | pm | `factory done` → T-0001 `done`, its agent row `done`, and a `report` message M20 to the lead. The pm stops |
| 23:43:15 | tick | Sees the `done` agent row and closes its pane (event `reaped`); sees the lead has unread mail and types the 📬 nudge |
| 23:43:18 | lead | `factory inbox`: reads M20 |
| 23:43:42 | lead | Adjusts the four tasks (`factory task update`) |
| 23:43:49–55 | lead | `factory spawn coder --task T-0002` → T-0002 `in_progress`, worktree, pane `w3:p4`, agent row, kickoff M21 |
| 23:44:01 | coder | Reads its kickoff with `factory inbox`, then starts on T-0002 |

About 8.5 minutes from the goal row to a coder working, nine messages (M13 to M21), and every step is a `factory` command that some agent chose to run, except the two tick actions.

### So, corrected, the loop is

1. **An agent, mid-turn, runs a CLI command** that changes state (`task add`, `verdict`, `done`).
2. **Some of those commands also insert a message** for a fixed recipient. `factory done` always reports to the worker's lead; `factory msg` goes to whoever the agent named.
3. **The agent's turn ends.** It is idle. Nothing else has happened.
4. **The tick** (timer, about every minute) finds recipients with unread rows and types a nudge into their panes. It also closes panes of `done` agents and starts queued spawns.
5. **The nudged agent starts a turn**, runs `factory inbox`, reads state with other commands, decides, and goes to step 1. One of the things it may decide is `factory spawn`, which is how a new session comes to exist.

The decisions are in steps 1 and 5 and are made by the language model following its role prompt. Steps 2 and 4 are fixed code.

**Not verified:** I saw no "nudge" entries in the event log, so the two tick nudges in the table are inferred from the timing (a message read within seconds of the tick's reap at 23:43:15) and from the nudge code, not from a recorded row. The boss's exact commands are inferred from the events it produced.

LSP: not used, the code read is Python (no language server installed for it); located with Grep.

Skipped: reading the message bodies and the tick's steps line by line; risk: the table shows what was written and when, while who was nudged when is inferred.

---

## Q: What's the purpose of "Run factory whoami and factory inbox first"

(Reply of 2026-11-13, as written.)

It is a start-up check in two steps: confirm who you are, then pick up anything already waiting for you. Both run before the agent touches its factory task.

Relevant insights: no relevant insights beyond the WSL quoting one (applied).

**`factory whoami`: confirm the identity is intact.**

- It prints one line from the agent's own database row: `coder-t-0002  role=coder  goal=G-001  team=g-001-a  task=T-0002  model=…`.
- The CLI decides what a caller may do from the pane's environment (`FACTORY_AGENT`). If that is missing or wrong, every later command would run as the wrong identity or be refused. In that case `whoami` prints `unknown (agent pane, identity lost — no privileges; export FACTORY_AGENT=<your agent name>)`, so the agent finds out at once instead of failing halfway through.
- It also gives the agent its facts from the database instead of from the prompt text: which goal, team and factory task it belongs to. From your own terminal the same command prints `owner (owner — not a factory agent)`.

**`factory inbox`: pick up what is already waiting.**

- The kickoff itself is stored as a message (for example M21, "kickoff: coder T-0002"). Reading the inbox marks it read, which is why your trace shows each kickoff read a few seconds after the spawn.
- More important, other messages may already be there. In your G-001 trace the director sent the lead its brief (M15) seven seconds after the lead was spawned. A worker can likewise find a decision or a STOP addressed to it.
- It sets the habit the whole factory depends on: orders arrive through the inbox, so look there before acting. `factory done` is even refused while unread orders are waiting ("unread orders: read and act on them, then run factory done again").

**Why it is in the kickoff and not left to the role prompt:** the kickoff is the one piece of text every new agent is certain to act on first, so the two checks are put where they cannot be skipped. That reason is my reading; the code only shows the sentence being built into every kickoff (`kickoff_text` in `bin\factory_cli.py`).

Checked this turn: the `whoami` code, its output from your terminal, and the stored kickoff messages M17 and M21.

LSP: not used, the code read is Python (no language server installed for it); located with Grep.

Skipped: nothing else was needed; risk: none.
