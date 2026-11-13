# Flow page: why T-0003 showed "Planned 2h 07m"

Checked 2026-11-13 on the snapshot home /tmp/flowprev (port 18626) and the live DB.

## Real timeline (events table)
- 23:35:24 goal G-001 created; 23:40:00 pm adds T-0003 (depends_on T-0002; spec: start only after T-0002 merged).
- 00:16 lead files spec v2 after staff-engineer review (M62).
- T-0002 meanwhile: 3 coder starts, specs v2-v6 (git identity unset -> blocked on owner 23:51-23:53, Go toolchain questions), PR #1 in_review 00:49, merged 00:59:29.
- 01:00:29 T-0003 task-auto-start; PR #3 at 01:12; in_review 01:31:37.
- 01:37 reviewer FAIL, 01:42 QA pass; 01:43:51 coder respawned for attempt 2.
So the planning work was ~36 min; ~45 min more was waiting for T-0002.

## Why the page says 2h07m
web/queries.py task_lifecycle: first_spawn = min(agents.started) for role coder. agents.name is the PRIMARY KEY, so the
respawn reuses the coder-t-0003 row and overwrites started. queued = created -> 01:43:45 (2h03m) + spec 3m41s = 2h07m.
Knock-on: coding span negative -> None; "Judge 22m" is from the QA pass (01:42) to now although the review failed.
Fix idea: first coder start from events (task-auto-start / agent spawn) instead of agents.started; judge only after a round where both pass.
