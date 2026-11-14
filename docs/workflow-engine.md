# Workflow engine

A second way for the factory to run work, beside the default one: the engine takes a Taskosaur story, has one builder
implement its children in order on one branch, reviews each child as it finishes, and merges the story through one PR.
It is a separate Go program (`go/cmd/workflow`, package `go/internal/workflow`, binary `factory-workflow`) and is **off
by default**. With the switch off nothing of it is built or run and the factory behaves as without it.

Status: a whole run from `factory wf start` to Done, for one story or a batch, with the workflow chosen from size and
complexity (TSR tasks HM-22 to HM-27 and HM-33 of story DVDG-565). The three workflow names are recorded but do not
change the steps yet; see "Limits of this first version".

## Why

Two reference runs of the default way of working (figures as recorded on TSR story DVDG-565, from TSR tasks HM-4 and
HM-5):

- Goal G-001 with every automation switch off: 8 h 55 m, 253 messages, 67 agent sessions; about half the cost went to
  coordination between agents.
- Goal G-002 with upstream's seven automation switches on: at 1 h 32 m, 38 m 47 s (about 42 %) had been spent waiting
  with no agent running, for one factory task of four; the plan was four pull requests in sequence, each with its own
  full CI run.

A story run removes both: one builder keeps the context of the whole story, the engine routes the work in code, and the
full CI run, final review and QA happen once per story (or batch) instead of once per task.

## Setup

1. Switch it on: `factory config workflow_engine on` (or Settings, Automation, "Workflow engine"). The next tick (or
   `factory up`) builds `factory-workflow`; `factory wf version` answers once it is built.
2. Taskosaur access: one agent user with a personal access token, in the two files of "Taskosaur access" below
   (`~/.config/factory/tsr-url`, `~/.config/factory/tsr-token`, mode 0600).
3. Optional: `factory config workflow_reviewer_session keep` to keep one reviewer per story (default `fresh`).
4. The end of a run is the factory's own pull request path, so the switches that drive it apply as they are:
   `review_autospawn` (reviewer and QA start when the pull request opens), `coder_ci_handoff` (the builder does not wait
   for CI; a red head restarts it), `risk_tiers` and `mech_merge` (merging without a judge agent). With them off, the pull
   request waits for a lead or judge as any other.
5. The boss gets the skill `factory-boss:story-run` (`roles/plugins/boss/`) at its next start or relaunch.

## How to use

Tell the boss which prepared Taskosaur keys to build: "pick up HM-12", or "for project taskosaur build in batch HM-12,
HM-13". The boss runs `factory wf start --story …` (skill `story-run`), reports the goal id and the workflow, and tells you
when a run is blocked or merged and Done. A key must be prepared: each child (and, in a batch, each story) has a
description, an `## Acceptance criteria` section with list items and its tests field, and the story has a size or a
complexity unless a workflow is named.

The workflow is chosen from the story's size and complexity, the larger result winning (`Choose` in
`go/internal/workflow/choose.go`); naming one (`--workflow`) overrides it, and `status` shows "chosen" or "given":

| Workflow | When |
|---|---|
| `simple` | size XS or S and complexity 1 or 2 |
| `medium` | size M, or complexity 3 |
| `huge` | size L or XL, or complexity 4 or 5, or the story has children |

A story with neither size nor complexity is refused unless a workflow is named. In a batch the largest workflow of its
stories applies. The texts of each workflow are in [workflows/README.md](../workflows/README.md).

## How to check

| Check | Command | A correct result |
|---|---|---|
| built | `factory wf version` | `factory-workflow 0.1.0`; exit 2 with "is not built" means the switch is off or no tick has built it yet |
| Taskosaur reachable | `factory wf tsr show <key>` (as the owner) | the task's title, status, description and tests field |
| a run | `factory wf status --goal <goal>` | the run's workflow (chosen or given) and state, each child with its state and fix rounds, the pull request once open |
| problems | `factory wf incidents --goal <goal> --json` | empty while all goes well; each rejection, failure, warning and escalation with its full detail |
| the record | the story in Taskosaur | each child's builder and reviewer comments, the "reviewed by agent" mark, and after the merge its commits and Done |

## The whole run

1. The boss runs `factory wf start --story KEY` for a prepared story (see "Starting a run"): one factory goal, one
   factory task (one branch, one pull request at the end), the builder skill for the goal, one builder.
2. The builder builds the children in order, one commit (or a short run of commits) per child, each naming the child's
   key, and sets each In Review with `factory wf tsr status CHILD in_review`, which records that child's commits first;
   no pull request and no CI wait between children.
3. Each tick notices a child that reached In Review and starts its reviewer on exactly that child's commits (see "Review
   per child"). A pass sets the "reviewed by agent" mark; changes go back to the builder, at most 5 rounds per child.
4. The builder runs `factory wf built` when every child is In Review. When every child is also reviewed, the engine
   mails the builder once to open the one pull request (`workflows/prompts/builder-open-pr.md`, with a body that passes
   the factory's PR body rules). The run is `merging`.
5. From the open pull request on, the factory's existing automation runs unchanged: final review and QA, CI, the judge
   or the mechanical merger. The engine only waits; it never calls `gh` and writes no verdict.
6. When the factory task is `done` with a `merged` event, the engine finishes, one step per state, each done once and
   retried on the next tick when it fails: link each child's recorded commits to it (from `child_commits`, so neither the
   worktree nor the deleted branch is needed), and the merge commit to the story, its full hash resolved in the
   project's repository (`linking`); comment on the story with the pull request, the merge commit, the fix rounds per
   child and the elapsed time (`reporting`); move every child, then the story, to Done (`closing`); one `report` mail to
   the boss, "KEY merged and Done" (`announcing`). Then the run is `done` and the goal's skills folder is removed.

| Run state | Meaning | Left by |
|---|---|---|
| `starting` | goal made, builder not started yet | the rest of `start` |
| `failed` | `start` stopped part-way; see the incident | (final; a new start for the story is refused) |
| `building` | the builder works the children; reviews run beside it | `factory wf built`, a stop |
| `built` | every child built; late fixes and reviews still run | every child reviewed: the open-PR mail |
| `blocked` | stopped for the boss (builder blocked, round limit, silent reviewers, builder resume limit) | `factory wf resume` |
| `merging` | the pull request is the factory gate's | the task done with a `merged` event |
| `linking`, `reporting`, `closing`, `announcing` | the finish steps after the merge, one each | the step succeeding |
| `done` | merged and Done in Taskosaur | (final) |

| Child state | Meaning |
|---|---|
| `todo` | not built yet |
| `in_review` | built; waiting for its reviewer |
| `reviewing` | a reviewer is on it |
| `reviewed` | passed review |
| `fixing` | changes requested; back with the builder |
| `stuck` | 5 rounds of changes; the run waits for `factory wf resume` |
| `blocked` | the builder cannot build it as written |
| `reported` | merged; its story's closing comment is posted |
| `done` | merged and Done in Taskosaur |

## The switch

`factory config workflow_engine on` (or the "Workflow engine" row in the Automation group of the Settings page).

- `off` (default): nothing happens.
- `on`: `factory up` and the tick build `factory-workflow` into `~/.local/lib/factory/` with a stamp (the tree hash of
  `go/`), exactly like the Go worker guard; the tick then launches `factory-workflow tick` once a minute, detached.

## Commands

`factory wf …` runs the binary with the same arguments and exits with its code. Binary missing or stamp stale:
exit 2, "factory-workflow is not built; set workflow_engine on and wait for a tick, or run factory up".

| Command | What it does |
|---|---|
| `factory wf version` | prints the version |
| `factory wf status [--goal ID]` | one line per run: goal, story key, workflow, state, and the pull request once there is one; with `--goal` also each child with its state and fix rounds; `no runs` when there are none |
| `factory wf tick` | advances every run once; the tick calls it, and only the owner may (exit 3 for an agent). A second run while one holds `run/workflow.lock` exits 0 at once |
| `factory wf incidents [--goal ID] [--kind KIND] [--json]` | lists incidents, newest first; `--json` prints the full detail. Owner and boss only (exit 3 otherwise) |
| `factory wf tsr …` | Taskosaur reads and the few writes agents may make; see "Taskosaur access" |
| `factory wf start --story KEY [--story KEY …] [--workflow simple\|medium\|huge] [--project ID]` | starts a story run (boss or owner); several `--story` make a batch; see "Starting a run" and "Batches" |
| `factory wf blocked CHILD --reason TEXT` | the run's builder stops on a child it cannot build as written: child and run `blocked`, an escalation incident, a decision mail to the boss |
| `factory wf built` | the run's builder reports every child In Review: run `built` |
| `factory wf review CHILD pass\|changes --notes FILE` | the child's reviewer records its result; see "Review per child" |
| `factory wf resume --goal ID [--fresh-builder]` | restarts a blocked run (boss or owner) |

## Starting a run

`factory wf start --story KEY` (TSR task HM-24):

1. Reads the story and its children from Taskosaur (a task without children is its own only child) and refuses, creating
   nothing, unless every child is prepared: a description, a `## Acceptance criteria` section with at least one list
   item, and its tests field (`none: <why>` counts). The message names each key and what it lacks. A story that already
   has a run is refused too, with that run's goal and state.
2. Checks the templates of `workflows/` (HM-31): the kickoff must fill without an unknown placeholder.
3. `factory goal new` (title = the story's title and key, intent = its description, success criteria = its
   acceptance section), then records the run as `starting`, with one `children` row per child in list order.
4. `factory task add` (role coder): one factory task, one branch `factory/<task>`, one PR for the whole story.
5. Copies `workflows/goal-plugin/` into `roles/plugins/goals/<goal>/` (the skill `story-run:story-builder`).
6. `factory spawn coder --name coder-<task>` (with the org prefix where spawn's naming rule needs one) with the
   kickoff `workflows/prompts/builder-kickoff.md`; the run becomes `building`.

A failure after step 3 leaves the run `failed` with an incident naming the step, the command, its exit code and its
error output (`factory wf incidents --goal <goal>`); the goal stays for the owner to close.

The engine checks its caller (boss or owner for `start`, the run's builder for `blocked` and `built`) and then runs its
factory steps with no agent identity, which is the owner, as the tick does: the boss may not add tasks or spawn coders
itself. `bin/factory` is passed to the engine as `FACTORY_CLI`.

### A child's commits

A child's commits are recorded when the builder says it is done, not when the tick looks (by then the builder may have
pushed the next child). `factory wf tsr status CHILD in_review`, run by the run's builder, refuses (exit 2) unless the
worktree is clean and `HEAD` is `origin/<branch>` ("commit and push first"), and unless a commit since the start of the
run names the child's key ("no commit names CHILD"). It then stores each such commit not stored yet in `child_commits`
with the child's current round, sets `head_sha` to `HEAD` (and `base_sha`, once, to the previous child's head or the
merge base), and only then moves the task. The reviewer is given exactly those commits (`{commits}`: round 1 all of the
child's commits, later rounds only that round's fix commits). While a run is `building`, each tick only notices the
Taskosaur status; a child moved to In Review some other way has no commits for its round and waits.

## Batches

(TSR task HM-33.) `factory wf start --story A --story B …` makes one run of several prepared stories, in the order
given: one goal, one factory task, one branch, one builder session for all of them, and one pull request with its full
CI run, final review and QA once, after the last story.

- Only Taskosaur keys make a batch (owner decision of 2026-11-14); the engine never writes, splits or enriches an item.
  Every item must be prepared: a story's children as for a single run, and the story itself too (description,
  acceptance section, tests field); a single prepared task is a story with one child.
- Refused before anything is made, each with a `start-refused` incident (goal id `-`): a story listed twice, stories
  from different Taskosaur projects, an item that is not prepared (the message names each key and what it lacks), and
  a story already in a run that is not `done`.
- `children` holds all children of the first story in order, then of the second, and so on, each with its story key.
  The builder finishes one story's children before the next story's (the `story-builder` skill).
- Review and the fix loop work per child as for one story; the round limit stops the whole batch.
- The mail to open the pull request goes only when every child of every story is reviewed. Its title is
  `<task>: batch <first>..<last> (<n> stories)`; the body lists each story with its children.
- After the merge: commit links per child, one closing comment per story (posted once each, also when a later story's
  comment fails and is retried), every child and then every story to Done, one mail to the boss naming all stories.
- `factory wf status` shows, for a batch, each story with how many of its children are reviewed.
- A blocked batch resumes as a whole (`factory wf resume`). Dropping one story from a running batch is not supported:
  stop the run and start a new one.

## Review per child

(TSR task HM-25.) While the builder goes on, each tick keeps one review going per run, in list order:

- The first child `in_review` gets a reviewer (`factory spawn reviewer`, kickoff `workflows/prompts/child-review.md`)
  for its recorded commits (see "A child's commits"); the child becomes `reviewing`. A refused spawn is tried again on
  the next ticks; the 5th refusal in a row for the same name stops the run (`spawn-retry-limit`). In round 2 and later the kickoff carries the
  earlier rounds' notes ("Findings of round N, to check first:").
- The reviewer ends with `factory wf review CHILD pass|changes --notes FILE` (only the reviewer of that child's current
  round; anyone else, or a second result, exits 3). The engine first saves the child's new state, then queues the
  comment with the notes, Taskosaur's "reviewed by agent" mark (`PASSED` or `FAILED`, `ref` = the head reviewed;
  `FAILED` moves the child back to In Progress there) and, on `changes`, the mail to the builder. The queue (`pending`)
  runs at once and at the start of every tick until each item is done, each once; a failed item leaves one
  `pending-failed` warning.
  - `pass`: the child is `reviewed`.
  - `changes`: `rounds` + 1, a `rejection` incident with the notes, the child `fixing`, and one `request` mail to the
    builder (`workflows/prompts/builder-findings.md`). When the builder sets it In Review again, it gets a new head (the
    base stays) and a new reviewer.
  - The `MaxFixRounds` (5th) `changes`: the child is `stuck`, the run `blocked`, and the boss gets one `decision` mail with
    every round's findings. Nothing is started for the run until `factory wf resume --goal G`.
- A reviewer that ends without a result: the child waits for a new reviewer once; the second time the run is `blocked`
  and the boss is told.

### Reviewer session: fresh or kept

Config `workflow_reviewer_session` (Settings page, "Reviewer session in story runs"), read when each review starts:

- `fresh` (default): a new reviewer per child and round, named `review-<child>-r<round>`.
- `keep`: one reviewer per run, `review-<task>`. The first review starts it; for each later child the engine resumes it
  (`factory spawn reviewer --resume <session id>`) and sends the child as a `request` mail
  (`workflows/prompts/child-review-resumed.md`). With no session id, or a refused resume, that review runs fresh and a
  `reviewer-resume-fallback` warning is recorded.

`factory spawn … --resume SESSION` is the fifth seam in `bin/factory_cli.py`: owner only (the engine), roles reviewer and
coder.

### The builder ends early

A builder whose session ended (`done`, `exited`, `lost`, `cancelled`) while work is left is resumed with its own session
(`factory spawn coder … --resume`) and told where it was (`workflows/prompts/builder-resumed.md`).

- An early end with work in hand (a child still to build, a child to fix whose findings reached the builder while it ran
  or after a later resume, or the pull request after its mail reached it) counts: at most `MaxBuilderResumes` (3), a
  `builder-resumed` warning each. The 4th, or a builder with no session id, stops the run (`builder-resume-limit`).
- Waking a builder that ended with nothing in hand, to give it new work (findings, the mail to open the pull request),
  does not count: a `builder-woken` warning each, no limit.
- A refused resume is tried again on the next ticks; the 5th refusal in a row stops the run (`spawn-retry-limit`).

The engine never starts a builder fresh by itself: a fresh one would not know the earlier children.

The same holds while the run is `merging` and the builder has not opened the pull request yet. A `merging` run with no
pull request, no agent and no change for 2 hours is reported to the boss once (`stale-merging`); a run whose task is
`done` without a `merged` event (closed by hand) is reported once (`closed-without-merge`) and waits.

`factory wf resume --goal G [--fresh-builder]` (boss or owner) restarts a `blocked` run: `stuck` children go back to
`fixing` with their rounds reset, `blocked` children to `todo`, and the counters of early ends start over.
`--fresh-builder` starts a new builder session whose kickoff (`workflows/prompts/builder-fresh.md`) lists the children
already built with their commit ranges.

## Taskosaur access

Factory agents have no MCP, so the engine talks to Taskosaur over its REST API (package `go/internal/tsr`) with one
personal access token of a Taskosaur agent user. Agents never hold the token; they get the `factory wf tsr` commands.

The owner sets it up once, in two files the engine reads and nothing else:

| File | Holds |
|---|---|
| `~/.config/factory/tsr-url` | the base address, ending in `/api` (for example `http://localhost:4000/api`) |
| `~/.config/factory/tsr-token` | the personal access token (`tsr_pat_…`) of an agent user (only agent users may set the "reviewed" / "tested by agent" marks) |

Each must be a regular file (not a symlink), mode 0600, owned by the factory's user and hold one line; the folder
should be mode 0700:

```
mkdir -p ~/.config/factory && chmod 700 ~/.config/factory
( umask 077; printf '%s\n' 'http://localhost:4000/api' > ~/.config/factory/tsr-url; cat > ~/.config/factory/tsr-token )
```

A file that breaks the rule is refused with a message naming the file and the rule, never its content. Requests time
out after 15 s, are tried at most 3 times on a network error or a 5xx (never on a 4xx), and never follow a redirect.
The token appears in no message, log or event.

| Command | Does | Roles (plus the owner) |
|---|---|---|
| `factory wf tsr show KEY` | key, title, type, status, size, complexity, the description (with the acceptance criteria), the E2E tests field and the attachment list | coder, reviewer, qa, staff-engineer, boss |
| `factory wf tsr children KEY` | one line per child: key, status, title, in the board's list order, Done ones included | the same |
| `factory wf tsr attachments KEY` | one line per attachment: id, size, MIME type, file name | the same |
| `factory wf tsr attachment ID --out PATH` | saves the file (mode 0600, at most 50 MB). `PATH` must be inside the current directory or `<tmp>/claude-<uid>`; an existing file is not overwritten; the server's file name is never used as a path | the same |
| `factory wf tsr comment KEY --file PATH` | adds the file as a comment whose first line names the calling agent | coder, reviewer, qa, staff-engineer |
| `factory wf tsr status KEY in_progress\|in_review` | moves a child of the run to the first In Progress status, or (after recording its commits, see "A child's commits") to the first status that asks for the owner's review | the run's builder only |

The token reaches every task, so every caller but the owner and the boss is held to its own run: the key (for
`attachment`, the task the attachment belongs to) must be a story or child of the run whose factory task the caller
works on; anything else exits 3, "KEY is not part of your story run". The marks, Done and commit links have no command:
only the engine sets them (the client's `AgentCheck`, `SetStatus` and `LinkCommit`).

## State

The engine keeps its own SQLite file, `$FACTORY_HOME/db/workflow.db` (mode 0600, `PRAGMA user_version` 1), created on
first use. It only reads `factory.db`; its one write there is an `events` row. The factory's schema is not changed.

| Table | Holds |
|---|---|
| `runs` | one row per run: goal id (key), first story, workflow name, factory task, state, times |
| `run_stories` | the stories of a run, in order (one row for a single-story run) |
| `children` | the Taskosaur children of the run's stories, in order across the run, with state, fix rounds and commit range |
| `incidents` | every rejection, failure, warning and escalation, with a structured cause and a JSON detail |
| `child_commits` | each child's commits with their round, recorded by the builder's `in_review` |
| `pending` | queued comments, marks and mails of a review result, until each is done |
| `counters` | small per-run counters (spawn refusals in a row, the open-PR mail reaching a running builder) |

### Incidents

Every rejection, failure, warning and escalation is recorded through one function, `Engine.Record`, with everything
known at that moment in `detail` (the command or call that failed with its exit code or HTTP status and output, the
state before and after, the ids involved). `kind` is one of `rejection`, `failure`, `warning`, `escalation`; `cause` is
a short value from the package's constant list in `go/internal/workflow/state.go`. `Record` also writes exactly one factory event:
entity `workflow`, entity id the goal, action the kind, detail `cause=<cause> incident=<id>` and nothing else, because
the events table is shown by a web UI without login.

When a run's step fails or panics during `tick`, an `engine-error` failure is recorded and the other runs go on.

## Troubleshooting

| Message or symptom | Cause | Fix |
|---|---|---|
| `factory-workflow is not built; set workflow_engine on …` (exit 2) | the switch is off, or the stamp does not match `go/` yet | switch it on and wait a minute, or run `factory up` |
| `not prepared for a story run … KEY: missing …` | a child (or batch story) lacks its description, an `## Acceptance criteria` section with list items, or its tests field | complete the task in Taskosaur, then start again |
| `KEY: neither size nor complexity is set; rate it …` | no workflow can be chosen | rate the story, or name a workflow with `--workflow` |
| `story KEY already has run G-… (state …)` | the story is in a run that is not `done` (a `failed` run counts) | look at that run (`factory wf status --goal`, `factory wf incidents --goal`); close its goal before starting again |
| `story KEY is listed twice` / `… another Taskosaur project …` | a batch was given the same key twice, or keys of two projects | one key once; one project per batch |
| `…/tsr-token: must be a regular file (not a symlink), mode 0600, owned by you and not empty` | the Taskosaur files break the rule | `chmod 600` the file, replace a symlink by the file itself |
| `run G-… failed at spawn` (and a `spawn-refused` incident) | the factory refused to start the builder (resource gate, missing project) | read the incident's `stderr`; the goal stays for the owner to close |
| boss mail "blocked on CHILD" | the builder ran `factory wf blocked` | decide, tell the builder, `factory wf resume --goal` |
| boss mail "did not converge in 5 rounds" | a child got changes requested five times | read the findings in the mail and on the child; `factory wf resume --goal` resets its rounds |
| boss mail "no review result for CHILD" | two reviewers ended without `factory wf review` | look at their panes or logs, then `factory wf resume --goal` |
| boss mail "the builder ended with N children left" | the builder ended more than 3 times, or has no session to resume | `factory wf resume --goal G --fresh-builder` |
| boss mail "no pull request and nobody working" | the run is `merging` but nobody opened the pull request for 2 hours | look at the builder; `factory relaunch` it or resume the run |
| `commit and push first` / `no commit names CHILD` (exit 2, to the builder) | the builder set a child In Review with uncommitted or unpushed work, or with no commit naming the child | commit with the key in the subject, push, run it again |
| `KEY is not part of your story run` (exit 3) | an agent asked about a task outside its run | nothing to fix: agents only see their own run |
| boss mail "could not be started" | `factory spawn` refused the same agent 5 times in a row (detail: its last answer) | fix the cause, then `factory wf resume --goal` |
| boss mail "closed without a merge" | the run's task is done, but the factory recorded no merge | decide what happened to the work; the run waits |
| a `pending-failed` warning in the incidents | a queued comment, mark or mail of a review failed | nothing, unless it repeats: it is retried every tick and done once |
| a `taskosaur-error` warning in the incidents | a finish step failed in Taskosaur (detail: HTTP status, route) | nothing, unless it repeats: the step is retried every tick and never done twice |
| a `failure` / `engine-error` incident each tick | a run's step fails (detail: the error and the run's state) | fix the cause named in the detail; the other runs are not affected |

## Limits of this first version

- The three workflows differ only in their name: the architect step (design and split before the build), QA of the
  whole branch before the pull request (`huge`) and the call to the architect after two rounds on the same finding are
  not built.
- A plain-text request does not become a story: only prepared Taskosaur keys start a run.
- No merge queue and no conflict handling beyond upstream's; stories that touch the same files should run one after
  another.
- No estimates before a run and no actuals written to Taskosaur after it (beyond the closing comment's rounds and
  elapsed time).
- A child's commits are found by its key in the commit subject; a commit that names no child is linked to none and
  reviewed with none.

## Upstream files this feature touches

The engine, the client and the texts are new files: `go/cmd/workflow/`, `go/internal/workflow/`, `go/internal/tsr/`,
`workflows/` (fork only), `roles/plugins/boss/`, `docs/workflow-engine.md`. Files that also exist upstream:

| File | Change |
|---|---|
| `bin/factory_cli.py` | the five seams below and two `DEFAULT_CONFIG` keys |
| `bin/flags.json` | the two keys |
| `go/internal/cli/defaults_gen.go`, `go/internal/cli/testdata/golden/base.sql`, `…/golden/s1/{config,config_unknown_key,flags_json,flags_table}/*` | regenerated for the two keys |
| `web/views/settings.py` | two rows in the Automation group |
| `docs/README.md` | one link |
| `tests/test_mech_merge.py` | the class `WorkflowEngineSeamTests` |
| `tests/test_flags.py`, `tests/test_web_settings.py`, `tests/test_plugins.py` | the new flag, the two Settings rows, the boss plugin tree |

## Seams in upstream files

Everything above is new files except these places in `bin/factory_cli.py`. After a merge from upstream,
`tests/test_mech_merge.py` (`WorkflowEngineSeamTests.test_the_seams_are_in_factory_cli`) fails when one is gone.

1. `DEFAULT_CONFIG`: the key `workflow_engine` (`off` | `on`).
2. `guard_tick`: builds `./cmd/workflow` as `WORKFLOW_BIN` while the switch is on.
3. `cmd_tick`: the step `tick_workflow(con)` right after the mechanical merger, error event `workflow-error`.
4. The `wf` subcommand (`cmd_wf`).
5. `cmd_spawn`: `--resume SESSION` (owner only, reviewer or coder), passed to `spawn(resume=…)`.

The keys `workflow_engine` and `workflow_reviewer_session` are the only additions to `DEFAULT_CONFIG`. A new key also
needs `bin/flags.json`, `go generate ./internal/cli` (rewrites `defaults_gen.go`) and the Go golden files
(`go test -count=1 -run TestGolden ./internal/cli/ -args -update-golden`, run from `go/`).
