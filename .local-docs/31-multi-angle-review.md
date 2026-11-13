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
