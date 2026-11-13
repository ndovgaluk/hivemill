# 36. Coder and reviewer lifetime, the cost of keeping context, extra attempts from the director

Answers given on 2026-11-13. Read from the merged code and prompts in `~/factory` (branch `main`) and from goal G-001's event log and session transcripts, read-only. Estimates are marked as estimates.

## Q: Do we release the coder when it finishes and passes the task to the reviewer? When a review is rejected, is a new coder with clean context created, or is the previous agent reused with its context?

Yes, the coder is released when it hands over to review, and a rejected factory task gets a new coder session with a clean context. It keeps the same agent name and the same worktree, so the code carries over but the conversation does not.

### After the coder finishes

- The coder runs `factory done` with a summary, which goes to its lead.
- The next tick (within a minute) closes its pane. On G-001 every coder was closed between 3 and 47 seconds after its `done`.
- The agent's record stays in the database as "exited", with its summary and session id. Nothing is deleted.

### After a rejection

- The lead runs `factory spawn coder --task T` with a retry brief. That command has no option to resume a session, so the factory starts a fresh one.
- On G-001 each retry of `coder-t-0003` and `coder-t-0004` started in a new pane, minutes after the previous one was closed.

### What the new coder gets

- The worktree and branch as the previous coder left them, including the open PR.
- The task record with earlier verdicts: step 1 of the coder's prompt is to read it and fix every finding listed.
- The lead's retry brief: "attempt N of 3", every open blocking finding with its source.

### What it loses

Everything the previous coder learned but did not write down: why it chose an approach, what it tried and dropped, what it read in the codebase. It rebuilds that from the code and the findings. On G-001 this is one likely reason retries were slow; not measured.

### Where a session is resumed

- `factory relaunch` restarts an agent with its old session. It is meant for the long-lived roles (boss, director, lead).
- An agent that was stopped, not finished, can be resumed.
- The setting `coder_ci_handoff` has a `resume` mode in which the tick restarts the same coder session when CI turns red. It is `off` on this factory.

Not checked: the session transcripts were not opened to confirm that the new sessions started empty.

## Q: What does it cost to keep the coder and reviewer active with context until the task is merged?

Almost nothing while they wait. The cost comes when they work again, because every request re-reads the whole kept context. On G-001's numbers that would add roughly 0.5 to 0.75 USD per retry round, about 35% to 70% on top of what the round cost with a fresh session. This is an estimate from measured token counts, not a measured run.

### While waiting

- Tokens: none. An idle agent sends no requests.
- Memory: about 290 to 340 MB per agent process (measured on the live boss and director). The box had 27 GB available.
- A slot: `max_live_agents` is 6. A waiting coder, reviewer and QA hold 3 slots per factory task, so two factory tasks in flight fill the factory.

### Measured on G-001 (factory tasks T-0003 and T-0004)

| | Fresh session starts at | Ends at |
|---|---|---|
| Coder (Sonnet 5.5) | about 45k tokens | 49k to 182k, typically 90k to 125k |
| Reviewer (Opus 5.5) | about 44k tokens | 60k to 122k |
| QA (Sonnet 5.5) | about 44k tokens | 62k to 90k |

A kept session starts the next round at the "ends at" size and pays for the difference on every request.

### Estimate for one retry round of T-0003

| | Fresh session (actual) | Kept context (estimate) | Extra |
|---|---|---|---|
| Coder, attempt 2 | 1.16 USD | about 1.71 to 2.03 USD | about 0.55 to 0.87 USD |
| Reviewer, round 2 | 1.84 USD | about 2.18 to 2.49 USD | about 0.34 to 0.65 USD |

Corrected the same day: the first version of this table used the 5-minute cache rate. The factory's agents write only to the 1-hour cache (measured, see the next question), so the 1-hour rate applies.

The extra has two parts: re-reading the larger context on each request of the round (the low end), and, when the wait was longer than an hour, rewriting the whole context into the prompt cache once (the high end). Reviews on G-001 took 10 to 70 minutes, so both cases occur.

How the coder figure was computed: attempt 1 ended at 125k tokens, a fresh session starts at 45k, so 80k extra tokens ride along on each of attempt 2's 69 requests (5.5M cache-read tokens, 0.55 USD), plus, after an expired cache, a write of 125k tokens against 45k (0.32 USD more at the 1-hour rate).

### What the estimate leaves out

- The saving: a coder with its context would not re-read the code or re-derive its reasoning, so it would likely need fewer requests. Not measured; it may outweigh the extra.
- Growth: the cost compounds each round. One coder reached 182k tokens in a single attempt. The context limit of the configured models was not looked up; a kept session is compacted once it fills, which loses detail anyway.
- Reviewer independence: a reviewer that keeps its context is anchored on its earlier verdict. Good for checking that its findings were fixed, worse for a fresh look.

Assumptions: prices from `web/prices.py` (dated 2026-10-25), 1-hour cache rate for cache writes. The role of each session was guessed from its first message; the models match the roles.

### Recommendation

Do not keep the processes alive. Close the pane as today and, on a rejection, resume the coder's saved session by its id: the same context with no memory or slot cost while waiting. The factory already resumes sessions elsewhere (`factory relaunch`, `coder_ci_handoff=resume`), so this is a change to how the lead respawns a coder, not a new mechanism. Keep fresh sessions for the reviewer.

## Q: For how long can an agent sit idle without its context being cleared?

Claude Code does not clear an agent's conversation because it is idle. The conversation is held by the running process and saved in a transcript file on disk, and it is sent again in full with every request. What does expire with time is the prompt cache on the API side, and that only changes the price of the next request.

- **Prompt cache: one hour for the factory's agents.** Measured: every cache write in the factory's session transcripts is of the 1-hour kind (6.4M tokens), none of the 5-minute kind. Each request renews the hour. After an hour of silence nothing is lost; the next request sends the whole context again and pays the cache-write price for it once (for a 125k-token coder on Sonnet 5.5 about 0.50 USD, for an 88k-token reviewer on Opus 5.5 about 0.70 USD, at the `web/prices.py` rates).
- **The 5-minute cache** is the API's default lifetime. Claude Code falls back to it in some situations (a session in usage overage is one); whether that ever applies to the factory's agents was not checked.
- **Size, not time, shrinks a context.** When the context window fills, Claude Code compacts the conversation into a summary. That is triggered by size only.
- **Transcripts on disk** are removed by Claude Code after a retention period (`cleanupPeriodDays`; the default is 30 days as far as I recall, not verified here; no override is set in the factory's settings). After that a session can no longer be resumed.

The factory adds two rules of its own:

- `recycle_context_tokens` = 250000: a director or lead whose context is above 250k tokens is relaunched fresh, without its old session, once it is idle with an empty inbox, at most once per 6 hours (`docs/context-policy.md`).
- `idle_coder_reap` = off, `idle_coder_reap_s` = 900: by its name, a switch that would stop a coder idle for 15 minutes. Its code was not read.

## Q: How many extra tries does the director allocate?

No fixed number. Nothing in the director's prompt or skills says how many extra attempts it may grant; it decides case by case and records a `decision` message. The code has no cap and no setting.

- The lead's side is written down: three attempts, then escalate to the director with the task history (file 35).
- On G-001, for T-0004 the director said "attempt 3 of 3 is the last" and asked to be told before a third attempt fails, "so I can decide on more attempts, not after" (message M118).
- For T-0003 it ruled that an attempt stopped because of its own design change does not use up the budget, and promised "one more attempt" if the next run failed, provided the failure was not in the shared helper (M133).

So the pattern was one conditional attempt per decision. The database shows T-0003 finished with 3 attempts and T-0004 with 2; that counter is lower than the lead's own "attempt N of 3" numbering for T-0004, and the reason was not investigated.

A firm ceiling would have to be added as a rule in the director's prompt or as a check in the code. That is TSR story HM-2 (cost-effectiveness limits on extra attempts), with grilling task HM-3.
