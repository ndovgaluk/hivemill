# Story runs: the workflow engine's texts

A story run builds prepared task-manager stories with one builder, a review per child and one pull request. The engine (`go/cmd/workflow`, reached as `factory wf`) routes the work; this folder holds every text an agent reads in a run. The engine loads these files and never rewords them. The feature guide is `docs/workflow-engine.md`.

Today's way of working (boss, director, lead, pm, coder, reviewer, qa, judge) is unchanged and stays the default. A story run is used only when the boss starts one for task-manager keys the owner named, and only while the switch `workflow_engine` is on.

## The run in one table

| Step | Who | What happens |
|---|---|---|
| Start | boss | `factory wf start --story <key> ...`; every story and child must be prepared: description, an "Acceptance criteria" section, tests written |
| Build | builder (role `coder`, one session for the whole run) | children in order, one branch, a commit per child, each child set In Review when built; no pull request and no CI wait between children |
| Review | reviewer (role `reviewer`) | each child as it reaches In Review, on that child's commits; pass sets the "reviewed by agent" mark, changes go back to the builder |
| Fix | builder | after the child in hand, before the next; at most 5 rounds per child, then the run stops for the owner |
| Pull request | builder, on the engine's mail | one for the whole run, when every child is reviewed |
| Final checks and merge | the factory as it is today | CI or the local gate, final review and QA, merge |
| Done | engine | commits linked, every child and story Done in the task manager, the boss told |

## The three workflows

| Name | Chosen when | File |
|---|---|---|
| `simple` | size XS or S and complexity 1 or 2 | [simple.md](simple.md) |
| `medium` | size M, or complexity 3 | [medium.md](medium.md) |
| `huge` | size L or XL, or complexity 4 or 5, or the story already has children | [huge.md](huge.md) |

The larger result wins when size and complexity disagree; the owner can name one through the boss. In this first version all three run the steps above: the name is recorded and shown, and the steps that will make them differ (the architect, QA before the pull request) are not built yet. Each file says what is planned.

## Every text, who reads it, and what loads it

| File | Read by | When | Loaded by (task) | Placeholders |
|---|---|---|---|---|
| `goal-plugin/story-run/` (skill `story-builder`) | builder | whole run | copied to `roles/plugins/goals/<goal id>/` at start (HM-24) | none |
| `prompts/builder-kickoff.md` | builder | at start | HM-24 | `{agent}` `{goal}` `{task}` `{branch}` `{stories}` `{first_story}` |
| `prompts/builder-findings.md` | builder | a child needs changes | HM-25 | `{child}` `{round}` `{max_rounds}` |
| `prompts/builder-open-pr.md` | builder | every child reviewed | HM-26, HM-33 | `{title}` `{body}` `{task}` `{base}` `{child_count}` `{story_count}` |
| `prompts/builder-resumed.md` | builder | its session ended early and was resumed | HM-25 | `{resume_count}` `{max_resumes}` `{goal}` `{task}` `{branch}` `{children_state}` `{pending}` |
| `prompts/builder-fresh.md` | a new builder | the owner asked for a fresh builder | HM-25 | `{agent}` `{goal}` `{task}` `{branch}` `{stories}` `{children_done}` `{children_todo}` |
| `prompts/child-review.md` | reviewer | a child is In Review (fresh session) | HM-25 | `{agent}` `{goal}` `{task}` `{child}` `{story}` `{round}` `{max_rounds}` `{commits}` `{base_sha}` `{head_sha}` `{previous_findings}` |
| `prompts/child-review-resumed.md` | reviewer | the same, when one reviewer is kept for the story | HM-25 | `{child}` `{story}` `{round}` `{max_rounds}` `{commits}` `{base_sha}` `{head_sha}` `{previous_findings}` |
| `roles/plugins/boss/factory-boss/skills/story-run/SKILL.md` | boss | the owner names keys to build, or engine mail arrives | attached to the boss by `factory spawn` (HM-27) | none |

Rules for the placeholders: `{commits}` is one line per commit of this child, oldest first, as `<full hash> <subject>`: in round 1 every commit of the child, from round 2 only the commits made since the head it was last reviewed at; `{previous_findings}` is empty in round 1 and otherwise the text "Findings of round N, to check first:" followed by the reviewer's earlier notes for this child; `{stories}` is the keys in order, comma separated; `{children_state}` is one line per child with key, story and state; `{body}` is a complete pull request body in the repository's template.

## Rules every text here follows

- Where a text departs from a role prompt (`roles/coder.md`, `roles/reviewer.md`), it says which parts it replaces and that this holds for this goal only.
- An agent never marks its own work: the engine sets the review mark, Done and the commit links.
- A rejection, failure, warning or escalation is written down in full where the next reader looks: the reviewer's notes become a comment on the child, the builder's block reason becomes an incident (`factory wf incidents`).
- Agents reach the task manager only through `factory wf tsr`: `show`, `children`, `attachments`, `attachment`, `comment`, `status`.
