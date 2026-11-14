# Reference run 2 (G-002): result and comparison with G-001

Measured on 2026-11-14 18:25 from the factory database (`~/factory/db/factory.db`, read-only) and from git in the reference repository. Both runs were measured with the same queries in this session, so the G-001 column can differ by a few units from the table in TSR task HM-5, which was measured on 2026-11-13.

## Q: How did reference run 2 compare with the first run?

Same goal text, word for word; run 2 had the seven automation switches on and built on `ndovgaluk/hivemill-ref` from commit `8d616f6`.

| Measure | G-001 (run 1) | G-002 (run 2) |
|---|---|---|
| Goal created | 2026-11-12 23:35:24 | 2026-11-13 23:23:58 |
| Goal closed | 2026-11-13 08:30:49 | 2026-11-14 18:23:37 |
| Wall time, created to closed | 8 h 55 m | 18 h 59 m |
| Time to the first merge | 1 h 24 m | 3 h 45 m |
| Factory tasks | 11 (coder 8, pm 3) | 13 (coder 7, pm 5, qa 1) |
| Merged pull requests | 8 | 7 |
| Merged diff | 18 files, +2,207, -57 (from HM-5) | 19 files, +2,451, -8 |
| Agent sessions started in the window | 67 | 147, of which 82 are restarts of the lead |
| Sessions without the lead | 65 | 65 |
| Coder / reviewer / QA / judge sessions | 22 / 15 / 13 / 8 | 13 / 12 / 15 / 6 |
| Messages in the window | 258 | 342 |
| Events in the window | 519 | 875 |
| Reviewer verdicts | 10 pass, 6 fail | 8 pass, 4 fail |
| QA verdicts | 10 pass, 3 fail | 11 pass, 1 fail |
| Judge | 8 merges | 7 merges, 1 reject |
| Audit rounds before sign-off | 2 (gaps, ready) | 2 (gaps, ready) |

Not measured for run 2: model requests, list-price cost, spec updates on running tasks (the query used here does not reproduce the 90 of HM-5, so no figure is given for either run).

## Where the time of run 2 went

- 23:24 to 07:43 (8 h 19 m): plan, six pull requests merged, first audit (gaps), follow-up tasks. This part is comparable with the whole of run 1 and was slightly faster.
- 06:43 to 16:27 (9 h 44 m): the last code task, T-0020, stood still. Its coder's `factory pr create` was denied by the agent's permission check at 06:43, a denied command needs the owner, and the question did not reach the owner: the boss pane got no new-mail nudges from 23:40 to 14:28 (the director's finding, message M554), then the owner answered at about 16:20. In the event log this is a gap with no agent event from 07:51 to 14:13 (6 h 22 m) and another from 14:28 to 16:26.
- 16:27 to 17:56 (1 h 29 m): T-0020 through three review rounds and three CI runs.
- 17:56 to 18:23 (27 m): audit round 2, then the director waited for the CI run on `main` before signing off.

Estimate, not a measurement: without the 9 h 44 m stall the run would have closed in about 9 h 15 m, the same as run 1.

## What the switches changed

- Fewer coder sessions (13 against 22) and fewer rejections (5 failing verdicts against 9).
- The lead no longer stays alive: it parks and is started again on each event, hence 82 lead sessions.
- No gain in wall time: each pull request still waited for CI (about 20 minutes per run), and the serial plan made the first merge later.
- A new failure mode: a question for the owner can sit unseen for hours.

## Limits of the comparison

- The factory's own code changed three times during run 2 (fast-forwards to the fork's `main` at 03:13, 04:35 and 16:57).
- The database still held the plan, specs and messages of G-001 while G-002 ran.
- The reference repository started with a failing `go` CI job.
- The reviewers of run 2 knew nothing of the isolation hole run 1 found; whether run 2 covered it was not checked here (the audit says all six success criteria have evidence).

## After the run

Done at 18:27: `factory project update hivemill --repo ~/factory --gh ndovgaluk/hivemill` and `factory config worktree_reuse 1`. The project list shows repository `~/factory`, GitHub `ndovgaluk/hivemill`.

## Q: Do we need hivemill-ref any more?

Answered 2026-11-14. Not to run anything; only as the record of reference run 2.

- Nothing uses it now: the `hivemill` project points at `ndovgaluk/hivemill` again (since 18:27), and no goal is open on it.
- What it still holds: the seven pull requests of G-002 with their review threads and CI runs. The numbers of the run are in this file and in the factory database, which do not depend on the repository; the pull request discussions exist only there.
- A later comparison run (for example the reference goal through the workflow engine) needs a repository whose `main` is commit `8d616f6`. `hivemill-ref` cannot serve again as it is, because its `main` now contains the feature. A fresh one is made the same way from the branch `baseline/pre-g-001` on the fork.
- The local clone `~/src/hivemill-ref` and the worktrees of G-002's tasks under `~/factory/worktrees` are only disk space.

Recommendation: archive the GitHub repository (read-only, keeps the evidence, costs nothing), and remove the local clone when convenient. Not checked: whether `factory clean` removes G-002's worktrees by itself now that the project points elsewhere. Nothing was changed.
