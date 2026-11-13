# Workflow: simple (draft)

For a task of size XS or S and complexity 1 or 2, with no children.

| Step | Who | What |
|---|---|---|
| 1 | code | preflight; pick this workflow, or take the owner's override |
| 2 | architect | readiness check: is the task enriched? If not (for example the owner gave the boss one sentence), read the code and write the task in Taskosaur: what to change, the files and places to change, acceptance criteria, how to verify. Ask the owner through the boss only for what the request leaves undecided and the code cannot answer. No design document, no split |
| 3 | builder | implement, test, run the checks, commit with the task key, comment, move the task to In Review |
| 4 | reviewer | review and run the tests in one pass; record the verdict |
| 5 | code | "changes requested": task back to In Progress, findings to the builder, then step 4 again with the same reviewer session |
| 6 | code | passed and checks green: merge queue, merge, Done in Taskosaur |

Limits: 5 fix rounds. After 2 rounds on the same kind of finding the architect is called before the third.

No separate QA and no audit.
