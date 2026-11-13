# 31. Why goal G-001 took hours, and what is wrong in the workflow

Read from the factory database (read-only) on 2026-11-13 at 03:56, about 4h 20m after the goal was created. Times are local.

## Q: Why does it take so long? It looked like a simple task, but it takes hours. Is there an issue with the workflow on the factory?

Yes, there are workflow problems, and the goal also turned out not to be simple. About half of the elapsed time went to rework that better sequencing would have avoided; the rest is real work on a harder problem than the title suggests.

### Why it was not simple

"Opt-in worktree reuse" changes the code that starts and cleans up every worker, and its success criteria ask for isolation between factory tasks and safety under concurrency. Review found a real security hole in that area: a worker can plant a `.git` file in its worktree that points at another task's git directory, so a reset or clean would damage a sibling's work. The same hole already existed in today's `factory clean`. At 01:55 the director decided to fix it inside this goal, so the scope grew from "reuse a folder" to "prove git can never be redirected". Four of the seven rejections are that one class of bug.

### Where the time went

| When | What happened | Cost |
|---|---|---|
| 23:43 to 00:27 | T-0002's coder was stopped and respawned six times because its spec was rewritten five times while it ran | About 44 min before the run that produced the PR, which then took 22 min |
| 23:48 to 23:54 | The box had no git identity and no Go toolchain; escalated to the owner; "Go via CI" was decided, then reversed to "Go local" four minutes later | Part of the 44 min above |
| 00:52 | T-0002 rejected by the reviewer for the PR description only (code and CI were fine) | One extra review round |
| until 01:00 | T-0003 and T-0004 waited for T-0002 to merge | 1h 20m queued, by plan |
| 01:45 | T-0004 got a new acceptance item after its PR was open, then failed review against it six minutes later | One full attempt |
| 02:27 | T-0004 attempt 2 failed QA for the PR description only (QA: "the code and tests are good") | One extra round |
| 02:36 | A new design from the staff engineer was adopted: the ownership check moves into T-0004 and T-0003 must use it. T-0003's coder, 53 minutes into attempt 2, was stopped and T-0003 now waits for T-0004 | Most of that attempt, plus a new dependency |
| 03:51 to 03:52 | T-0004 attempt 3: the reviewer passed it, then changed the verdict to fail 49 seconds later after a director ruling arrived mid-review | Recorded by the factory itself as "unclear spec" |

### The workflow problems

1. **Specs change while workers are running.** T-0002 had six spec versions, T-0004 five, T-0003 three; acceptance lists grew to 20 items. Each change stops a coder and restarts it. The director ruled "stop respawning for spec tweaks" at 00:04, and it still happened at 00:27 and 02:36.
2. **Acceptance items are added after the PR is open** and the work is then judged against them. That guarantees a rejection.
3. **The design for the hard part came last.** The staff engineer's design for the ownership check was adopted at 02:35, after two attempts on each of T-0003 and T-0004 had already been coded and rejected.
4. **PR-description format costs whole review rounds.** Two of seven rejections were for the description only, and the coder's own PR check failed on "body" in four of its six recorded runs.
5. **The box was not ready.** No git identity and no Go toolchain, found only once a coder was running.
6. **Rulings arrive in the middle of a review**, which produced a pass and a fail on the same commit within a minute.

One observation, not a proven cause: coders run on Sonnet 5.5 and reviewers on Opus 5.5, and the reviewer found a new variant of the same security bug in each of the first three rounds.

What does not look like a problem: capacity. The limit is 6 live agents and the count stayed between 4 and 6. Not checked: the per-team cap of 2 workers, and whether the spawn queue ever held anything back.

### Where it stands and what is likely next

- T-0004 has one blocking item left, and the director's note already names the fix (run the existing "not a git worktree" check before the ownership check). But the lead's note calls the current attempt "3 of 3", so it probably needs the director to grant another attempt. The director's decision was not read.
- T-0003 is deliberately parked behind T-0004. That is why it shows as "todo" with no coder.
- T-0005 and the new follow-up T-0006 come after both.

### What the owner can do

- **Now:** tell the boss to freeze T-0004's spec and acceptance until it merges, and to grant the extra attempt. The remaining fix is small.
- **For later goals:** these are corrections for the factory's own agents, so they belong as factory lessons (`factory lesson add`), not in these notes. The four worth recording: no spec or acceptance change while a worker runs or after its PR is open; design review before the first coder on anything touching spawn, clean or isolation; the coder fixes its PR check before asking for review; check git identity and required toolchains before a goal starts. None was recorded by the session that wrote this.

Not investigated: the full text of the messages and verdicts (only their first 200 to 330 characters were read), and token cost per round.
