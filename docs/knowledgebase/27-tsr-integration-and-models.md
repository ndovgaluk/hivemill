# Built-in TSR integration (planned), model per role, Windows ↔ WSL folders

## Q: We'll need to add that optional integration with TSR. Create the detailed stories and tasks in both projects (both epics).

**Hivemill epic DVDG-539 → story DVDG-545** (L, complexity 4, batch B545, colour #8000ff, execution graph attached), off by default:
1. **DVDG-546** (M, c4): `goals.tsr_key` + `factory goal new/edit --tsr KEY`; config `tsr_sync` (0), `tsr_api_url` (`http://127.0.0.1:4000/api`), `tsr_token_file` (`~/.config/factory/tsr-token`: must be mode 0600, your own file, one `tsr_pat_…` line), `tsr_done_status` (In Review); token checks; **guard + role settings deny every agent reading the token** (reject + accept tests).
2. **DVDG-547** (M, c4): an outbox table filled with goal events; a tick step `tick_tsr_sync` pushes them to Taskosaur's REST API (`PATCH /tasks/{id}/status`, `POST /task-comments` with `externalKey`, `POST /task-commits`, `POST /notifications/messages`); at most 20 rows per tick, 10 s timeout, exponential backoff, one director alert after 5 failures; `factory tsr status|retry`; the token never appears anywhere. Blocked by DVDG-546 and **TSK-587**.
3. **DVDG-548** (S, c2): a "Factory goal G-…" external link on the TSR task, the TSR key on the factory's goal page, the boss prompt uses `--tsr`, `docs/tsr-sync.md`. Blocked by DVDG-547 and **TSK-588**.

**Taskosaur epic DVDG-16 → story TSK-586** (L, complexity 3, batch B586, colour #5023d5, graph attached). Checked first what Taskosaur already has: commit links are already idempotent (`@@unique([taskId, sha])`); every organization has an MCP-connector bot PAT (the token the factory should use). Missing:
1. **TSK-587** (M, c2): optional `externalKey` on `POST /task-comments`, unique per task; same key → 200 with the existing comment (no duplicate); race-safe; MCP `add_comment externalKey`.
2. **TSK-588** (M, c3): `TaskExternalLink` model, `PUT/GET/DELETE /tasks/{id}/external-links`, an "External links" block on the task page, MCP `link_external`, and `docs/automation-clients.md`. Blocked by TSK-587.

Cross-project links: DVDG-547 ← TSK-587, DVDG-548 ← TSK-588. Every child has its tests designed in its E2E tests field. Suggested split of work: the Hivemill story as factory goals (project hivemill), the Taskosaur story for your C1–C4 agents.

---

## Q: How to define which model is associated with each role?

Three levels (`~/factory/bin/factory_cli.py`, `docs/model-routing.md`):

1. **Default table `MODELS`** (in code): boss, director, lead, pm, reviewer, judge, staff-engineer, researcher → `claude-opus-5-5`; coder, qa, scout, retro, evaluator → `claude-sonnet-5-5`; cleaner → `claude-haiku-5-5`. Changing it is a code change (goal/PR) and reaches agents spawned afterwards.
2. **Config override `model_<role>`**: `role_model()` (line 9570) uses `factory config model_<role>` **only for keys that exist in `DEFAULT_CONFIG`**. Today only `model_cleaner` exists (`factory config model_cleaner claude-sonnet-5-5`, director or owner; validated; the next cleaner spawn uses it). Overrides for other roles would be a small factory goal: add `model_coder` etc. to `DEFAULT_CONFIG` with the same validation; `role_model()` already picks up any key that exists.
3. **Per spawn**: `factory spawn <role> --model …` (lead/director) sets it for that one agent; relaunches keep the agent's recorded model.

Related: `opus_effort` sets Claude's `--effort` (low | medium | high | xhigh | max) for Opus agents; the Cursor org has its own model map (`scout/orgs.py`: judgement vs build models). Each running agent's model shows in `factory agents` and on the web UI Agents page.

---

## Q: Can I open a Windows folder in WSL?

Yes, both ways:
- **Windows folder from Ubuntu:** Windows drives are mounted under `/mnt`: `cd /mnt/d/_DEV/Taskosaur`, `ls /mnt/c/Users/Dell`. In VS Code's WSL window: File → Open Folder → `/mnt/d/_DEV/...`. It works, but git and npm are slow there and file modes and locks behave differently, so repos the factory works on belong in `~/src`.
- **Ubuntu folder from Windows:** Explorer address bar `\\wsl$\Ubuntu\home\dell\src\hivemill` (pin it to Quick access), or in Ubuntu run `explorer.exe .` to open the current folder in Explorer; `code .` opens it in VS Code in WSL mode.

---

## Q: Also create the tasks in parallel in Taskosaur, so HM tasks are linked to TSR tasks: when the boss creates a goal, the tasks are created in TSR too, and every task move updates the TSR task.

Yes, and it happens **automatically, not by an agent** (the pm and coders have no TSR access): every `factory task add` or status change writes an outbox row, and the tick pushes it to TSR.

Added:
- **HM DVDG-549** (M, c4, wave 5, last): a project can be mapped to a TSR epic (`factory project update hivemill --tsr-epic DVDG-539`), so **every new goal becomes a TSR story** under it (or uses the item given with `--tsr`); **every factory task becomes a TSR task** `[T-0002] …` under that story, with the spec as description and links both ways; **status map**: todo → To Do, in_progress → In Progress, in_review → In Review, merged/done → `tsr_done_status` (In Review by default, you move to Done), blocked → comment, cancelled → comment + Done; rejections, merges (PR + SHA + commit link) and spec updates as comments; `factory tsr backfill G` for existing goals. Blocked by DVDG-548 and TSK-589.
- **Taskosaur TSK-589** (M, c3, wave 4, last): `POST /tasks` with an external link is idempotent per project (a retry returns the existing task), plus `GET /tasks/by-external?system=&key=&project=` and MCP support. Mirrored tasks use the "Synched" source with sourceName "Hivemill".

Re-rated both stories to **XL** (HM ≈ 5d2h human, Taskosaur ≈ 4d). Per the TSR rules for XL: a **grilling task DVDG-550** first (shared by both stories, with 8 open questions listed in DVDG-545: source of truth, auto-create stories, status mapping, which token, how much text to copy, backfill, failure policy, non-coder tasks) and a **feature guide** per story (`docs/tsr-sync.md`, `docs/automation-clients.md`). Waves shifted by one; new execution graphs v2 attached; story titles updated.

Final structure:
- HM DVDG-545: DVDG-550 (grilling) → DVDG-546 → DVDG-547 → DVDG-548 → DVDG-549.
- Taskosaur TSK-586: (DVDG-550) → TSK-587 → TSK-588 → TSK-589.
- Cross: TSK-587 → DVDG-547, TSK-588 → DVDG-548, TSK-589 → DVDG-549.

## "HM" = Hivemill
From now on "HM" means Hivemill (saved to memory).

## Q: The Factory should operate with TSR off. Would that be possible? Or is the current workflow based on tasks from TSR?

Answer of 2026-11-16 (Opus 5.5), read from the code at `1b54223` plus the uncommitted HM-45 chip change:

There are two workflows, and only the new one needs Taskosaur.

| Workflow | Input | Needs TSR? |
|---|---|---|
| Default (upstream): boss → director → lead → coder, one PR per factory task, reviewer + QA + judge | a goal as free text (`factory goal add`) | **No.** Nothing in `bin/factory_cli.py` calls Taskosaur. |
| Workflow engine (`factory-workflow`, DVDG-565 / HM-34, switch `workflow_engine`, default `off`) | one or more prepared TSR story keys (`factory wf start --story HM-12`) | **Yes.** It reads the story and children from TSR, and writes comments, the "reviewed by agent" mark, statuses and commit links back. Without `~/.config/factory/tsr-url` and `tsr-token`, a start is refused. |

So today the factory **does** run with TSR off, but only through the default (slow) workflow. The fast workflow is TSR-based by design: the owner decision of 2026-11-14 is that only TSR keys make a batch, and the engine never writes or splits a task itself (`docs/workflow-engine.md`).

What touches TSR when it is off:
- `workflow_engine off` (the default): nothing of the engine is built or run.
- HM-45 dashboard links: with `tsr_web_url` empty, the keys are plain chips. Goals that are not story runs show no key and no card.
- `roles/settings/*.json.in` only deny agents writes to a `.tsr` folder; harmless without TSR.
- The boss skill `story-run` is used only when the owner names TSR keys; free text goes to the director as before.

Making the fast workflow run without TSR is possible, and the code is shaped for it. The engine reaches TSR only through the `Tracker` interface in `go/internal/workflow/deps.go` (7 methods: `TaskByKey`, `Children`, `Comment`, `AgentCheck`, `Statuses`, `SetStatus`, `LinkCommit`), and the tests already stub it. A second, local tracker would need:
1. a source of stories without TSR, e.g. a story file in the repo, or stories and children kept in `factory.db` (new tables plus `factory story add`);
2. a local `Tracker` implementation (status, comments and checks as rows or events in the factory DB, so the dashboard shows them);
3. a config switch, e.g. `workflow_tracker = tsr | local`, so `wf start` picks the tracker;
4. the boss skill accepting a local story, and a dashboard view of local stories (owner rule: every feature trackable in the UI).

Not checked: the size of that change; it would be a new TSR task, sized by the planner.

## Q: How does it read from TSR and write? Does it use direct API interaction or MCP?

Answer of 2026-11-16 (Opus 5.5), read from `go/internal/tsr/` and `go/internal/workflow/` at `1b54223`:

**The direct REST API, not MCP.** Factory agents have no MCP, so the workflow engine (Go, `factory-workflow`) calls Taskosaur's HTTP API itself, through package `go/internal/tsr`.

- **Auth:** one personal access token (`tsr_pat_…`) of a Taskosaur *agent user*, sent as `Authorization: Bearer …`. Only agent users may set the "reviewed / tested by agent" marks.
- **Config:** two files that only the engine reads. Each must be mode 0600, not a symlink and one line, in a folder of mode 0700. On this box both exist, and the base is `http://localhost:4000/api` (the API; the web pages are on 4001):
  - `~/.config/factory/tsr-url`
  - `~/.config/factory/tsr-token`
- **Hardening:** 15 s timeout, at most 3 tries on a network error or a 5xx (never on a 4xx), redirects not followed. The token never appears in a message, log or event.
- **Agents never hold the token.** They go through `factory wf tsr …` subcommands, which the engine runs with the token, each allowed only for named roles.

| Call (`tsr.Client`) | HTTP | Used for |
|---|---|---|
| `TaskByKey` | `GET /tasks/key/{key}` | read a story or child at start; `wf tsr show` |
| `Children` | `GET /tasks?…` (paged) | the story's children, in board order |
| `Statuses` | `GET /task-statuses/project?projectId=…` | find the In Progress / In Review / Done status ids |
| `SetStatus` | `PATCH /tasks/{id}/status` | builder: In Progress / In Review (`wf tsr status`); engine: Done after the merge |
| `Comment` | `POST /task-comments` | builder / reviewer / QA comments (`wf tsr comment`); the engine's merge report |
| `AgentCheck` | `PATCH /tasks/{id}/agent-check` | the reviewer's "reviewed by agent" PASSED / FAILED, with the head commit it reviewed |
| `LinkCommit` | `POST /task-commits` | after the merge: each child's commits and the story's merge commit |
| `Attachments`, `AttachmentByID`, `Download` | `GET /task-attachments/task/{id}`, `GET /task-attachments/{id}`, `…/download` | agents read attached screenshots and files (`wf tsr attachments`, `wf tsr attachment ID --out PATH`) |

In order: **at start** the engine reads (story, children, statuses). **During the build** agents write through `factory wf tsr` (comments, In Progress / In Review), and the reviewer's result becomes an `AgentCheck` plus a comment. **After the merge** the engine links the commits, posts a report comment and sets every child and the story to Done.

Who else talks to Taskosaur:
- The **web dashboard**: never. HM-45 only builds links from `tsr_web_url` (the web address, e.g. `http://localhost:4001`).
- The **owner's Claude Code sessions** (like this one) use the Taskosaur **MCP** server (`mcp__tsr__*`). That is outside the factory.

## Q: do we need to care about DVDG-545?

Answer of 2026-11-16 (Opus 5.5 session). Mostly no. Its useful part was built another way; the rest only serves the old workflow, which is on hold.

**Built, under the workflow engine (DVDG-565 / HM-34) instead of DVDG-545:**
- Taskosaur is reached over the REST API by a Go client (`go/internal/tsr`), with no MCP client.
- The token sits in `~/.config/factory/tsr-url` and `tsr-token` (mode 0600, no symlinks). It belongs to an agent user, which matches the owner's decision of 2026-11-13 (a manager-level agent user with a personal access token).
- Agents never hold the token. They call `factory wf tsr …`, which is held to the caller's own run (`docs/workflow-engine.md`, "Taskosaur access").
- The engine reads a TSR story and its children and moves each child to In Review and then Done. It sets the "reviewed by agent" mark and links commits.
- The dashboard links a run's goal to its TSR story and children (HM-45).
- This is the "tight integration" the owner asked for in the DVDG-545 comments: TSR as the input and working surface.

**Not built, and only needed if the old boss/director/lead workflow comes back:**
- Mirroring old-workflow goals and factory tasks into TSR (`goals.tsr_key`, `projects.tsr_epic`, `tasks.tsr_key`).
- The `tsr_sync` switch, the outbox, `tick_tsr_sync`, `factory tsr status|retry|backfill` and `docs/tsr-sync.md`.
- None of the children DVDG-546…550 has a commit, and all are still To Do.

**Gap to check:** a grep of `roles/` and the Go guard found no worker-guard rule naming `tsr-token`. "Agents never hold the token" may rest on the token's location and the CLI alone. Not checked further.

**Recommendation:** close DVDG-545 and its children as superseded by DVDG-565, with a comment. Or park them until the old workflow is used again (owner decision of 2026-11-14: no slow workflow until HM-34 is done).
