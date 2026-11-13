# Workflow: medium (draft)

For a task of size M, or complexity 3, with no children.

| Step | Who | What |
|---|---|---|
| 1 | code | preflight; pick this workflow, or take the owner's override |
| 2 | architect | readiness check. If the task is not enriched: write the design and its reasons, the files to touch, edge cases, acceptance criteria and how to verify into the task. No split. Then the task is frozen |
| 3 | builder | implement, test, run the checks, commit with the task key, comment, move the task to In Review |
| 4 | reviewer | review, run the tests and walk the acceptance list in one pass; record the verdict |
| 5 | code | "changes requested": task back to In Progress, findings to the builder, then step 4 again with the same reviewer session |
| 6 | code | passed and checks green: merge queue, merge, Done in Taskosaur |

Limits: 5 fix rounds. After 2 rounds on the same kind of finding the architect is called before the third.

A task that turns out larger than M while the architect reads it is re-rated and moved to `huge`.
