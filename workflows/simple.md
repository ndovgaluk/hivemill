# Workflow `simple`

For a small, clear piece of work: size XS or S and complexity 1 or 2. Typically one task with no children; the engine treats it as a story with one child.

## What runs today

The run in [README.md](README.md): one builder builds the task, one reviewer checks its commits, the builder fixes findings (at most 5 rounds), one pull request, the factory's final checks and merge, then Done in the task manager.

## What is planned to differ

- **Architect:** none. A task that is not prepared is refused at the start; it is never enriched on the fly.
- **Final review:** for this workflow the per-child review and the final pull request review look at the same single change. The final review may later be reduced to the tests and the merge checks, once real runs show it finds nothing the first review missed. Not built; today both run.
- **QA:** no separate QA step beyond what the factory's final gate already runs.
