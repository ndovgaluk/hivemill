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
