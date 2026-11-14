# DevDigest as a PR reviewer for the factory

Written 2026-11-14. Read from the DevDigest checkout on Windows (`D:\_DEV\DevDigest`, last commit `188540e`) and the WSL clone of Hivemill. Nothing was built or run; DevDigest was not running, so no call to it was tested. Related: [08-mcp-access.md](08-mcp-access.md), [24-testing-in-the-factory.md](24-testing-in-the-factory.md), [31-multi-angle-review.md](31-multi-angle-review.md).

## Q: Can we integrate with the factory project DevDigest that serves as advanced automatic PR reviewer with agents used with their skills?

Yes. The fit is good for the factory's own pull request path, and the cleanest way in is the factory CLI calling DevDigest's HTTP API, not the factory agents calling its MCP server.

**What DevDigest offers today** (it is the course starter, so part of the "advanced" side is not built yet):

| Piece | State |
|---|---|
| Review of a GitHub PR by an agent (model + system prompt), structured findings with severity, score computed from the findings | works |
| Skills linked to an agent, added to its prompt, versioned | works |
| Grounding gate (drops findings that do not point at a changed line), PR intent, repo map as context | works |
| HTTP API on port 3001: `POST /pulls/{id}/review` with `{"all": true}`, `GET /pulls/{id}/runs`, `GET /pulls/{id}/reviews`, `POST /pulls/{id}/comments` | works |
| MCP server `devdigest-mcp` (list agents, run agent, get findings, conventions) | works; blast radius is a stub |
| Command line `review`: a diff on standard input, one prompt file, `-provider claude-code` runs on the Claude subscription with no key, `-json` | works; no skills, no repo map, no intent, no database |
| Several agents on one PR | run one after another, each a separate review; the real multi-agent review, memory, eval pipeline and export to CI are later lessons (L06, L07), not in the code |

**Three ways to connect it**

| | How | Keeps the agents and their skills | Needs |
|---|---|---|---|
| A | The reviewer pipes `gh pr diff` into the `review` command line | no (one prompt file per call) | only the binary built for Linux |
| B (recommended) | A factory CLI step calls the HTTP API when a PR opens: make sure the repo is imported, sync the PRs, start every enabled agent, poll the runs, read the findings | yes | the DevDigest API running and reachable from WSL |
| C | B, plus the judge refuses to merge while DevDigest reports blockers | yes | B, and a change to the merge gate (risky path, full suite) |

Recommended order: B as advice first, C later behind a config switch once the findings have proved useful. In B the findings are input for the factory reviewer, the same way the `multi-angle-review` result is: the reviewer re-checks each one and writes its own `factory verdict`. Reviewer and QA verdicts stay the only merge gate.

**Why the CLI and not MCP:** every role except the boss starts with `--strict-mcp-config` and an empty server list, on purpose, and tests enforce it. Giving the reviewer an MCP server loosens a guard. A CLI step (Python standard library, `urllib`) needs no change to that, and it can record what happened.

**What B has to contain**

- Config: `devdigest_review` off / advise (default off) and `devdigest_url`.
- A step on "PR opened" that starts the runs, and a later step that collects them. No HTTP call while a database transaction is open, and no reliance on the tick's environment in a program started with `systemd-run` (both are INSIGHTS entries of 2026-11-14).
- A record per PR head: state (requested, running, done, failed, skipped and why), run ids, score, counts by severity, cost. This needs a table or events; without it the UI could not tell "not asked" from "asked and failed".
- Web UI (owner rule, everything trackable): on the factory task page a "DevDigest review" row with that state, the counts, the reason of a failure or skip, and a link to the PR in the DevDigest web app (port 3000). The Settings page shows the switch.
- The findings go into the reviewer's brief as untrusted text (they are model output), with the instruction to verify each.
- DevDigest not answering is recorded as "skipped: not reachable" and the review goes on without it. It never blocks in advise mode.
- Tests: a stub DevDigest server in `tests/stubs/`, one test where the step must refuse or skip, one where it must record findings.

**Limits to know before starting**

- DevDigest reviews only `github.com` pull requests it has imported. So it fits factory-built PRs, not the local straight-to-main fixes, and not the workflow engine's per-child reviews (those happen on commits before a PR exists; only way A fits there).
- DevDigest runs on Windows here (`.exe` binaries, its own Postgres). WSL has no Docker, gcc or psql, so it cannot run inside WSL as is. WSL networking is mirrored, so `127.0.0.1:3001` should be reachable from the factory when DevDigest is up. Not tested: it was down (no answer on 3001 or 3000).
- The factory then depends on a second service that is started by hand. Hence "skipped, with the reason" rather than a hard requirement.
- Cost: each agent run is a model call paid through an API key (OpenRouter, Anthropic, OpenAI). The `claude-code` provider (subscription, no key) exists for the command line; whether the API's agents can use it was not checked.
- The repo map is built with tree-sitter grammars for JavaScript and TypeScript only (from `go.mod`). On Hivemill itself (Python, Go) reviews would most likely run with little or no repo context; on a TypeScript project it is used in full. Inferred, not run.
- DevDigest's working tree has uncommitted deletions (`.beads/`), and its last commit is of 2026-11-01.

**Decisions that are the owner's**

1. A, B or C (recommendation: B).
2. Which projects: Hivemill itself, or the target projects the factory builds (TypeScript ones get the most out of it).
3. Whether DevDigest also posts its findings as comments on the GitHub PR, or they stay in the factory UI and DevDigest.

Not done: no code, no TSR task, no request to the boss.

---

## Q: If effort is not taken into account, strategically what would be the best way to integrate?

Asked 2026-11-14, after the answer above. Judgement from the same reading of both codebases; nothing new was run.

Make DevDigest the factory's one review engine, run as a separate service beside the factory, and make the factory its main source of feedback. That is more than option C above: the two products stay separate, but review knowledge lives in one place and gets better with every PR the factory builds.

**The target shape**

| Part | Owner | What it does |
|---|---|---|
| Review rules, agents, skills, findings, scores, statistics | DevDigest | The single source of truth for "what is wrong with this change" |
| Who works on what, verdicts, merge, state | Hivemill | Unchanged; it stores only a state and a summary of each DevDigest review, with a link |
| Judging each finding | The factory reviewer | Accepts or dismisses every finding through DevDigest's API, with a reason, then writes its verdict |
| The gate | The engine and the mechanical merger (corrected 2026-11-14: was "the judge"; a story run has no judge agent, see the next question) | A child passes review, and the PR merges, only when DevDigest's review of those commits has no blocker left undecided or accepted-and-unfixed |

**Why this shape is the strategic one**

1. **One review brain, not two.** Today the factory's review rules sit in `roles/reviewer.md` (R1 to R7, S1) under a 12000-byte prompt limit that is already full. As DevDigest skills they are versioned, measurable per rule, and free of that limit. The reviewer role shrinks to judging findings and checking spec fit.
2. **Independent eyes.** Factory coder and reviewer are both Claude. DevDigest agents can run on other vendors' models through OpenRouter, so the review does not share the coder's blind spots.
3. **A feedback loop neither product has alone.** The factory produces many PRs and knows the outcome of each finding: fixed on the retry, dismissed with a reason, or missed and found later by QA or CI. Sent back to DevDigest, that is exactly the data its planned eval pipeline, per-agent statistics and memory (lessons L06 to L08) need. DevDigest then tells which agents and skills earn their cost.
4. **Lessons and skills converge.** A factory lesson about review (`factory lesson add`) and a DevDigest skill are the same kind of thing. One direction of sync (factory lesson → DevDigest skill, or the reverse) removes the duplicate.
5. **Loose coupling.** Hivemill stays standard library and SQLite and stays mergeable with upstream; DevDigest stays a product usable without the factory. The link is one HTTP contract and one adapter in the factory CLI.

**What DevDigest must gain for this**

- Review of a commit range in a local clone, not only an imported GitHub PR. This covers the workflow engine's per-child reviews and the local straight-to-main commits, which no option above reaches.
- A headless Linux install as a systemd user unit next to the factory, so it starts and is watched like the tick, instead of a Windows program started by hand.
- Repo context for Python and Go (only JavaScript and TypeScript grammars are present now).
- A run that is idempotent per head commit, and a re-review that marks each earlier finding as resolved or still open (the factory reviewer's rule R2, done by the engine).
- A callback or event stream to the factory when a run ends, an outcome route (finding fixed, dismissed, missed), and the subscription provider for API agents if cost matters.
- Not checked: whether the API has any authentication. A gate must not trust an open local port blindly.

**What Hivemill must gain**

- A DevDigest result bound to the head commit, required per project (like `required_checks`) by whatever merges: the mechanical merger in a story run, the judge in the old flow (corrected 2026-11-14: was "required by the judge"). With an explicit override that leaves a record.
- A table for the review state per PR head, and the web UI row from the answer above, extended with the per-finding decisions.
- The reviewer's brief and role text rewritten around judging findings; the review rules moved out into DevDigest skills.
- A fail-closed rule with a visible escape: DevDigest down means "waiting for DevDigest" on the task, shown as such, and the owner can waive it.

**The main risk** is the gate itself: model findings blocking merges. The design answers it with the reviewer as arbiter (a blocker counts only until it is dismissed with a reason) and with the dismissal rate per agent as the measure that shows a noisy agent. Order of rollout by risk, not by effort: advice, then judged findings, then the gate.

**What I would not do:** merge the two codebases, embed the review engine in the factory, or give factory agents the DevDigest MCP server. Each trades the loose coupling for a short-term convenience.

---

## Q: We implemented a new workflow with no judges (for HM)

Said 2026-11-14 as a correction to the answer above. Checked in `docs/workflow-engine.md` and `DEFAULT_CONFIG`: in a story run (switch `workflow_engine`) the engine reviews each child on its recorded commits before a pull request exists, and with `mech_merge` on the tick's mechanical merger merges the pull request, with no judge agent. I did not read what the mechanical merger checks before it merges.

The strategy stands; the anchor moves, and the fit gets better. A judge agent is a model deciding; the engine and the mechanical merger are code, so the DevDigest condition becomes a deterministic check instead of an instruction in a prompt.

**Where DevDigest plugs into a story run**

| Step of the run | Today | With DevDigest |
|---|---|---|
| A child reaches In Review, its commits recorded (`base_sha`, `head_sha`, round) | the engine starts a reviewer on exactly those commits | the engine first asks DevDigest to review that commit range, then starts the reviewer with the findings |
| The child's reviewer | reads the commits, runs `factory wf review CHILD pass\|changes` | judges each finding (accept or dismiss, with a reason), adds its own spec-fit check, then the same command |
| `factory wf review CHILD pass` | records the pass | refuses while a DevDigest blocker on those commits is undecided or accepted and unfixed |
| A fix round | the reviewer gets only that round's fix commits | DevDigest re-reviews only those commits and marks each earlier finding resolved or still open |
| The pull request | final review and QA, CI, mechanical merger | the mechanical merger also needs a DevDigest result on the PR head with no open blocker |
| After the merge | commits linked, closing comment, Done | the outcome of every finding (fixed in round N, dismissed, missed) is sent back to DevDigest |

**What this changes in the earlier answer**

- Review of a commit range in a local clone was one item on DevDigest's list. It is now the first requirement: the per-child review happens before any pull request, so the GitHub-PR-only review reaches just the last step.
- The adapter belongs in the engine (Go, `go/internal/workflow`, next to the Taskosaur client `go/internal/tsr`), not in the Python CLI. Both sides are Go, so the HTTP contract types can be shared or generated.
- The state for the web UI goes into the engine's own `workflow.db` beside the child states: per child and round, DevDigest requested, running, done, failed or skipped, with counts and the decisions. A child then shows "waiting for DevDigest" as its own state, not folded into `in_review`.
- The simple workflow's open point (per-child review and final review look at the same change twice) gets a clean answer: DevDigest plus the child's reviewer is the review; the pull request step keeps tests, QA and the merge checks.
- The old flow (coder, reviewer, QA, judge) is out of scope: the owner said the same day that every new build through the factory uses the new workflow. So the integration is designed for the story run only, and options A to C of the first answer (built around the old pull request path and the judge) are superseded by the table above.

Not changed: one review engine, DevDigest as a separate service, the reviewer as arbiter of findings, outcomes fed back, no MCP for factory agents, rollout in order of risk (advice, judged findings, gate).

---

## Q: Will we be able to manually reject or approve the PR from within DevDigest?

Asked 2026-11-14. Checked in DevDigest's route list (`api/specs/http-api.md`), its GitHub client and `specs/review-flow.md`.

Not today, but it can be added, and it is a natural part of the integration.

**What DevDigest can do with a pull request now**

| Action | Present |
|---|---|
| Accept or dismiss a single finding | yes |
| Show a verdict (`approve`, `request_changes`, `comment`) | yes, but it is the model's answer shown in a banner, not a human decision, and it is sent nowhere |
| Post a comment or a reply on the GitHub pull request | yes |
| Submit a GitHub review (approve, request changes) | no route, no client code |
| Merge or close the pull request | no |
| A human decision on the whole pull request | no |

**How it should work in the integration**

- Add an owner decision in DevDigest on the thing being reviewed (a child's commits, or the pull request): Approve, or Reject with a note. It is stored in DevDigest, bound to the head commit, and the factory reads it.
- Do not implement it as a GitHub approval. The factory's pull requests are opened under the same GitHub account the DevDigest token belongs to, and GitHub does not let an account approve its own pull request. (GitHub's rule as I know it; not tried here.) A decision stored in DevDigest also works for a child's commits, where no pull request exists yet.
- In a story run: a Reject on a child goes to the builder as changes, with the note, like a reviewer's `changes`. A Reject on the pull request stops the mechanical merger. An Approve can be made a requirement per project ("needs the owner's approval"), or left optional so the owner only steps in when they want to.
- The owner's decision overrides the agents in both directions, and each override is recorded with who, when and why, and shown in the factory web UI on the child or the factory task.
- This fits the split of the two UIs: the factory web UI is read-only and has no login, so it is the place to watch; DevDigest becomes the place to act on a review.

Open points: whether an owner Reject counts against the five-round limit of a child (suggestion: no), and that DevDigest's API was not checked for authentication, which matters once a button there can stop or allow a merge.

## Q: What's the general purpose of DevDigest?

Asked 2026-11-14. From DevDigest's `README.md` and `specs/review-flow.md`.

DevDigest is a local AI pull request review studio: a web app on your own machine that imports pull requests from GitHub, runs reviewer agents on them, and gives a person the findings to act on. Its purpose is to help a human review a pull request faster and better, and to be a workbench for building and measuring reviewer agents. It is not a merge tool and not a CI gate.

- **Reviewer agents:** each is a model plus a system prompt plus linked skills (rules added to the prompt). Two are built in (General, Security); you create your own.
- **A review:** the agent gets the diff, the pull request's intent (why it exists, what is in and out of scope) and a map of the repository. It answers structured findings with a severity. DevDigest drops findings that do not point at a changed line, computes a 0 to 100 score from the rest, and records the cost.
- **The person:** reads the diff and the findings in the web app, accepts or dismisses each, can follow the run live and open its trace.
- **Local:** everything runs on the machine; the only outbound calls are to GitHub and to the model provider.
- **For coding agents:** an MCP server lets Claude Code list the reviewers, run one on a pull request and read the findings.

The checkout is the starter of a course. Each lesson adds a feature: run cost and filters, skills and a conventions extractor, the intent layer and smart diff, the MCP server and blast radius, project context and a PR brief, an eval pipeline with gates and export to CI, multi-agent review with memory and per-agent statistics, plugin export and a performance dashboard. Of these, cost, skills, intent, the MCP server and an onboarding tour are in the code; the rest is not.

---

## Q: Can DevDigest (DD) be used as a gateway for Hivemill (HM)? So for instance to not merge until we have received confirmation from DD that everything is fine, or if the PR was merged manually from GitHub?

Asked 2026-11-14. Checked in `docs/mech-merge.md` and `bin/factory_cli.py` (HM), and DD's GitHub client. Nothing built or run.

Yes. HM has one place every merge goes through, and it already knows how to wait for a named check, so DD can become a gate with a small change on the HM side. The manual-merge half works too, but HM does not pick it up by itself today.

**Why HM is ready for a gate**

- The mechanical merger and `factory judge --merge` both call one function, `judge_gate_and_merge`. A condition added there holds for every merge HM makes.
- That gate already requires named checks to be green on the PR head: `required_checks`, set per project.

**The cleanest mechanism: DD reports a status on the commit in GitHub**

1. DD reviews the head commit and posts a GitHub commit status on it, for example `devdigest/review`: pending while it runs, success when no blocker is left open, failure otherwise, with a link to the review in DD.
2. HM's project gets `devdigest/review` in its `required_checks`. HM then does not merge until DD says the head is fine. A new push is a new commit with no status, so it waits again by itself.
3. The same status can be made required in GitHub's branch protection of `main`. Then a merge by hand on GitHub is held to the same rule, and DD is the gate for both ways in.
4. The owner's Approve or Reject in DD (previous question) simply sets that status, so one signal carries both the agents' result and the owner's decision.

A status belongs to a commit, not to a pull request, so the same signal also works for a child's commits in a story run, before a pull request exists.

| What is needed | Where | Present today |
|---|---|---|
| Post a commit status to GitHub | DD | no; its GitHub client reads PRs and posts comments only |
| Review a commit range, not only an imported PR | DD | no |
| Wait for a named check before merging | HM | yes (`required_checks`); not checked whether it reads commit statuses as well as Actions check runs |
| Show "waiting for DevDigest" as its own state, with the reason | HM web UI | no; today it would be one more pending check |
| An owner override that leaves a record | HM | partly: the owner can merge on GitHub (next part) |

**Merged by hand on GitHub**

Possible, but HM does not accept it automatically today:

- The owner or the director must run `factory task update T --status done --merged-externally --reason "..."`. HM then verifies that GitHub says MERGED and that the merge commit is on main, and closes the factory task.
- That records an `update` event, not a `merged` event. The story-run engine finishes a run only on a `merged` event; a task done without one is reported once as `closed-without-merge` and waits. The engine's code and document do not mention `--merged-externally`, so a story run whose pull request was merged by hand would most likely stop there. Read from the code, not tried.

To make "merged by hand on GitHub" a full second way in, HM needs: the tick noticing a pull request that GitHub reports as MERGED, recording a `merged` event that says by whom and that it was outside the gate (and what DD's status was at that moment), and the engine going on with its finish steps (links, closing comment, Done). The web UI then shows "merged by the owner on GitHub", distinct from "merged by the factory".

**What to decide**

1. DD down or silent: with DD as a required check nothing merges until it answers (fail closed). The override is the owner's merge on GitHub, or a recorded waive command in HM.
2. Whether the hand merge on GitHub is also held to DD's status (branch protection requires it) or is the owner's way around DD (it does not). Both are valid; they cannot both be true.
3. Whether a hand merge needs any DD result at all, or only gets its DD status recorded for later.

---

## Q: Save all findings and discussions about DD as docs under the DevDigest folder and create tasks for implementation; the integration and DD acting as a gateway should be an option in HM

Asked 2026-11-14. Done the same day: docs written in the DevDigest repository, 19 Taskosaur tasks created. Nothing is implemented.

**One correction to the answers above.** They propose a GitHub commit status (`devdigest/review`) as the gate signal. While preparing the tasks I read story HM-34 (local tests are the gate, no pull requests for engine runs). So the design that was turned into tasks does not use GitHub at all: Hivemill's engine asks DevDigest directly over HTTP, per child and review round, on a commit range.

**Docs, in the DevDigest repository** (`D:\_DEV\DevDigest`, not committed):

| File | What it holds |
|---|---|
| `specs/hivemill-gate.md` | the contract: data, routes, JSON, the gate state table, acceptance criteria AC-1 to AC-10 (Status draft) |
| `docs/hivemill-integration/README.md` | the two products, the design, the code facts found in both repositories, the decisions, what is left out, the task list |
| `docs/hivemill-integration/discussion.md` | a copy of this file's questions and answers, with a note on what was overtaken |

**The design in short**

- One Hivemill config key, `devdigest`: `off` (default), `advise` or `gate`; plus `devdigest_url` and `devdigest_wait_s`.
- When a child of a story run reaches In Review, the engine posts a gate review to DevDigest for the child's whole commit range, polls it each tick, and gives the findings to the child's reviewer.
- DevDigest answers one state: `pending`, `pass`, `fail` or `error`. In DevDigest a gate review is a `pull_requests` row with `kind = 'range'`, so its existing screens work.
- `advise`: DevDigest never holds anything; a silent DevDigest is recorded as skipped.
- `gate`: the reviewer's pass is refused while DevDigest has an open blocker or the owner rejected; the reviewer can dismiss a wrong finding with a reason; the owner can approve in DevDigest or waive with `factory wf dd waive`; the story does not go to the merge until every child is cleared.
- The dashboard shows it through factory events on the goal (it cannot read the engine's own database).

**Tasks** (Taskosaur, project Dev)

| Story | Children | Notes |
|---|---|---|
| DD-6, DevDigest side (epic DVDG-1) | DD-7 to DD-13 | size L; DD-7 and DD-8 start in parallel, the rest is one chain |
| HM-55, Hivemill side (epic DVDG-539) | HM-56 to HM-64 | size XL; HM-56 is the grilling with the owner and blocks the rest; HM-64 (guide, first real run) waits for DD-13 |
| HM-65, standalone (epic DVDG-539) | | a pull request merged by hand on GitHub closes the factory task with a `merged` event, behind `hand_merge_accept`, off by default |

Most children are rated complexity 2 (light model); DD-10, DD-13, HM-59 and HM-60 are 3, HM-61 and HM-65 are 4.

**Decisions I took that the owner has not confirmed** (they are the questions of HM-56): fail closed in gate mode; the factory's reviewer may dismiss a finding; every fix round is a full re-review of the child's range; in advise mode the reviewer waits up to 15 minutes for DevDigest; an owner Reject goes through the reviewer's "changes"; which agents and models review factory work.

**Left out on purpose**, listed in the DevDigest README: a GitHub commit status, repo context for Python and Go in DevDigest, DevDigest as a Linux service, matching findings across rounds, moving Hivemill's review rules into DevDigest skills.

**Code facts found on the way** that matter beyond this work:

- `workflow.db` has no migration path: the engine refuses any `user_version` but 1 (HM-59 adds one).
- The dashboard shows no engine state at all today, and cannot read `workflow.db`.
- The CLI does not validate the values of `workflow_engine`, `mech_merge`, `review_autospawn` or `risk_tiers`; only the Settings page does.
- `_judge_gate_and_merge` is not on the risky list of `ci/ci_tier.py`: the prefix `judge_` does not match the leading underscore. Not fixed, not turned into a task.
- The `no-new-python` check exists in Go but no job in `.github/workflows/tests.yml` runs it. Reported by the reading agent, not checked by me.
- `factory task update --merged-externally` records an `update` event, so a story run stops at `closed-without-merge` (HM-65).
