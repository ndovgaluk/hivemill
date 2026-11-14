---
name: story-builder
description: Rules for the one builder of a story run - several task-manager children built in order on one branch, reviewed child by child, one pull request at the end. Use when your kickoff or a mail says you are the builder of a story run, or names factory wf commands.
---

# Building a story run

Purpose: you build every child of the stories named in your kickoff, in order, in one session, on one branch. Your task's spec is only a pointer; the work is defined in the task manager.

In this goal these rules replace four habits of the coder prompt: no pull request per piece of work, no `factory prcheck` and no waiting for CI between children, no report to a lead (there is none), and `factory done` only at the very end.

Follow these steps in order.

1. Read the plan once: `factory wf tsr children <story>` for each story in your kickoff, in the order given. That order of children is your order of work. Finish every child of one story before the first child of the next.
2. For the next child: `factory wf tsr show <child>`. Read the description, the acceptance criteria and the tests field in full. If it lists attachments, `factory wf tsr attachments <child>` and save the ones you need with `factory wf tsr attachment <id> --out <file>`.
3. `factory wf tsr status <child> in_progress`.
4. Build this child and nothing else. Follow the coder prompt for how to write code and tests. Write the tests its tests field asks for.
5. Run the checks the child names, then the affected tests: `python3 ci/affected.py --base origin/main --quick --run`. Fix what fails.
6. Commit with the child's key at the end of the subject, for example `feat(area): what changed (HM-12)`. One child, one commit or one short run of commits. Never put two children in one commit: the reviewer reads a child by its commits.
7. Push the branch: `git push origin HEAD:<your branch>`, alone in its own call.
8. Write your report to a file and attach it: `factory wf tsr comment <child> --file <file>`. It holds what changed and why, the files, the commit hashes, each command you ran with its real result, and anything you did not do.
9. `factory wf tsr status <child> in_review`. Do not wait for the review. Go to step 10.
10. Run `factory inbox`. A mail that says a child needs changes comes first: read the findings on that child (`factory wf tsr show <child>`), fix them, commit with that child's key, push, comment, and set it `in_review` again. Then return to the next unbuilt child at step 2.
11. When every child of every story is `in_review` and your inbox has no findings, run `factory wf built`, then wait for mail. Keep checking `factory inbox` until the mail to open the pull request arrives; findings can still arrive before it.
12. Open the pull request only when that mail says so, once, for the whole branch, with the title and body it gives: `factory pr create --title <title> --body -`. Then `factory task update <task> --status in_review --pr <url>` and `factory done "<pull request url, children built, checks run>"`.

Stop and escalate:

- A child cannot be built as written (its description contradicts the code, a decision is missing, a blocker outside your reach): do not guess and do not redesign. Comment on the child with what you found, then `factory wf blocked <child> --reason "<one sentence>"`, and stop working until mail arrives.
- Never edit a child's description, acceptance criteria or tests. Never set a child to Done. Never open a pull request without the mail. Never start a child out of order because an earlier one looks hard.
- You are resumed in this same session if it ends early; a mail then tells you where you were. Your own comments on each child are the exact record: re-read them instead of trusting memory of early children.

Source: owner decisions of 2026-11-13 and 2026-11-14 on story runs (one builder, children in sequence, review per child, one pull request per story or batch).
