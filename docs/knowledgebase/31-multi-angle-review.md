# multi-angle-review: the gated-PR review workflow

Written 2026-11-13. Read from the old Windows checkout (`D:\_DEV\__Factories\hivemill`), not the WSL clone, so the files may be behind. Related: [21-where-interactions-are-defined.md](21-where-interactions-are-defined.md), [24-testing-in-the-factory.md](24-testing-in-the-factory.md).

## Q: What is multi-angle-review? (status line `multi-angle-review ▮▮▮ 3/6 · 2m11s · ↓ 248.2k tokens` in an agent pane)

`multi-angle-review` is Hivemill's saved review Workflow for risky PRs: a factory agent (reviewer, QA or coder) is running it in that pane.

**What it does** (from `D:\_DEV\__Factories\hivemill\roles\workflows\multi-angle-review.js` and the reviewer skill's `SKILL.md`):

- **Review phase:** three read-only agents each review the PR from one angle: correctness, guard/security, and spec fit.
- **Verify phase:** one verifier agent per angle tries to disprove that angle's findings.
- **Result:** `{confirmed, unverified, dropped, angles}`. This is input to the reviewer's verdict, not the verdict itself: the reviewer still re-checks each finding by hand and writes its own `factory verdict`.
- **Coder mode:** a coder's self-review of its own PR uses the angles security, spec and tests, with no verifiers (3 agents in total).

**When it runs:** only on gated PRs, meaning the diff touches `roles/hooks/`, `roles/settings/`, `ci/` or `.github/`, or has more than 500 changed lines. Other PRs get a normal single-pass review.

**The status line in the screenshot:**

| Part | Meaning |
|---|---|
| `3/6` | Most likely 3 of the 6 agents have finished, so the review phase is done and the verifiers are running. This is an inference; the 6 matches the workflow's "max 6 agents". |
| `2m11s` | Time elapsed in the workflow. |
| `↓ 248.2k tokens` | Tokens used by the workflow's agents so far. |
| `auto mode on` | The Claude Code permission mode of that pane, unrelated to the workflow. |

Cost and the off switch are described in `D:\_DEV\__Factories\hivemill\docs\review-workflow.md`, which I did not open. I read the files from the old Windows checkout, not the WSL clone, so they may be behind.

LSP: not used, the question was answered from a Markdown skill file and a `.js` workflow (text search by name; no LSP for JavaScript).

## Details from the two files

- Models (workflow `meta.description`): the angle agents run on Sonnet, the verifiers on Opus; at most 6 agents, 3 in parallel.
- How the reviewer starts it: `Workflow(name="reviewer-skills:multi-angle-review", args={"pr": "<pr url>", "base": "origin/main", "spec_task": "<T-id>"})`. Always by the saved name, never a script path: the name resolves from the main-checkout plugin, so a PR cannot weaken its own review.
- `args` must be that object. A bare string or a missing field stops the workflow with an error before any agent starts; that error is not a clean review.
- The gate has one source: `review_gate` in `bin/factory_cli.py`. Spawn adds a "Gated PR" line to the reviewer's brief when it is met. On an ungated PR the reviewer does not run the workflow, even if the brief asks.
- The angle agents are read-only: no file edits, no git write commands, no `gh pr merge/review/comment`, no `factory` commands. A guard denial inside the workflow is a finding to report.
- Reading the result: `confirmed` findings are re-checked by the reviewer in the code; `unverified` means the verifier died, so the reviewer checks them by hand; an angle with an `error` did not complete and is hand-reviewed. A short or empty result is not evidence of a clean diff.
- The reviewer's summary names that the workflow ran, the `angles` counts, `unverified`, `dropped`, any errored angle and the run id (`wf_...`).
- If the Workflow tool is unavailable or errors: normal single-pass review, said so in the summary, no retry loop.

---

## Q: What's the purpose of self review of coder agent: Agent(Self-review T-0015 diff)

(Reply of 2026-11-14, as written.)

It is a cheap second look at the coder's own change before the real review: the coder hands its diff to one fresh helper agent that has none of the coder's context, so it can spot what the coder no longer sees.

Relevant insights: no relevant insights.

The line `Agent(Self-review T-0015 diff)` in the pane is that helper running. It is step 7 of the coder's role prompt (`roles\coder.md`): "Run skill `coder-skills:self-review` (one Sonnet subagent)".

**Why it exists**

- The coder's earlier check (pre-pr-check) is done by the same agent that wrote the code, so it shares the same blind spots.
- A rejection by the reviewer, QA or judge is expensive: a new coder session, a new CI run and a new review round. In your T-0013 run each round cost about half an hour. Catching an obvious defect before the PR goes to review avoids a round.

**What happens**

1. The coder collects the factory task's spec and acceptance, the reviewer's checklist (correctness, security, spec fit, maintainability, tests) and its diff against `origin/main`.
2. It starts exactly one subagent on the Sonnet model with those three things. The subagent only reads and returns findings as "blocking or nit, file and line, failure scenario". It may not edit files, run git writes, touch the PR or run any `factory` command.
3. The coder checks every finding against the code itself, fixes the verified blocking ones, adds a test where behaviour changed and reruns the tests. A finding it cannot reproduce is dropped and reported as such.
4. The PR body gets the line `Self-review: N findings, fixed/not` and one line per finding, so the reviewer sees what was found and what was done.
5. After a rejection, the retry coder runs it again on the new diff.

**When it is three agents instead of one:** for a risky change (the diff touches the guard hooks, role settings, `ci/`, `.github/`, the sandbox modules or the merge-gate functions, or is over 500 lines) the coder runs the `multi-angle-review` workflow in coder mode: three Sonnet agents (security, spec, tests), no verifiers.

**What it is not:** it does not replace the reviewer, QA or judge. The helper works from the coder's own framing of the task and runs no gates, so those three verdicts are still required.

Timing: it runs after the diff is committed and pre-pr-check is done, and before the coder sets the factory task to `in_review`.

Checked this turn: `roles\coder.md` step 7, the skill file `roles\plugins\coder\coder-skills\skills\self-review\SKILL.md` and `docs\self-review.md`, all in the working clone. I did not look at the T-0015 pane or its PR, and the "half an hour per round" figure is from the T-0013 verdict times (00:32 reject, 01:03 next verdict).

LSP: not used, only Markdown role files were read.

Skipped: reading what the T-0015 self-review actually found; risk: none.
