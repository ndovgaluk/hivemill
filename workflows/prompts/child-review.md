You are `{agent}`, reviewing ONE child of a story run. Goal `{goal}`, factory task `{task}`. You are in the builder's worktree; read, run and test there, change nothing.

This is not a pull request review. There is no pull request yet and none to look for. Do not run `factory verdict`, do not wait for CI, do not review other children. These instructions replace those parts of your role prompt for this one job.

Child: `{child}` (story `{story}`), review round {round} of {max_rounds}.
Commits to review, and only these (they are this child's own commits; other children's commits lie between them and are not yours to judge):

{commits}

The branch as it stands for your tests is at `{head_sha}`; this child's work started from `{base_sha}`.

{previous_findings}

Steps:

1. `factory wf tsr show {child}`: read the description, the acceptance criteria and the tests field. They are the contract. If it lists attachments that matter, save them with `factory wf tsr attachment <id> --out <file>`.
2. Read the builder's comment on the child (in the same output): what it says it changed and which checks it ran.
3. `git show <hash>` for each commit listed above, in order. Read every changed line and the code around it that the change depends on. Do not use `git diff {base_sha}..{head_sha}`: that range can contain other children's work.
4. Check, in this order, and stop adding findings of a lower kind once a higher kind fails:
   - each acceptance criterion: met by this diff, with evidence you ran or read yourself;
   - the tests the tests field asks for exist, test what they claim, and fail without the change where that can be shown;
   - correctness: errors handled, edge cases the description names, no change outside the child's scope;
   - the repository's own rules for code (the coder rules the builder follows).
5. Run the tests of this child and the affected tests: `python3 ci/affected.py --base {base_sha} --quick --run`. Quote the result.
6. In round 2 or later: first check each earlier finding is fixed or answered with evidence in the builder's comment, then look at what the fix changed. Do not raise new style points on code you passed before.
7. Write your notes to a file: for a pass, one line per acceptance criterion with its evidence and the test results; for changes, numbered findings, each with file and line, what is wrong, why it matters, and what would make it pass. No finding without a concrete failing case or a named criterion.
8. Finish with exactly one of:
   - `factory wf review {child} pass --notes <file>`
   - `factory wf review {child} changes --notes <file>`
   then `factory done "<child>: pass or changes, N findings"`.

Pass only what you would merge. Ask for changes only for things that must change: a missed criterion, a missing or empty test, a defect, a scope breach. Preferences are not findings.
