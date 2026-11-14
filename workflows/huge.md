# Workflow `huge`

For large or hard work: size L or XL, or complexity 4 or 5, or a story that already has children. Also the shape of a batch: several prepared stories in one run.

## What runs today

The run in [README.md](README.md):

- one builder session works every child in order, across all stories of the run, and keeps its context from child to child; if the session ends early the engine resumes the same session;
- each child is reviewed as soon as it is In Review, while the builder goes on with the next;
- a rejected child is fixed after the child in hand and before the next one starts; five rounds on one child stop the run for the owner;
- the pull request is opened once, when every child of every story is reviewed; the full checks run once;
- after the merge every child and every story is Done in the task manager, each story with its own closing comment.

A batch is started by the boss only for task-manager keys, all prepared beforehand; free text is never part of a batch.

## What is planned to differ

- **Architect (not built):** design, an attack on the design for the risky parts, and the split into self-contained children with their dependencies, following the task manager's own planning rules. Until then a story must arrive already split and prepared.
- **QA before the pull request (not built):** when all children are In Review and reviewed, QA tests the whole branch as one result, and its findings go to the builder like review findings. Today the factory's final gate does the testing after the pull request is open.
- **Architect on non-convergence (not built):** after two rounds on the same kind of finding the architect is asked before the third. Today the engine only counts rounds and stops at five.
- **Merge queue and conflicts (not built):** one merge at a time per project, open branches re-checked after every merge, conflicts resolved by the builder of the branch that has not merged. Today the factory's existing staleness and refresh rules apply to the one pull request.
