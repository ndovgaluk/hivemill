# Flow debugger

The Flow section of a goal page (`/goal/G-001`) and a task page (`/task/T-0003`) of the web UI is an interactive debugger for the agent workflow. It shows who worked on the goal or task, how long each step and each handoff took, what each step cost, which instructions went from one agent to another, and where the run went wrong. It is for the owner, looking back at a run or watching one live.

## 1. What it is

Three linked views share one selection:

```
 summary bar: totals + findings chips
┌──────────────────────────────────────────────┬───────────────┐
│ diagram: one box per role, arrows = handoffs │ inspector:    │
│ (time or cost on boxes, waits on arrows)     │ rankings, or  │
├──────────────────────────────────────────────┤ the selected  │
│ timeline: Lanes (one lane per role) or       │ box / arrow / │
│ Sequence (phases)                            │ step          │
└──────────────────────────────────────────────┴───────────────┘
```

- A **box** is work: a role (goal page) or a stage (task page) with its work time and cost.
- An **arrow** is a handoff: its label is the wait before it (queue before coding, PR before review) or the number of messages each way. A slow wait is drawn thicker and amber or red.
- Selecting anything (a box, an arrow, a timeline mark, a findings chip, a list row) selects it everywhere: the diagram dims the rest and animates the arrow of a selected step, the timeline highlights its lanes and puts a cursor at the step, the inspector shows its details.

The page is a small React app (`web/flowapp/`) built into committed files under `web/static/flow/`; it reads `/api/flow/goal/<id>.json` and `/api/flow/task/<id>.json`, built by `web/flow.py` (structure), `web/flowcost.py` (tokens and cost) and `web/flow_findings.py` (findings and phases). The server needs no Node.

## 2. Setup

Nothing to install to use it: `factory serve` serves the page and the committed bundle.

**Message text.** Instruction text (message bodies, specs, verdict summaries) is shown only when the owner switches it on and the server listens on a loopback address, because the UI has no authentication:

```
factory config serve_show_text 1
factory serve --bind 127.0.0.1
```

With text off, the debugger shows subjects only and says how to switch text on.

**Changing the app.** You need Node LTS (24 or newer worked; checked with v26.13.1 installed through `nvm` in WSL):

```
cd web/flowapp
npm ci
npm test
npm run typecheck
npm run build
```

`npm run build` writes `web/static/flow/flow.js`, `flow.css` and `manifest.json`; commit them with the source. `tests/test_web_flow_bundle.py` fails when the committed bundle no longer matches the source (the hash in `manifest.json`, computed by `web/flowbundle.py`). For hot reload and the Agentation feedback toolbar use the development page: see "Development page" in [web-ui.md](web-ui.md).

## 3. How to use it

- **Summary bar:** Elapsed, Agent time, Longest wait, Rejections, Tokens, Cost (est.), and the findings as chips; a chip selects what it is about. Clicking the Longest wait value selects the arrow with that wait; clicking Rejections opens the list of failing reviewer, QA and judge verdicts, with the picked one's details on the right (as in a box's **Messages and events**).
- **Review gate:** a dashed frame labelled "Review gate" holds two boxes, **Reviewer** above **QA**: every actor has its own box, also when they work as one step. Each box has its own state, time, cost and findings, so after a rejection the red box shows which role rejected; the review, verdict and rework arrows start or end on the frame.
- **Boxes:** name, state dot (green done, blue live and blinking, red failed, grey idle, dashed pending), work time and cost, a share bar. A numbered badge counts the findings on the box; it opens the findings list. A selected box shows **Expand on timeline** and **Messages and events**.
- **Share bar** (the strip along the bottom of a box): how much of the whole run the box accounts for; its width is the box's value divided by the run's total.
  - Time view (blue): the box's work time divided by the elapsed time of the run, from its first event to its last. A nearly full Coders bar means coders were working for almost the whole run.
  - Cost view (amber): the box's estimated cost divided by the run's total cost.
  - Red: the box's last session ended in FAIL (either view).
  - It stops at 100%: agents of one box can work in parallel, so a box's work time can exceed the elapsed time; the bar is then full. No bar: the value is unknown (for example, cost not recorded) or zero.
- **Arrows:** click the label chip to select the arrow; if it carries instructions, the **instruction viewer** opens: the list of that link's instructions on the left, and for the chosen one the **From** and **To** cards (agent and role), subject, time, tokens and cost, and the text. **Show on diagram and timeline** closes it and keeps the step selected.
- **Time / Cost:** switches the main value of every box; in the Cost view the most expensive box gets an amber border.
- **Zoom:** **Ctrl** + wheel (or a trackpad pinch) or **+** / **−**; a plain wheel scrolls the page (50 to 200%), **Fit** goes back to 100%; drag to pan.
- **Timeline, Lanes:** one lane per role with work bars, hatched waits, red bars for a run that ended in a failing verdict, and a mark per step (dot message, square status, circle verdict). Clicking a mark selects the step and opens **Quick info** next to it: the mark type and what its shape and colour mean (grey normal, amber needs attention, red failure or rejection, green passing verdict), the title, From → To, time, tokens and cost; Esc, Close or a click outside closes it. A lane label selects the role and opens one row per agent. **Prev event** / **Next event** step through all steps in time order ("12 / 116"). Zoom 1x to 8x keeps the labels in place.
- **Timeline, Sequence:** the run grouped into phases: on a goal, "Goal setup", one phase per task, "Wrap-up"; on a task, Spec, Coding attempt N, Review and QA attempt N, Merge. Each phase shows its failed, passed and to-check counts and a summary; a long silence before a phase is noted.
- **Inspector:** with nothing selected, "Where the time went" and "Where the cost went"; a box shows its figures, its input, output, cache-read and cache-write tokens, its agents (on a goal page with **Open task flow** to the task's own page) and its steps; a step shows route, time, its own tokens and cost, its text, and "Around this event".
- **Copy for investigation:** every selected item has a key chip (`M62` a message, `V12` a verdict, `E457` an event-log row, `S-T-0003` a task's spec, `box:coders`, `arrow:rw`) and a **Copy for investigation** button; `c` on the focused diagram does the same. Paste it into a coding agent's chat: it names the database row and holds a link that reopens the page with that item selected. It never contains message text.
- The page address keeps the selection, the timeline tab and the lens (`?sel=V12&tab=lanes&lens=cost`), so a link reopens the same view. The view refreshes every 30 seconds while the tab is visible and keeps the selection.

## 4. How to check it

On demo data, without touching your factory home:

```
export TRIAL=$(mktemp -d)
python3 ci/demo_seed.py --home "$TRIAL/demo" --now 2026-10-25T12:00:00+01:00
HOME=$TRIAL/demo/home FACTORY_HOME=$TRIAL/demo bin/factory serve --bind 127.0.0.1 --port 18624
```

Open `http://127.0.0.1:18624/goal/G-009` and `http://127.0.0.1:18624/task/T-0091`. A correct result: the debugger fills the content width, the browser console shows no Content Security Policy error, Next event moves the cursor and the address shows `?sel=…`, the chips under the totals name the long queue and the rejections.

Tests:

```
python3 -m unittest tests.test_web_flow_api tests.test_web_flow_cost tests.test_web_flow_findings tests.test_web_flow_bundle tests.test_web_detail
cd web/flowapp && npm test
```

## 5. Troubleshooting and limits

| What you see | Cause | Fix |
|---|---|---|
| "Flow data could not be loaded (HTTP 404)" | the goal or task does not exist | check the id |
| "Message text is hidden. Set serve_show_text=1 and bind to loopback to show it." | text is off, or the server is bound to a LAN address | `factory config serve_show_text 1` and `--bind 127.0.0.1` |
| Cost shows "unknown", note "token index not ready yet" | the token index is still on its first scan after a server start | wait a minute and let the page refresh |
| "no session log found for coder-…" | the agent's Claude Code log is not in the projects dir (another machine, deleted, never attributed) | none; the value stays unknown |
| "Cursor agents record no token usage" | the agent ran on Cursor | none |
| "session log larger than the read cap" | one log file is over 64 MB | values for that agent stay unknown |
| "That item is not in this flow any more" | a link names a step that is gone | pick the step again |
| The old static diagram shows and nothing reacts | JavaScript is off, or the bundle did not load | check `/static/flow/flow.js` loads; rebuild if the bundle test fails |

Limits worth knowing:

- **Unknown is never zero.** A missing start event, an unreadable log or an unpriced model makes a value unknown, with the reason in a tooltip or note.
- **Per-step cost** splits each agent session by time: a model request belongs to the first step the agent made at or after it (anywhere in the factory, not only on this page); requests after the agent's last step are its "after last event" share. One request is never split. The sums add up to the session's total.
- **Respawned agents:** the factory keeps one row per agent name, so an earlier session of a respawned agent may be attributed to no agent and count as unattributed (the "not attributed to any agent" finding).
- **Goal-level agents on a task page:** the lead's box shows its whole session time, but its cost counts only its steps on this task.
- Agent time counts the sessions the event log records (spawn to done or reaped); a session without an end event is unknown.

## 6. Implementation report (story DVDG-551, 2026-11-13)

Decisions (grilling DVDG-552, owner accepted all): stack on the DVDG-544 branch; keep the old SVG flow as the no-JavaScript fallback; phases as in section 3; the per-step cost rule above; poll every 30 s with the 60 s page reload off on these two pages; a source hash plus a Python test for bundle freshness (no Node in CI); Vitest and Python tests, no browser runner; the server renders Markdown (`md()` → `body_html`); fixed layout; React 19, React Flow 12, CSS Modules on the existing colour variables; Agentation registered at user level; "send" means copy.

| Task | Delivered |
|---|---|
| DVDG-552 | Grilling: 13 decisions recorded on the story |
| DVDG-553 | `web/flow.py` and the two JSON routes: nodes, edges with waits, lanes from every session, events with stable keys and row references |
| DVDG-554 | React scaffold, selection store, data hook, committed bundle, `web/flowbundle.py` hash and freshness test |
| DVDG-563 | Development page with hot reload, API proxy, fixtures and the Agentation toolbar (development only) |
| DVDG-555 | `web/flowcost.py`: tokens and cost per step, agent, box and total from the session logs, cached per file |
| DVDG-560 | `web/flow_findings.py`: six findings and the Sequence phases |
| DVDG-556 | Diagram: boxes, arrows, wait chips, badges, lens, zoom, toolbar |
| DVDG-557 | Timeline: Lanes and Sequence tabs |
| DVDG-558 | Summary bar, findings chips, inspector |
| DVDG-559 | Instruction viewer, findings and events dialogs |
| DVDG-564 | Key chips, Copy for investigation, the address mirroring the view |
| DVDG-561 | Mount on both pages at full width, no page reload there, final bundle, manual check |

Findings worth knowing, from the live goal G-001 that motivated the story: 8 rejections with T-0003 still open; T-0005 queued 6h 27m (98% of elapsed); $18.94 of $31.68 not attributed to any agent; T-0003's PR waited 3h 24m without a reviewer until the director nudged the lead; T-0001 has no recorded coder start.

Test results as run on 2026-11-13: Vitest 10 files, 69 tests passed; the web, flow, token, scrub and hygiene Python modules, 283 tests, passed. The full suite was left to CI (on this stacked branch `ci/affected.py --quick` asks for the full run).

Left open: the browser-to-agent round trip of the Agentation toolbar (needs the user-scope MCP registration); drag-pan and the arrow animation were checked in tests, not by hand.
