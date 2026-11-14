Next review in this story run, in the same session: you keep what you learned from the earlier children.

Child: `{child}` (story `{story}`), review round {round} of {max_rounds}.
Commits to review, and only these (this child's own commits):

{commits}

The branch as it stands for your tests is at `{head_sha}`; this child's work started from `{base_sha}`.

{previous_findings}

Same rules as before: this is not a pull request review, no `factory verdict`, no waiting for CI, change nothing. Follow the same eight steps as in your first review of this run: read the child (`factory wf tsr show {child}`), read the builder's comment, read each listed commit with `git show <hash>`, check criteria, tests, correctness and rules in that order, run `python3 ci/affected.py --base {base_sha} --quick --run`, write your notes to a file, and finish with exactly one of:

- `factory wf review {child} pass --notes <file>`
- `factory wf review {child} changes --notes <file>`

then `factory done "<child>: pass or changes, N findings"`.

What you know from earlier children helps you spot a contradiction between children; it is not a reason to re-review them. A problem you now see in an earlier child goes into your notes as a separate numbered point marked "earlier child <key>", and does not by itself fail this child.
