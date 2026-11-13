# Taskosaur (TSR) tasks, the boss, and screenshots

## Q: Can we reuse tasks created in TSR by forwarding them to the boss?

Yes. The boss is the one agent that can reach your TSR MCP server, so it can read a TSR task and turn it into a goal. A few things don't carry over automatically.

**Why it works:**
- The boss is started without the "no MCP" lock the other roles get (`bin/factory_cli.py:10411`), so it should load the `tsr` and `mts` servers you added to Claude Code in Ubuntu.
- Its settings file (`roles/settings/boss.json.in`) has no MCP block.
- Its prompt sends you only decisions like "new external services", so reading your own tracker is within its normal work.

**How to use it:** in the boss pane, write something like:
> Make a goal from TSR task DVDG-123 in project hivemill. Read it with the tsr tools: description, acceptance criteria and comments. Use its acceptance criteria as the success criteria and put the key DVDG-123 in the goal's intent.

**What doesn't carry over:**

| | |
|---|---|
| **No sync back** | The factory doesn't update TSR. If you want TSR updated, tell the boss to comment on the TSR task when the goal closes, or do it yourself |
| **TSR's split isn't reused** | A TSR story with children becomes **one goal**; the factory's pm makes its own plan |
| **One goal = one project** | The TSR task must map to a registered repo |
| **Attachments** | See below |
| **Your TSR rules don't apply** | Your `working-with-taskosaur` skill isn't loaded in factory agents |

**Not verified yet:** that the boss actually sees the `tsr` tools once it runs. Type `/mcp` in the boss pane.

---

## Q: Check the attachments point

I checked it, and the answer was **no**: the boss couldn't see screenshots attached to TSR tasks.

| Step (tested on DVDG-355, `card-button-hover.png`) | Result |
|---|---|
| List attachments: `api_request GET /task-attachments/task/{id}` | ✅ works through MCP. Returns `fileName`, `mimeType`, `id`, and a relative `viewUrl` |
| Download via that `viewUrl` (`curl {API origin}{viewUrl}`), from Ubuntu | ❌ **404**, also under `/api/` and `/uploads/` |
| The real route `GET /api/task-attachments/{id}/download` (`task-attachments.controller.ts:150`) | Needs a logged-in user, so a plain `curl` can't use it |
| Same route through MCP `api_request` (which is logged in) | ❌ Returns the PNG bytes **mangled as text** |
| Any Taskosaur MCP tool that returns an image | **None existed** |

Fix options: (1) add a `get_attachment` tool to the Taskosaur MCP server returning images as MCP image content — best, helps every agent; (2) give the boss a token for `curl` — no; (3) paste screenshots by hand.

---

## Q: We need to make the TSR MCP return images if requested (TSK-585)

I created **TSK-585** under the Taskosaur epic (DVDG-16) and implemented it.

**The new tool, `get_attachment`:**
- `get_attachment task=DVDG-355` lists the task's attachments with name, type, size and id.
- Adding `attachment=card-button-hover.png` (a file name or an id) returns that attachment:
  - **images** (png, jpeg, gif, webp) come back as image content, so the agent sees the screenshot like a pasted image;
  - **text files** (txt, md, csv, json, xml, svg, html) come back as text;
  - **other types** (PDF, Office) only get a description;
  - files over 5 MB are refused before downloading.
- It works on both the local (stdio) and the HTTP MCP server.

**Changes, in `D:\_DEV\Taskosaur\tools\taskosaur-mcp\`:**

| File | Change |
|---|---|
| `src/tools/files.ts` | The new tool |
| `src/client.ts` | `getBytes()` downloads raw bytes with the same login and 401-retry as other calls; `request()` now shares that path |
| `src/util.ts` | Tool results can now hold images |
| `src/registry.ts` | The in-app assistant is text-only, so it shows a short note instead of `undefined` for an image |
| `scripts/attachments.test.mjs` (new) + `package.json` | 8 tests against a fake API: list, image by name and by id (bytes match exactly), text, PDF, unknown name, duplicate name, over 5 MB |

Checks: typecheck exit 0, build exit 0, `npm test` 32/32.

**Live result:** after `npm run build:mcp --workspace=backend` and a backend restart, Claude in WSL read `card-button-hover.png` from DVDG-355 over the HTTP MCP and described it correctly without reading the task text (dark card, ▶ and "…" buttons, hand cursor on "…" with no hover outline, cut-off title "server (ngro…").

The TSR skill's "Reading attached screenshots" (`working-with-taskosaur/references/reading.md`) now says to use `get_attachment`.

**Committed:** `84b5450 feat(mcp): get_attachment returns task attachments, images as image content (TSK-585)` on local master (not pushed), linked, task Done; time logged 3m implementation + 1m commit (measured). Still open: re-bundle the Windows `taskosaur-agent` plugin, which ships its own copy of the server.
