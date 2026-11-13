# Workflow: huge (draft)

For a task of size L or XL, or complexity 4 or 5, or a task that already has children. The unit of work is a story with child tasks; one branch and one PR per story.

| Step | Who | What |
|---|---|---|
| 1 | code | preflight; pick this workflow, or take the owner's override |
| 2 | architect | readiness check. If the story is enriched (children exist and each is complete), go to step 5 |
| 3 | architect | design in the story: approach and reasons, contract, files and areas touched, risks. For changes to spawn, clean, isolation, the guard or the merge gate: have a second session attack the design, and fold the result in |
| 4 | architect | split into children the way the `working-with-taskosaur` skill does: each of size M or smaller and self-contained (goal, context, contract, files, acceptance, how to verify), with dependencies and an order |
| 5 | code | freeze the story and its children; check the files against other open stories of the project (overlap → this story waits) |
| 6 | builder | one child at a time, in order: implement, test, run the checks, commit with the child's key, comment, move the child to In Review; then the next child |
| 7 | reviewer | for each child as it reaches In Review, while the builder goes on: review that child's commits, run its tests, record the verdict |
| 8 | code | "changes requested": the child goes back to In Progress; the builder fixes it after the child it is on and before starting the next; the same reviewer session re-checks |
| 9 | qa | when all children are In Review and reviewed: test the whole branch against the story's acceptance criteria |
| 10 | code | QA failed: the affected children go back to In Progress, findings to the builder, then steps 7 and 9 again for what changed |
| 11 | code | reviewed, tested, checks green: merge queue, one merge, every child and the story Done in Taskosaur |
| 12 | architect | audit: each success criterion against evidence; gaps become follow-up tasks |

Limits: 5 fix rounds per child. After 2 rounds on the same kind of finding the architect is called before the third.

Conflicts with another merge: the builder of this story resolves them between two children, using the merged task's design; the reviewer re-checks the affected children only.
