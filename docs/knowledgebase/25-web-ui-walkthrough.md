# Web UI walkthrough (http://127.0.0.1:8765/)

Source: `~/factory/docs/web-ui.md` (section "Pages"), `web/views/`. Read-only, no login, refreshes every 60 s.
Filled in as we go through the UI together; each `## Q:` is one question from the walkthrough.

## Layout
Sidebar: **Work** (Overview, Goals, Tasks, Agents), **Insights** (Throughput, Quality, Tokens, Changelog),
**System** (Resources). Header: "Updated hh:mm", a health pill (worst first: Memory low, Usage cap reached,
Gate closed, Claude usage n%, …, All normal), a **"Needs you"** badge, the org filter (All · Claude · Cursor), theme.

| Page | What it shows | Mainly about which roles |
|---|---|---|
| `/` Overview | per org: boss/director running?, active teams, live workers, queued; then Needs you, System gauges, Open goals, Agents running, Shipped, Quality | boss, director, everyone |
| `/goals`, `/goal/{id}` | goals with status, priority, progress; one goal: blockers, success criteria met/open (linked to tasks), tasks by status, intent, teams, plan version, cost and time | boss (creates), director (staffs), pm (plan, audit) |
| `/tasks`, `/task/{id}` | every task: status, assignee, PR + CI state, rejections, cost, tokens, wall time; one task: lifecycle by stage, verdicts, per-agent cost, rework | pm (writes), coder, reviewer, qa, judge |
| `/agents` | running agents grouped by org and team, queued with reason, teams with lead state, ended | lead (spawns workers), director (staffing) |
| `/throughput` | merges per day, spawn→merge time, where time goes (coding, review/QA wait, judge, rework), slowest tasks, cost per merged PR | lead, director |
| `/quality` | rejections per merged PR, first-try merge rate, bouncing now, rejections by source (reviewer/QA/judge) and cause | reviewer, qa, judge, retro |
| `/tokens` | Claude usage, tokens and estimated cost by goal/task/agent/model | director (cost), you |
| `/changelog` | merged work by date or goal | judge (merges) |
| `/resources` | spawn gate, capacity (agents, memory, load, usage), queues, recent events, caps and config | director, the tick |

Costs are estimates at list prices (API-equivalent, not a bill). `/api/{page}.json` returns any page's data.

---

## Q: Where in the UI are the projects shown?

**Nowhere on the pages: the web UI has no Projects page, column or filter.** I checked the code: the goals query (`web/queries.py:167`) reads each goal's `project_id`, but no page in `web/views/` (overview, goals, tasks, agents, throughput, quality, tokens, changelog, resources) renders it. The only filter across pages is the **org** (Claude / Cursor), not the project.

Where you *can* see projects:
- **CLI:** `factory project list` (id, repo path, GitHub repo, base branch, auto-merge, required checks, gate settings); `factory goal show G-001` prints `project=hivemill` in its header; `factory goal list` per goal.
- **JSON:** `http://127.0.0.1:8765/api/goals.json` includes `project_id` for every goal (the data is there, the page just doesn't show it).
- **Indirectly in the UI:** a goal's tasks link to PRs on the project's GitHub repo, so the PR links show which repo it is.

With one project (hivemill) this doesn't matter. Once Taskosaur or MTS are registered, the Goals and Tasks pages would mix projects with no way to tell them apart at a glance. A small, safe **first-UI goal for the factory**: "Show each goal's project on /goals and /goal/{id}, add a project filter (like the org facet, `?project=`) to Goals and Tasks, and a /projects page listing `factory project list`; read-only, tests for each page."

---

## Q: We need to filter everything by project: a dropdown next to "Hivemill" with All + projects. Create an epic "Hivemill" under Dev (in TSR) and put the task there.

Created in Taskosaur (project Dev):
- **DVDG-539** epic "Hivemill".
- **DVDG-540** story (size L → split per the TSR rules), batch **B540**, colour `#ff8000`, execution graph `dvdg-540-execution-graph.svg` attached. Shared contract: `?project={id}` (whitelisted from the `projects` table, unknown = All, never echoed); dropdown "Project" next to the wordmark with "All" + each project, no JavaScript needed; kept on every link together with `?org=` (AND); goal/task/team/agent belong to a project through their goal; items without a goal (HQ agents) only under All; box capacity never filtered; project chip on Goals pages; `/api/{page}.json?project=`; `docs/web-ui.md` updated. Copies the org-filter pattern (`org_param`, `org_filter`, `_with_org`, `tests/test_web_orgs.py`).
  1. **DVDG-541** (wave 1, M, c2): dropdown, plumbing, Goals pages.
  2. **DVDG-542** (wave 2, M, c2): Overview, Tasks, Agents.
  3. **DVDG-543** (wave 3, M, c3): Throughput, Quality, Tokens, Changelog; Resources capacity stays shared.
  All three change `web/queries.py`, so they run in one lane, in sequence. Repo rule respected: no new `.py` files (tests go into existing `tests/test_web_*.py`).
- `.tsr` written to `~/src/hivemill` (Organisation=Nick, Project=Dev, EpicId=DVDG-539), not committed.

## Q: (+t) Show on a diagram the flow of the task, with notes from the DB as tooltips, where the task currently is; animate the current task/operation. Best library?

Created **DVDG-544** (M, c3) under the Hivemill epic.

**Recommendation: no library — server-rendered inline SVG + CSS animation.** The deciding facts:
- The web UI sends a strict CSP (`web/server.py:30`): `script-src 'self'; style-src 'self'` — no CDN, no inline scripts or styles. Its only JS is `web/static/theme.js`; its charts are already server-side SVG (`web/charts.py`).
- The task flow is a **fixed graph** (Planned → Coding → PR open → Review ∥ QA → Judge → Merged, loop Rejected → Coding, side states Blocked/Cancelled), so no auto-layout engine is needed.
- Data exists in the DB: `events` (ts, actor, action, detail), `verdicts` (role, verdict, summary), `messages` with task_id, `rejection_incidents`, task notes, live agents.
- Tooltips: SVG `<title>` + a CSS hover/focus card; animation: CSS `@keyframes` (pulsing current stage, "marching ants" on the active edge, only while a live agent works on it), off under `prefers-reduced-motion`.
- Mermaid injects inline styles (blocked by the CSP) and is ~3 MB; Cytoscape.js/D3/React Flow would bring the first JS dependency into a no-build, stdlib UI. Fallback if ever needed: vendor Cytoscape.js into `web/static/`.

## Q: Can we use archify (github.com/tt-a1i/archify, local at D:\_DEV\archify)?

Not for the live task page; yes for offline explainers.
- Archify is **an agent skill + zero-dependency Node CLI** (Node ≥18): an LLM writes a typed JSON IR (Architecture, Workflow, Sequence, Data Flow, **Lifecycle**, ERD, … modes), the CLI validates it and writes **one self-contained interactive HTML file** (plus PNG/PDF). Animation is a setting; details open in click panels.
- Verified in the local clone: its own preview server serves diagrams with `script-src 'unsafe-inline'; style-src 'unsafe-inline'` (`archify/bin/preview.mjs:458`); example outputs are ~845 KB each with 4 inline `<script>`, 2 `<style>`, 20–42 `style=` attributes and 1 external link (`archify/examples/lifecycle-agent-run.html`, `dataflow-product-analytics.html`).
- Hivemill's CSP blocks all of that; loosening it to `'unsafe-inline'` would weaken the whole dashboard. It would also need Node on the server per render and replace a page section that refreshes every 60 s.
- Good use: a one-off **lifecycle diagram of the factory** (roles, goal/task lifecycle) as a learning aid in `.local-docs`, using its `lifecycle.schema.json` mode.

---

## Q: Can we reuse Archscribe (github.com/lazypay/Archscribe, local D:\_DEV\Archscribe)?

**Not as a dependency, but yes as a source of ideas (and small code, MIT).**

What it is: a Codex/Claude **skill + Python CLI** (`scripts/render_animated_diagram.py --spec … --outdir …`). A JSON spec (layouts *panorama*, *swimlane*, *graph*; nodes, lanes, edges, animation) becomes `.excalidraw`, PNG, an **animated GIF**, MP4, and optionally an SVG (fonts embedded) and an interactive HTML page. MIT, young (9 commits, no release yet).

Why not as a dependency of the live task page:
- `scripts/svg_renderer.py` imports **Pillow** (`from PIL import Image`, line 43); its rich path launches Playwright + headless Chromium per render. Hivemill's UI is stdlib-only and renders per request.
- Its SVG carries a `<style>` block (base64 fonts) and its HTML inlines `<script>` and `<style>`; the UI's CSP (`script-src 'self'; style-src 'self'`) blocks both.
- It compiles a fixed spec into files in a batch run; a task's live state would need one pre-rendered image per stage.

What we can reuse:
- The **interaction design** of its HTML view: click a node to highlight it and its links (or the whole chain, BFS), hover tooltips, keyboard focus (tabindex + Enter/Space), and the CSS `@keyframes flowmove` dashed-edge animation.
- Under our CSP that works when the JS lives in a **same-origin file** (e.g. `web/static/flow.js`, allowed by `script-src 'self'`) and the CSS in `app.css`. Setting `element.style` from JavaScript (CSSOM) isn't blocked by `style-src 'self'`; only `style=` attributes written in the HTML are.
- So DVDG-544 stays "server-rendered SVG + CSS", with an optional extra step: a small `flow.js` adapted from Archscribe's interactive script for richer tooltips and click-to-trace, while the page still works without JavaScript. Copied code keeps Archscribe's MIT copyright notice.

Offline use: its animated GIF output suits a one-off **animated explainer of the factory flow** for learning (needs Pillow in a Python venv; Playwright optional).
