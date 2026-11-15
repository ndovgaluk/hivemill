# Hand merges on GitHub

A pull request is normally merged by the factory: the judge (or the mechanical merger, `docs/mech-merge.md`) merges it
only when the reviewer and QA passed on its head and the required checks are green. When the owner merges a pull request
**by hand on GitHub**, none of that ran, and the factory does not know the change landed: the task stays `in_review`,
and a story run of the workflow engine waits for a `merged` event that never comes (`docs/workflow-engine.md`).

This page describes how such a merge is accepted (TSR task HM-65).

## Two ways to accept a hand merge

| Way | When | Who |
|---|---|---|
| `factory task update T --status done --merged-externally --reason "..."` | at once | the owner or the director |
| the switch `hand_merge_accept on` | within an hour (the drift check runs at most hourly) | the tick |

Both go through the same check and the same close:

1. **Verify** (`verify_merged_externally`): GitHub must say the pull request is `MERGED` and its merge commit must be on
   the base branch (`gh api repos/OWNER/REPO/compare/BASE...SHA` is `identical` or `behind`). Anything that cannot be
   checked is a refusal, never a pass.
2. **Close** (`close_merged_externally`): the task becomes `done`; an `update` event records
   `status=done merged-externally by=... pr=... merge_sha=...`; a `merged` event records
   `@<sha8> by=<who>: merged-externally — <reason>`; then the post-merge hook runs (lessons, role changes), as after a
   judge merge. The `merged` event is what a story run waits for: the engine goes on to its finish steps (link commits,
   comment, Done, mail the boss).

`by=` names the owner or director for the manual command, and `github-hand-merge` for the switch.

## The switch

```
factory config hand_merge_accept on     # off (default) | on
```

Also on the Settings page, group Automation: "Accept pull requests merged by hand on GitHub".

- **Off** (default): exactly the old behaviour. The hourly drift check sees the merged pull request and mails a `D2`
  drift line ("in_review but PR #N MERGED") to the lead or director (`docs/lifecycle.md`).
- **On**: in the same drift run, every `in_review` task whose pull request GitHub reports `MERGED` is verified and
  closed as above, and gets no `D2` line. A merge that cannot be verified closes nothing: the task gets one
  `hand-merge-unverified` event with the reason (once per task and reason), and its `D2` line stays.

A closed (not merged) pull request is never accepted. The switch does not change the judge, the mechanical merger or
anything else of the merge gate.

## What the dashboard shows

On the task page (`/task/T-...`), in the attempt timeline:

- **Merged by hand on GitHub (outside the factory gate)**, with the merge commit, in amber instead of the green of a
  normal merge;
- **Hand merge could not be verified**: the verifier's reason (not merged, merge commit not on the base, gh failed).

A story run's goal page shows the run moving on from `merging` once the `merged` event exists.

## Limits

- The switch acts at the hourly drift check; use the manual command when it must happen now.
- Only pull requests of tasks in `in_review` are looked at, as the drift check does.
- A hand merge bypasses the factory's merge gate: no judge verdict and no gate checks are recorded for it. That is why
  it is off by default and why both events say `merged-externally`.
