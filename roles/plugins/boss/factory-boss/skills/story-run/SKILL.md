---
name: story-run
description: Boss steps to start, follow and unblock a story run of the workflow engine. Use when the owner names task-manager keys to pick up, build or implement (for example "pick up HM-12", "build in batch HM-12, HM-13"), asks about a run's progress, or a mail from the engine arrives (blocked, merged and Done).
---

# Story runs (boss)

Purpose: a story run builds prepared task-manager stories with one builder, a review per child and one pull request, with no team, lead or director. You start it and report on it; the engine does the rest.

Follow these steps in order.

1. Is it a story run? Yes when the owner names one or more task-manager keys to build. No when the owner gives work as free text: that is a normal goal for the director, as before. Never turn free text into a task yourself.
2. Is `factory config workflow_engine` set to `on`? If not, tell the owner that story runs are switched off (Settings page, "Workflow engine") and start nothing.
3. One key: `factory wf start --story <key>`. Add `--project <id>` when the owner names a factory project, and `--workflow <simple|medium|huge>` only when the owner names a workflow.
4. Several keys:
   - The owner said "as batch", "in batch", "as a batch" or "in one batch": one run for all of them, in the order given: `factory wf start --story <key> --story <key> ...`. Example: "For project taskosaur build in batch the following tasks T1, T2, T3" becomes `factory wf start --project taskosaur --story T1 --story T2 --story T3`.
   - No such words: one run per key, started one after another. Start the next only when the previous is merged, unless the owner says they may run together.
   - A batch takes keys only. If any item is free text, start nothing and say so: a batch needs prepared tasks; name the keys, or have the text written up as a task first.
5. If the start is refused, give the owner the engine's message as it is: which key, and what is missing (description, acceptance criteria, tests) or wrong (unknown project, key already in a run). Do not fill the gaps and do not retry with other arguments.
6. On success tell the owner: the goal id, the keys in order, the workflow, and that nothing merges until every child is built and reviewed and the one pull request has passed its checks.
7. Progress, when asked: `factory wf status --goal <id>`. Report children done out of total per story, the child in work, review rounds above one, and the pull request once it exists. Do not ask agents for status.
8. Mail "blocked": read `factory wf incidents --goal <id> --json` for the newest incident and tell the owner in plain words what stopped, on which child, and what decision is needed. After the owner decides: `factory wf resume --goal <id>`; add `--fresh-builder` only if the owner asks for a new builder.
9. Mail "merged and Done": tell the owner which stories are done and give the pull request address.

Stop and escalate:

- Never create a team, spawn a lead or ask the director for a goal started this way, and never message its builder or reviewer with instructions: the engine routes the work.
- Never run `factory wf start` for a key the owner did not name, and never change a task's text in the task manager.
- An engine error you cannot explain from the incident list goes to the owner as an escalation with the incident's summary.

Source: owner decisions of 2026-11-13 and 2026-11-14 (story runs, batches of prepared tasks only).
