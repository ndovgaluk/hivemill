# HQ nudges and stale-mail alerts

How the tick makes sure mail reaches the boss and the director, and how unread mail that sits too long is surfaced
(goal G-003). The rules for *when* the boss pane is prompted are in [boss-mail.md](boss-mail.md).

## Why

On one night the boss pane got no new-mail prompt for almost 15 hours while workers and leads were prompted normally.
After a resumed relaunch the terminal host listed the boss pane by name, but with no agent status; the tick treated
that as "not idle", skipped the boss on every tick, and recorded nothing. An owner decision waited 7.5 hours.

## Finding the pane of an HQ agent

Tick step 3 handles the boss and the director apart from the other roles (`_hq_nudge_tick`, `_hq_nudge_host` in
`bin/factory_cli.py`). A prompt is *due* for the boss when unread mail qualifies under its wake rules and its cooldown
has passed, and for the director when it has unread mail (or its cycle is due) and `nudge_cooldown_s` has passed.

When a prompt is due, the host entry is looked up by agent name, else by pane id:

| Host entry | What the tick does |
|---|---|
| status `idle` or `done` | prompts the agent, as before |
| listed, but no status (`unknown`) | **fallback:** prompts only when the pane's foreground is just the agent, the last 60 lines hold no unsent input, and no dialog is open. Records `hq-nudge-fallback` once per episode. Otherwise it waits; no alert. |
| status `working` or `blocked` | busy: waits; no alert |
| no entry for the name or the pane | undeliverable: `no-host-entry` |
| the host list could not be read | undeliverable: `host-list-failed` |
| the prompt command failed | undeliverable: `prompt-failed`; `last_nudge` is not set, so the next tick tries again |

The boss is never prompted over unsent input or an open dialog, in any of these cases.

## An undeliverable prompt is reported

For each (agent, reason) the tick records one event `nudge-undeliverable` (detail: agent, role, pane, reason) and sends
one mail of kind `alert` from `tick`, subject `nudge undeliverable: <agent> (<reason>)`: to the director when the boss
cannot be reached, to the boss when the director cannot. The alert is not repeated while the same reason lasts. The next
prompt that gets through clears it, so a later failure alerts again.

Workers and leads are prompted as before; none of this applies to them.

## Unread mail older than an hour

After step 3 the tick runs `tick_stale_unread`. For every live agent (evaluators excluded) it looks for unread mail at
least `stale_unread_alert_s` seconds old (default `3600`; exactly that age counts).

- The first time an agent has such mail, one mail of kind `alert` from `tick` goes to the director, or to the boss when
  the agent is the director. Subject: `stale unread mail: <agent> (<n> msg, oldest <m> min)`; the body lists up to 20
  messages (id, kind, sender, age). One event `stale-unread-alert` is recorded (detail: agent, count, oldest, to).
- No second alert while the agent still has stale unread mail.
- When the agent has none left, the episode ends; new stale mail alerts again.

Change the threshold with `factory config stale_unread_alert_s 1800`. A failure inside the step is recorded as the event
`stale-unread-error` and never stops the tick.

## How to check

```
python3 -m unittest tests.test_boss_wake tests.test_boss_mail
sqlite3 /home/user/factory/db/factory.db "SELECT ts, entity_id, action, detail FROM events WHERE action IN ('hq-nudge-fallback','nudge-undeliverable','stale-unread-alert','stale-unread-error') ORDER BY id DESC LIMIT 20"
```

## Limits

- The alert for an undeliverable prompt is addressed to the role name (`director`, `boss`); on a box with two orgs it
  goes to the HQ agent the mail routing picks for the tick, which may not be the org of the agent that could not be reached.
- With the `hc` terminal backend a failed agent list is not told apart from a missing entry: it is reported as
  `no-host-entry`.
- A stale-mail alert is itself mail. If the director does not read it for an hour, the boss is told once.
