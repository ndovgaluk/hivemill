# Forwarding TSR work to the boss, and syncing TSR

## Q: Give me a description I can forward to the boss; it'd be better if the factory workflow also moved the TSR tasks. Possible?

Yes, with one limit: only the **boss** can reach Taskosaur (the only agent with MCP). So the boss can keep TSR in sync at the **goal level**, if the request tells it to. Nothing in the factory does this automatically yet.

| | How | Reliability |
|---|---|---|
| **A. Ask the boss in the request (works now)** | The boss uses its `tsr` tools at fixed points: when the goal starts, when each PR merges (the director reports merges), when the goal closes | Best effort: the boss follows the instruction, no code enforces it |
| **B. Build it into the factory** | A goal records its TSR key; a tick step calls the Taskosaur API on goal events | Reliable; needs a token for the factory and outbound access from the tick → became story DVDG-545 (+ Taskosaur story TSK-586), see note 27 |

Before pasting: type `/mcp` in the boss pane and check `tsr` is connected.

Message to paste to the boss (two goals):

```
Two new goals for project hivemill, both defined in Taskosaur (TSR). Read them with the tsr tools
before creating the goals: get_task on each key, its children and comments, and get_attachment for
attached files (the story has an execution graph).

Goal 1 — TSR story DVDG-540 "Hivemill web UI: filter every page by project" (children DVDG-541,
DVDG-542, DVDG-543). A "Project" dropdown next to the Hivemill wordmark with "All" plus every
registered project; every page and metric filters by it. Take the shared contract, scope and
acceptance criteria from DVDG-540 and its children as the success criteria; the children's
"E2E tests" fields list the tests to write. Priority 2.

Goal 2 — TSR task DVDG-544 "Animated task-flow diagram on /task/{id} with DB notes as tooltips".
Server-rendered SVG + CSS animation (no new library; archify and Archscribe were evaluated and
rejected for the live page, see the task's comments). Take success criteria from DVDG-544.
Priority 2. Both goals change web/ (DVDG-544 touches web/views/tasks.py, as does Goal 1): let the
director order them or have the leads coordinate on shared files.

Keep TSR in sync (you are the only agent with TSR access):
1. When you create each goal: put the TSR key in its intent, move the TSR item to In Progress
   (for DVDG-540 also its children) and comment on it with the goal id ("Factory goal G-xxx").
2. When the director reports a merged PR for a goal: comment on the TSR item with the PR URL,
   the merge commit and what it delivered; for Goal 1 put it on the matching child
   (DVDG-541/542/543) and call link_commit with that child's key.
3. When a goal is closed: move its TSR items to In Review with a closing comment (what changed,
   PRs, how it was verified, anything left open), and send me a TSR message (send_message,
   kind: completed). I check and move them to Done myself.
Write TSR comments in plain English; never put local paths or tokens in TSR.
```

Notes:
- The boss makes one goal per item; the factory's pm re-plans each goal, so DVDG-540's children are input, not the factory's own task list.
- The boss stops at In Review: your TSR rules have you verify before Done, and the boss can't log measured working time the way those rules require.
- G-001 touches spawn/clean code, these touch `web/`: no file overlap; the director may still queue them behind G-001 for capacity.
