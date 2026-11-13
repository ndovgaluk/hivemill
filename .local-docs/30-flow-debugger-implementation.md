# 30. Flow debugger: implementation instructions (story DVDG-551)

Written 2026-11-13. Collects the instructions and answers from the planning session, newest decisions first.
Nothing is implemented yet. Design canvas: https://claude.ai/artifact/Lz8XDieguNNapzzYH243tv (private).
Story: **DVDG-551** in Taskosaur (org Nick, project Dev, epic DVDG-539 Hivemill), batch `B551`, 13 children DVDG-552 to DVDG-564.

## Q: Give me the sequence of tasks for Opus 5.5, implemented sequentially without parallel subagents

The order respects every blocker link in Taskosaur.

| # | Task | What it is | Why here |
|---|---|---|---|
| 1 | DVDG-552 | Design grilling with you | Blocks everything; needs your answers, not just the agent |
| 2 | DVDG-553 | Flow data as JSON, with the `M`/`V`/`E` keys | Everything else reads this |
| 3 | DVDG-554 | React scaffold, committed bundle, shared selection | Foundation for all frontend tasks |
| 4 | DVDG-563 | Dev page with hot reload and Agentation | Early, so you can watch and annotate the rest as it is built |
| 5 | DVDG-555 | Tokens and cost per box and per step | The hardest task; doing it early surfaces any change to the data format before the views depend on it |
| 6 | DVDG-560 | Findings and Sequence phases | Completes the API |
| 7 | DVDG-556 | Diagram | |
| 8 | DVDG-557 | Timeline | |
| 9 | DVDG-558 | Summary bar and inspector | |
| 10 | DVDG-559 | Instruction viewer and dialogs | |
| 11 | DVDG-564 | Key chip and "Copy for investigation" | Needs the four views above |
| 12 | DVDG-561 | Mount on the goal and task pages, final bundle | Needs everything before it |
| 13 | DVDG-562 | Feature guide | Last; closes the story |

A prompt that does this in one go:

```
/working-with-taskosaur implement DVDG-551 in this order, one task at a time, no subagents:
DVDG-552, DVDG-553, DVDG-554, DVDG-563, DVDG-555, DVDG-560, DVDG-556, DVDG-557,
DVDG-558, DVDG-559, DVDG-564, DVDG-561, DVDG-562.
Read each task's comments before starting it; later comments override the description.
```

Things to settle or know before you start:

- **Comments carry corrections.** The key format (`M62`, `V12`), the diagram chip and the stable ids were added as comments on DVDG-553 and DVDG-564 after the descriptions were written. The story's description still shows the first version of the data format; the grilling task is where it gets updated.
- **Base branch.** The work builds on DVDG-544's branch `dvdg-544-task-flow` (PR #4, still unmerged, in the worktree `~/src/hivemill-dvdg544`). Either merge that PR first or tell the agent to branch from it.
- **Node in WSL.** It is not installed there; DVDG-554 installs it, which may need your approval.
- **Model fit.** DVDG-552 and DVDG-555 are rated as needing the strongest model. If Opus 5.5 finds DVDG-555 harder than it can settle, the task tells it to stop and comment instead of pushing on.
- **Two open confirmations.** The Agentation server registered at your user level (DVDG-563), and "send" meaning copy and paste (DVDG-564). The grilling is a natural place to confirm both.

The waves and lanes written on the story describe a parallel run; this sequence replaces them for a single agent.

## The eight open questions the grilling (DVDG-552) must settle

1. Does the old server-rendered SVG flow from DVDG-544 stay as a no-JavaScript fallback, or is it removed?
2. How are the Sequence tab's phases derived from real data (by task for a goal, by lifecycle stage for a task, or something else)? The mock's phases are hand-written.
3. Per-step cost rule when two events of one agent fall inside one model request, and for subagent logs.
4. Refresh: polling interval, and whether the 60 s full-page reload is switched off on these two pages.
5. Where the bundle-is-fresh check runs, given Node is not installed in the WSL clone and CI is Python only.
6. Whether browser-level tests are wanted (the repo has no browser test runner) or component tests plus Python tests are enough.
7. Which Markdown renderer the instruction viewer uses: a small bundled one like the mock's, or a library.
8. Node positions on the diagram: fixed layout as in the mock, or computed.

Not yet decided either: the React version, and how CSS is scoped (my suggestion: CSS Modules).

## Q: Should we add keys? (a chip or small icon to copy a reference the agent can interpret)

Yes to keys, but there is no need to invent or store new ones: the factory already has them for messages.

- **Messages already have keys.** The `factory` CLI names every message `M` plus its number (it prints `M15 → lead-g-001-a`), and the agents quote them in their own messages ("Ack M15", "M62 Q3"). In the live database, M15 is the director's "brief G-001" to the lead.
- **Verdicts and event-log rows get the same style:** `V12` and `E457`, built by the API from the row number. Nothing new is stored and the database schema stays as it is.
- **Goals and tasks keep their keys:** `G-001`, `T-0003`.

On the page, each step shows a chip with its short key and a small copy icon. One click copies a one-line reference that includes the task or goal:

| What you click | What lands on the clipboard |
|---|---|
| A step inside a task | `T-0003 M62` |
| A goal-level step | `G-001 M15` |
| A verdict | `T-0003 V12` |
| A box or an arrow | `G-001 box:coders`, `T-0003 arrow:gate-coders` |

Paste that line to the agent and it can find the exact record. The longer "Copy for investigation" block (who, when, title, link) stays as a second option and uses the same key. The page address uses it too, for example `?sel=V12`.

Recorded as comments on DVDG-553 (the API builds the keys) and DVDG-564 (the chip and copy icon).

## Q: An easy way to capture the event/action ID and send it for investigation, when debugging the diagram

Task **DVDG-564**, with a matching addition to the API task DVDG-553.

- **On the diagram itself:** whatever is selected (a box, an arrow, or the step currently animating along an arrow) shows a small chip with its id and a "Copy for investigation" button beside it. When you step with Prev/Next, the chip follows the current step. Pressing `c` with the diagram focused copies it too.
- **Everywhere else:** the same button is in the side panel, the instruction viewer, the events dialog and each Sequence item.
- **What gets copied:** the goal and task; the step's stable id and the database row behind it; who did what to whom, when, and the step's title; a link that reopens the page with that step selected.
- **Page address:** it always mirrors the current selection, so copying the browser's address also works.

Two choices to confirm:

- **"Send" means copy and paste.** The dashboard page does not post anything anywhere; a direct send would mean loosening the server's content security policy or adding a write endpoint to a read-only UI.
- **The copied block carries no instruction text**, only ids and facts, so it is safe to paste anywhere. The agent reads the full record from the database.

## Q: Add support for the Agentation feedback component

Task **DVDG-563**. It covers both the hot-reload development page and the Agentation toolbar, since the toolbar needs that page.

The toolbar will exist only on the Vite development page, not on the dashboard's goal and task pages. The dashboard's content security policy blocks the toolbar's connection to its local server, and the policy is not loosened for a development tool. The committed bundle stays free of it, and a test checks that.

On the development page you get:

- instant updates when a component changes;
- real goal and task data through a proxy to a running `factory serve`, or the sample data when no server is up;
- the Agentation toolbar, sending annotations to the coding agent.

Two choices to confirm:

- **Where the Agentation server is registered:** at your user level, not as a committed `.mcp.json` in the repo. Factory agents run Claude Code in checkouts of this repo, and a committed entry would be offered to every one of them.
- **Mode:** live sync to the agent by default, with copy-and-paste mode available through a setting.

Both Agentation packages are under the PolyForm Shield licence (source-available, no competing product), fine for personal development use.

## Q: Will there be hot reload on the React page?

Yes for development, with one limit: hot reload works on Vite's own dev page, not inside the Python-served dashboard page.

- **How you would work:** `npm run dev` in `web/flowapp/` starts Vite's dev server with hot module reload. Vite proxies `/api` to a running `factory serve`, so the dev page shows real goal and task data (or the fixture files when no server is running). The goal or task to show comes from the address, for example `?scope=goal&id=G-001`.
- **Why not inside the real page:** the dashboard page loads the committed bundle from `/static/flow/flow.js`. Hot reload there would mean loading scripts and a WebSocket from Vite's port, which the server's content security policy blocks.
- **Seeing a change on the real page:** run `npm run build` (or `vite build --watch` to rebuild on save) and refresh the browser.

## Q: Which tech stack for React? Backend, build engine, CSS framework, Vite?

| Layer | Choice | Status |
|---|---|---|
| Backend | The existing Python server (`factory serve`, standard library only) reading the SQLite DB read-only, plus two new JSON routes | Fixed in DVDG-553 |
| Runtime | No Node on the server: the built files are committed and served from `/static/flow/` | Owner's decision |
| Build | Vite, building to fixed file names (`flow.js`, `flow.css`, `manifest.json`) | Fixed in DVDG-554 |
| Language | TypeScript, strict | Fixed in DVDG-554 |
| UI | React, with React Flow (`@xyflow/react`) for the diagram | Owner's decision; the React version is not pinned yet |
| State | React context plus a reducer for the shared selection; no Redux or other state library | Fixed in DVDG-554 |
| Data loading | Plain `fetch` on an interval; no query library | Fixed in DVDG-554; the interval is a grilling question |
| Tests | Vitest and React Testing Library for components; Python `unittest` for the server side | Fixed; browser-level tests are a grilling question |
| Markdown | A small renderer of our own that builds React elements, or a library | Open, grilling question 7 |

**CSS: no framework.** Plain CSS files that use the colour and spacing variables already defined in the dashboard's `app.css`, so the page matches the other pages and follows the light/dark switch.

- The server's content security policy allows styles only from its own files. That rules out libraries that inject styles at run time (styled-components, Emotion) unless the policy is loosened.
- Tailwind would work, since it compiles at build time, but it would bring a second set of colours and spacing next to the existing tokens. Worth adding only if the whole UI is rebuilt in React.

## Q: Can we rebuild the entire UI in React?

Yes, technically. Not recommended now.

- **What it costs:** the web UI is nine page modules backed by 27 Python test modules. The tests were not opened; if most assert on rendered HTML, as the `test_web_detail.py` ones described in DVDG-544 do, they would need rewriting. The fork would also diverge from upstream on every page, making each `git merge upstream/main` harder.
- **What it buys:** little for most pages (an estimate). Going by their names (overview, lists, throughput, quality, tokens, changelog, resources) they look like read-only tables and charts, which the server-rendered UI already handles. The flow debugger is the page that needs rich interaction.
- **Instead:** let DVDG-551 prove the React setup (build, committed bundle, the content security policy, tests). After that, move one page at a time, and only where it needs interaction. Pages without a parameter already have a JSON route, which makes that path cheap.

## The story's task list (as created)

| Wave | Task | What it delivers |
|---|---|---|
| 1 | DVDG-552 | Design grilling with you; blocks everything else |
| 2 | DVDG-553 | Flow data for a goal or task as JSON |
| 2 | DVDG-554 | React app scaffold, committed bundle, shared selection |
| 3 | DVDG-555 | Tokens and cost per box and per step |
| 3 | DVDG-556 | Diagram |
| 3 | DVDG-557 | Timeline (Lanes and Sequence tabs) |
| 3 | DVDG-558 | Summary bar and inspector |
| 3 | DVDG-559 | Instruction viewer and dialogs |
| 3 | DVDG-563 | Dev page with hot reload and Agentation |
| 4 | DVDG-560 | Findings and Sequence phases |
| 4 | DVDG-564 | Key chip and "Copy for investigation" |
| 5 | DVDG-561 | Mount on both pages, live refresh, final bundle |
| 6 | DVDG-562 | Feature guide in `docs` |

- The story has the design file and the execution graph (third version) attached.
- The story builds on DVDG-544's unmerged branch; it is not linked as a blocker, because that would also block the grilling.
- The execution order for a parallel run is in comments on the story.

## The design concept (what the page is)

The page is a debugger with one selection shared by three linked views. Boxes on the diagram show work time and cost; arrows show the wait before a handoff, and a slow wait is drawn thicker and red.

| Depth | What you see |
|---|---|
| 1. Overview | Totals for time, tokens and cost, plus findings as clickable chips. The diagram shows time and cost per box and wait per arrow. The timeline has one lane per role. The side panel ranks where the time and the cost went. |
| 2. Box or arrow | Selecting one dims the rest and highlights its lanes and events on the timeline. The side panel shows its figures, agents and events. |
| 3. Event | The arrow animates in the message's direction and the sender pulses. A cursor marks the moment on the timeline. The side panel shows the message body with tokens and cost for that step. |

- **Diagram to timeline and back:** clicking a box, an arrow label or a timeline mark sets the same selection everywhere. "Prev event" and "Next event" replay the flow one step at a time.
- **Icons on the diagram:** numbered badges pulse on boxes with findings and open a dialog. A selected box gets two icons: expand its lanes on the timeline, or list its messages.
- **Zoom:** the diagram zooms and pans; the timeline zooms with the lane labels staying in place.
- **Instructions on a link:** clicking an arrow label opens a viewer with "From" and "To" cards (agent and role), the subject, time, tokens and cost, and the text rendered as Markdown; a list on the left steps through all instructions on that link. Rejection verdicts count as instructions on the rework arrow.
- **Cost:** a Time / Cost switch re-encodes the diagram by cost and marks the most expensive box; a selected box lists input, output, cache-read and cache-write tokens; every step shows its own tokens and cost.
- **Timeline tabs:** Lanes (bars per role, expandable to one row per agent) and Sequence (everything in order, grouped into phases).
- **Goal and task:** both use the same layout. At goal level a box sums a role across tasks; at task level it is one stage or attempt.

What the live data showed on 2026-11-13 (each is a finding the page should surface by itself):

- T-0003 was booked as queued for 2h 03m, 77% of its elapsed time.
- Attempt 1 of T-0003 had no "Coder started" event, so its coding time was unknown.
- PR #3 sat green with no reviewer or QA until the director nudged the lead.
- $1.45 of T-0003's $3.25 was not attributed to any role.
- $8.11 of the goal's $21.39 was goal overhead.

The design itself was never checked in a browser by the planning session; its logic ran under Node only.
