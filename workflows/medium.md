# Workflow `medium`

For normal feature work: size M, or complexity 3. One task or a story with a few children.

## What runs today

The run in [README.md](README.md), the same steps as `simple`: one builder, a review per child, fixes after the child in hand, one pull request, the factory's final checks and merge, then Done in the task manager.

## What is planned to differ

- **Architect (not built):** before the build, an architect on the strongest model reads the code and writes the design into the task: the contract, the files to touch, the edge cases, the acceptance criteria and the tests. Until that step exists the task must arrive prepared, written that way by whoever planned it.
- **Design freeze (not built):** once the build starts, a change to the design is a visible edit with a comment and pauses the builder. Today the builder's rule covers the builder's side only: it never edits a task's text, and it stops with `factory wf blocked` when the text cannot be built as written.
- **QA:** no separate QA step beyond what the factory's final gate already runs.
