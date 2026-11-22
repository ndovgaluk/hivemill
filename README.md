<a id="readme-top"></a>

<!-- README media slots. Each SLOT marker names a block that T-0480 (new screenshots) or T-0708 (video v2) swaps by
     changing only the file path or URL inside it, never the surrounding layout. See docs/readme-media.md. -->

<p align="center"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/wordmark-dark.svg"><img src="docs/images/wordmark-light.svg" alt="Hivemill" height="72"></picture></p>

<h3 align="center">Hivemill is a self-hosted software factory of AI coding agents (Claude Code and Cursor),<br>with separate review, QA and a judge that decides the merge.</h3>

<p align="center">
  <a href="https://github.com/volekerb/hivemill/actions/workflows/tests.yml"><img src="https://github.com/volekerb/hivemill/actions/workflows/tests.yml/badge.svg?branch=main&event=push" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT"></a>
  <a href="docs/SETUP.md"><img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python 3.11+"></a>
  <a href="docs/go-toolchain.md"><img src="https://img.shields.io/badge/go-guard-00ADD8.svg" alt="Go (worker guard)"></a>
  <a href="https://github.com/volekerb/hivemill/releases"><img src="https://img.shields.io/github/v/release/volekerb/hivemill?include_prereleases&sort=semver" alt="Release"></a>
</p>

<p align="center">
  <a href="#quickstart"><b>Quickstart</b></a> ·
  <a href="docs/README.md">Docs</a> ·
  <a href="docs/examples/README.md">Examples</a> ·
  <a href="docs/adopt/ADOPT.md">Adopt with Claude</a> ·
  <a href="SECURITY.md">Security</a> ·
  <a href="https://github.com/volekerb/hivemill/discussions">Discussions</a>
</p>

<!-- SLOT:VIDEO (T-0708): replace only the bare user-attachments URL on the next line and keep the links below it. -->
https://github.com/user-attachments/assets/dfec91f4-de05-4592-aaec-3662ce674c4a

<p align="center"><a href="docs/demo/README.md">how it was made</a> · seeded demo data only</p>

<!-- SLOT:HERO (T-0480): one big screenshot. Swap the two paths (light in img src, dark in source srcset) and the alt text. -->
<p align="center">
  <a href="docs/images/home-light.png"><picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/images/home-dark.png">
    <img src="docs/images/home-light.png" width="860" alt="The overview page of the web UI: live agents, open PRs, goals, items waiting on the owner and usage">
  </picture></a>
</p>

## Where you run and watch it

| Surface | What it is | Status in v0.5.0 |
|---|---|---|
| herdr-core (`hc`) | The headless core of herdr. Hivemill runs its agent panes through it. | The default backend: `terminal_backend = auto` prefers `hc` when both binaries are installed. See [docs/terminal-backends.md](docs/terminal-backends.md). |
| Classic herdr terminal UI | The herdr TUI you attach to and watch panes in. | Still supported, opt-in: set `terminal_backend = herdr`. |
| Herdr desktop app plugin | The Hivemill dashboard: a status bar and a dashboard tab in the Herdr desktop app, installed with `/hivemill:setup`. | Available. See [Herdr desktop dashboard](#herdr-desktop-dashboard). |
| Web view | `factory serve`: the web UI with goals, agents, cost and throughput. | Available. See [The web UI](#the-web-ui). |

## What you get

You describe what you want built to one boss agent. A director staffs a team, and a chain of coders, QA, reviewers and a judge ships it as pull requests. The agent that writes a change never reviews, tests or merges it. Hivemill's CLI is `factory`.

<table>
  <tr>
    <td width="33%"><b>Fixed roles</b><br>Each role has its own prompt and permissions, enforced by hooks rather than by trust.</td>
    <td width="33%"><b>Independent review</b><br>A separate reviewer and QA check every pull request against a real test run.</td>
    <td width="33%"><b>A judge merges</b><br>Only on passing reviewer and QA verdicts. Anything else goes back with findings.</td>
  </tr>
  <tr>
    <td><b>One source of truth</b><br>Goals, tasks, messages and verdicts are rows in SQLite with an append-only log.</td>
    <td colspan="2"><b>Small-box friendly</b><br>A spawn gate queues agents until RAM, load and Claude process count allow.</td>
  </tr>
  <tr>
    <td><b>Two runtimes, side by side</b><br>A Claude org and a Cursor org, each a full chain of command, share one box and one DB (<a href="docs/runtimes.md">runtimes</a>).</td>
    <td><b>A read-only web UI</b><br>Goals, agents, throughput, quality, and cost, tokens and wall time per task, in light and dark.</td>
    <td><b>Opt-in containment</b><br>A worker guard on every tool call, an optional sandbox, a GitHub token per worker role and optional per-task clones (<a href="docs/worker-guard.md">guard</a>, <a href="docs/worker-sandbox.md">sandbox</a>).</td>
  </tr>
</table>

## One change, five steps

1. **You ask.** Describe what you want to the boss. It becomes a goal with success criteria.
2. **A team forms.** A director staffs a lead, who plans tasks. Each task gets its own worktree and branch.
3. **A coder builds.** It opens a pull request and stops. It cannot merge or review.
4. **Two others check.** A reviewer reads the diff. QA runs the tests against the acceptance criteria.
5. **A judge decides.** Both pass, it merges. Either fails, it goes back with findings. Every verdict is stored.

The roles and the merge gate as diagrams are under [How it works](#how-it-works).

The factory runs on [herdr](https://herdr.dev), the terminal multiplexer that hosts the agent panes ([source](https://github.com/herdrdev/herdr), pinned release [v0.9.5](https://github.com/herdrdev/herdr/releases/tag/v0.9.5)).

## Quickstart

### Install

Needs a fresh Debian or Ubuntu machine and a logged-in Claude Code (the Cursor org also needs the Cursor Agent CLI, see [docs/runtimes.md](docs/runtimes.md)). In Claude Code:

```
/plugin marketplace add volekerb/hivemill
/plugin install hivemill
/hivemill:setup
```

The full guide, with the installer options and the manual steps, is [docs/SETUP.md](docs/SETUP.md).

### Look around without installing

Seeded fictional data, nothing real runs ([docs/demo-data.md](docs/demo-data.md)). Run from the repository root:

```
export TRIAL=$(mktemp -d)
python3 ci/demo_seed.py --home "$TRIAL/demo" --now 2026-10-25T12:00:00+01:00
HOME=$TRIAL/demo/home FACTORY_HOME=$TRIAL/demo bin/factory serve --bind 127.0.0.1 --port 18624
```

Open <http://127.0.0.1:18624/> to see the read-only web UI on the demo data. In another shell, put `HOME=$TRIAL/demo/home FACTORY_HOME=$TRIAL/demo` in front of `factory goal list` to see the demo goals as a table.

## A task's life in commands

Three walkthroughs with full output on the demo data: [from a goal to a merged PR](docs/examples/01-goal-to-merged-pr.md), [handling a rejection](docs/examples/02-handling-a-rejection.md), [the digest and scorecard](docs/examples/03-digest-and-scorecard.md).

## How it works

- **Separation of roles.** Each role has its own prompt and its own permission settings, enforced by hooks rather than by trust.
- **Two orgs, one box.** An org is a complete chain of command (boss, director, leads, workers) on one runtime and one model map: `claude` (Claude Code, the default) and `cursor` (Cursor Agent). Each goal belongs to one org, every spawn inherits it, and both orgs share one agent cap and one resource gate ([docs/runtimes.md](docs/runtimes.md)).
- **Evidence over claims.** A task is done when a reviewer and QA have checked the PR diff and a real test run, not when an agent says so.
- **Resource-aware on a small box.** A spawn gate watches RAM, load and the number of Claude processes, and queues new agents until there is room. The whole factory runs on one modest VM.
- **Contained workers.** A worker guard hook blocks actions outside a role's job. Opt-in extras: the worker sandbox (`sandbox_roles`), a worker GitHub token per role (`worker_gh_roles`) and a standalone clone per coder task instead of a worktree (`task_clones`, off by default; [docs/git-hardening.md](docs/git-hardening.md)). The guard is Python by default; a Go port is available through `guard_impl` ([docs/worker-guard-go.md](docs/worker-guard-go.md)), about 8 ms against about 69 ms per call. A Go build of the `factory` CLI is opt-in through `cli_impl`, `factory schedule` runs only in Go, and Python stays the default ([docs/cli-go.md](docs/cli-go.md), [docs/schedule.md](docs/schedule.md)).
- **Everything auditable.** Goals, plans, tasks, messages, verdicts and decisions are rows in SQLite with an append-only event log, exported to readable markdown every minute.

```mermaid
flowchart TB
    owner([owner]) <--> boss
    boss <--> director
    director <--> lead["team leads (lead)"]
    lead --> pm
    lead --> coder
    lead --> qa
    lead --> reviewer
    lead --> judge
    director --> cleaner

    subgraph infra [Infrastructure]
        direction LR
        tick["tick (systemd timer, every minute)"]
        herdr["herdr panes (one per agent)"]
        db[("SQLite DB + factory CLI")]
        web["web UI (read-only)"]
    end

    tick -->|"reap, spawn, nudge, export"| herdr
    herdr -->|"hosts every agent"| boss
    boss -.->|"factory CLI"| db
    director -.->|"factory CLI"| db
    lead -.->|"factory CLI"| db
    db --> web
    tick --> db
```

The merge gate, for every change:

```mermaid
flowchart LR
    coder["coder opens PR"] --> reviewer["reviewer: diff verdict"]
    coder --> qa["qa: test and acceptance verdict"]
    reviewer --> judge{"judge"}
    qa --> judge
    judge -->|"both pass"| merge["merge to main"]
    judge -->|"any fail"| retry["back to coder with findings"]
    merge --> cleaner["cleaner removes worktree and branch"]
```

Details: [docs/lifecycle.md](docs/lifecycle.md), [docs/verdict-gates.md](docs/verdict-gates.md), [docs/db-layout.md](docs/db-layout.md).

### What the application is made of

Python 3.11+ and the standard library only: nothing to `pip install`. Go is used only for optional ports (the worker guard, the CLI). Linux only (on Windows, inside WSL2).

| Part | Where | What it does |
|---|---|---|
| `factory` CLI | `bin/factory` (a stub) and `bin/factory_cli.py` | Every command: goals, tasks, messages, verdicts, spawn, judge, config, export, `serve`. Agents and the owner work only through it ([cli-layout](docs/cli-layout.md)). |
| State | `$FACTORY_HOME/db/factory.db` (default `~/factory`) | One SQLite file: goals, plans, tasks, agents, messages, verdicts and an append-only event log. Only `factory init` creates it; the path is resolved in `web/dbpath.py` ([db-layout](docs/db-layout.md)). |
| Heartbeat | `systemd/factory-tick.timer` → `factory tick` | Every minute: reap ended agents, spawn behind the resource gate, nudge idle ones, export state ([spawn-queue](docs/spawn-queue.md)). |
| Roles | `roles/<role>.md`, `roles/settings/`, `roles/plugins/`, `roles/hooks/` | The prompt, permissions, skills and the PreToolUse worker guard of each role ([worker-guard](docs/worker-guard.md)). |
| Agent panes | herdr / herdr-core (`hc`) | One terminal pane per agent, a Claude Code or Cursor Agent session ([terminal-backends](docs/terminal-backends.md)). |
| Sandboxing and scouting | `scout/` | Orgs and runtimes, the optional worker sandbox, per-role GitHub tokens, the skill scout ([runtimes](docs/runtimes.md), [worker-sandbox](docs/worker-sandbox.md)). |
| Web UI | `web/` | The dashboard served by `factory serve`, described under [The web UI](#the-web-ui). |
| CI tooling | `ci/` | Test selection, sharding, the test-count gate, guard corpus and the public-text scanners ([tests-and-ci](docs/tests-and-ci.md)). |
| Installer plugin | `plugins/hivemill/` | The Claude Code plugin behind `/hivemill:setup` ([SETUP](docs/SETUP.md)). |

## Features

| Feature | What it does | Docs |
|---|---|---|
| **Run it** | | |
| Setup and operations | Install, boot units, reboot recovery, identity rules | [SETUP](docs/SETUP.md), [operations](docs/operations.md) |
| Adopt with Claude | An instruction file your own Claude Code follows to install it | [ADOPT](docs/adopt/ADOPT.md) |
| **Ship safely** | | |
| Verdict gates | The judge merges only on passing reviewer and QA verdicts | [verdict-gates](docs/verdict-gates.md) |
| Goal lifecycle | From request to goal to done, with plan and success criteria | [goal-lifecycle](docs/goal-lifecycle.md) |
| **Contain agents** | | |
| Worker guard | Hooks that block actions outside a role's job | [worker-guard](docs/worker-guard.md) |
| Worker sandbox | Opt-in namespaced spawn and worker GitHub tokens, with known limits | [worker-sandbox](docs/worker-sandbox.md) |
| Per-task clones | Optional standalone clone per coder task (`task_clones`) | [git-hardening](docs/git-hardening.md) |
| Stopping a worker | Stop one agent cleanly without losing its work | [stopping-a-worker](docs/stopping-a-worker.md) |
| **Two runtimes** | | |
| Claude and Cursor orgs | Orgs, runtimes, model maps and message routing | [runtimes](docs/runtimes.md) |
| **Run it fast** | | |
| Scheduled jobs | Owner-defined recurring jobs that mail the director (`factory schedule`) | [schedule](docs/schedule.md) |
| Go CLI | Opt-in Go build of the `factory` CLI (`cli_impl`); Python stays the default | [cli-go](docs/cli-go.md) |
| Terminal backends | herdr-core (`hc`) is the default; the classic herdr terminal UI is opt-in | [terminal-backends](docs/terminal-backends.md) |
| **See it** | | |
| Web UI | Read-only pages for goals, tasks, agents, throughput and quality | [web-ui](docs/web-ui.md) |
| State branch | Markdown exports and a DB dump pushed to the `state` branch | [state-branch](docs/state-branch.md) |

Each feature has its own file under docs/ (all pages: [docs/README.md](docs/README.md)). Also: [tests and CI](docs/tests-and-ci.md), [lessons](docs/lessons.md), [per-role plugins](docs/per-role-plugins.md), [updating persistent agents](docs/updating-persistent-agents.md), [boss mail](docs/boss-mail.md).

<p align="right"><a href="#readme-top">back to top</a></p>

## How it compares

| | One Claude Code session | Hand-run subagents | Hivemill |
|---|---|---|---|
| Role separation | One agent plans, writes and judges its own work | You choose the roles each time | Fixed roles with their own prompts and permissions, enforced by hooks ([worker-guard](docs/worker-guard.md)) |
| Independent review | The author reviews itself | Only if you start a reviewer | A separate reviewer and QA check every PR ([verdict-gates](docs/verdict-gates.md)) |
| Merge gate | You merge by hand | You merge by hand | The judge merges, gated on reviewer and QA ([verdict-gates](docs/verdict-gates.md)) |
| State and audit | The chat transcript | Whatever you wrote down | Goals, tasks, messages and verdicts in SQLite with an append-only event log ([db-layout](docs/db-layout.md)) |
| Resource gate | None | None | A spawn gate queues agents until RAM, load and Claude process count allow ([spawn-queue](docs/spawn-queue.md)) |
| Recovery after reboot | Start over | Start over | Boot units resume the headquarters and active teams ([operations](docs/operations.md)) |

Works with: Claude Code, Cursor Agent, [herdr](https://github.com/herdrdev/herdr), `gh`, systemd user units and the [Moshi](#use-it-from-your-phone) phone app.

## The web UI

A read-only web UI shows goals, tasks, live agents, throughput and quality, in light and dark themes, with an org filter, a runtime chip per agent and cost, tokens and wall time per task. Start it with `factory serve` ([docs/web-ui.md](docs/web-ui.md)). The screenshots come from fictional demo data only ([docs/demo-data.md](docs/demo-data.md)); click one for the full-size light image.

<!-- SLOT:GALLERY (T-0480): six page shots in a 3x2 table; swap paths and alt text only. -->
<table>
  <tr>
    <td align="center" width="33%">
      <a href="docs/images/home-light.png"><picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/images/home-dark.png">
        <img src="docs/images/home-light.png" width="280" alt="The overview page: a needs-you list, system gauges, goals with progress, live agents, shipped changes and quality">
      </picture></a><br>
      <sub><a href="docs/web-ui.md">Overview</a>: agents, PRs, goals and usage</sub>
    </td>
    <td align="center" width="33%">
      <a href="docs/images/goals-light.png"><picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/images/goals-dark.png">
        <img src="docs/images/goals-light.png" width="280" alt="The goals page: goals grouped by status with progress bars and priority">
      </picture></a><br>
      <sub><a href="docs/web-ui.md">Goals</a>: status and priority</sub>
    </td>
    <td align="center" width="33%">
      <a href="docs/images/tasks-light.png"><picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/images/tasks-dark.png">
        <img src="docs/images/tasks-light.png" width="280" alt="The tasks page: tasks grouped by status with goal, assignee, PR and CI state">
      </picture></a><br>
      <sub><a href="docs/web-ui.md">Tasks</a>: status, assignee and PR</sub>
    </td>
  </tr>
  <tr>
    <td align="center" width="33%">
      <a href="docs/images/agents-light.png"><picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/images/agents-dark.png">
        <img src="docs/images/agents-light.png" width="280" alt="The agents page: live Claude and Cursor agents by role and team with model and uptime">
      </picture></a><br>
      <sub><a href="docs/web-ui.md">Agents</a>: live agents by role and team</sub>
    </td>
    <td align="center" width="33%">
      <a href="docs/images/throughput-light.png"><picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/images/throughput-dark.png">
        <img src="docs/images/throughput-light.png" width="280" alt="The throughput page: merges per day and spawn-to-merge times as charts">
      </picture></a><br>
      <sub><a href="docs/web-ui.md">Throughput</a>: merged changes over time</sub>
    </td>
    <td align="center" width="33%">
      <a href="docs/images/quality-light.png"><picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/images/quality-dark.png">
        <img src="docs/images/quality-light.png" width="280" alt="The quality page: merge, rejection, retry and CI pass-rate cards with per-team scores">
      </picture></a><br>
      <sub><a href="docs/web-ui.md">Quality</a>: rejections and retries per team</sub>
    </td>
  </tr>
  <tr>
    <td align="center" width="33%">
      <a href="docs/images/goal-light.png"><picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/images/goal-dark.png">
        <img src="docs/images/goal-light.png" width="280" alt="The goal detail page: a goal's intent, plan, teams, tasks and progress">
      </picture></a><br>
      <sub><a href="docs/web-ui.md">Goal detail</a>: intent, plan, teams and tasks</sub>
    </td>
  </tr>
</table>

### How the web UI works (back end)

The dashboard is a small server in `web/`, built on Python's `http.server` with no framework, no Node at run time and no outside requests. It reads the factory DB and the Claude Code session logs and renders HTML on the server.

```mermaid
flowchart LR
    browser([browser]) -->|"GET page / api JSON"| server["web/server.py<br>Host allowlist, 8 requests at a time, CSP"]
    server --> views["web/views/*.py<br>data() then render()"]
    views --> queries["web/queries.py, execstate.py, flow.py<br>pure read-only queries"]
    queries --> db[("factory.db<br>opened mode=ro, query_only")]
    views --> tokens["web/tokens.py<br>Claude session logs → tokens and cost"]
    browser -->|"POST owner form (loopback only)"| server
    server -->|"runs"| cli["bin/factory config / halt / start / goal pause|resume|stop / project update"]
    cli --> db
```

- **One request.** `web/server.py` checks the method and the `Host` header, takes one of 8 request slots (503 when busy), then looks the path up in the route table of `web/views/__init__.py`. Each page is a module with `data(ctx, **params)`, which returns a plain dict, and `render(ctx, data)`, which returns HTML through the helpers in `web/html.py` and `web/components.py`. The view gets a fresh read-only DB connection for that request; nothing is cached across requests.
- **Read-only data access.** `web/db.py` opens the DB with `mode=ro` and `PRAGMA query_only`, and never imports the CLI (whose DB open migrates). `web/queries.py` holds pure query functions that return JSON-ready dicts. They never select message bodies, plan bodies, task specs or spawn arguments; instruction text appears only when the owner sets `serve_show_text=1` and the server is bound to loopback.
- **Derived states.** `web/execstate.py` works out the one state each goal and task shows (Running, Waiting, Paused, Stopping, Stopped, Blocked, Done) from the agents, holds and halts in the DB ([web-ui: execution states](docs/web-ui.md#execution-states-hm-47)).
- **Cost and tokens.** `web/tokens.py` indexes the Claude Code session logs, also those of sandboxed workers, and attributes each session to an agent, task and goal. `web/prices.py` turns tokens into an estimate at list prices. Cursor Agent writes no usage counts, so Cursor-org work shows sessions and agent-hours only.
- **JSON API.** `/api/<page>.json` returns the same dict a page renders, `/api/flow/goal/<id>.json` and `/api/flow/task/<id>.json` feed the flow debugger, and `/healthz` answers `ok`.
- **Flow debugger.** The Flow section of the goal and task pages is a React app (TypeScript, Vite, React Flow) in `web/flowapp/`. Its build is committed under `web/static/flow/`, so the server, tests and CI need no Node; a manifest hash makes a test fail when the build is stale ([flow-debugger](docs/flow-debugger.md)). Every other page works without JavaScript.
- **Owner controls, on loopback only.** The UI answers GET and HEAD, plus five POST paths: `/settings` and `/settings/gate` (curated settings and a project's merge gate), `/halt` and `/start` (urgent stop and start again), and `/goal-control` (pause, resume or stop a goal). Each is refused unless the server is bound to a loopback address, the `Origin` is the server's own, and the form carries the token issued at start. The server never writes itself: it runs the matching `bin/factory` command, which validates the input, checks the role and logs an event.
- **Self-reload.** About once a minute the server compares its code (`web/`, `scout/`, `bin/factory`) with what it started with. When the new code imports cleanly, it finishes the open requests and re-executes itself on the same port. When the new code fails to import, the old code keeps serving and the journal logs an error.

Pages and their routes:

| Route | Page |
|---|---|
| `/` | Overview: what needs you, system gauges, open goals, running agents, shipped work, quality |
| `/goals`, `/goal/<id>` | Goals by status; one goal with its state, criteria, tasks, flow, cost and time |
| `/tasks`, `/task/<id>` | Tasks with PR and CI state; one task with its stage flow, verdicts, rework and cost per agent |
| `/agents` | Running, queued and ended agents by org, team, role and runtime |
| `/resources` | The spawn gate, capacity gauges and the checks behind them |
| `/throughput`, `/quality` | Merges over time and where the time goes; rejections, retries and CI pass rate |
| `/changelog`, `/tokens` | Merged work; token use and estimated cost by goal, task, agent, model and org |
| `/settings`, `/halt`, `/goal-control` | Owner controls (forms only on a loopback bind) |

Run it: `factory serve` listens on one private LAN address, port 8765 by default (`serve_bind`, `serve_port`, `serve_hostnames`), and refuses wildcard and public addresses. To start it at boot, run `systemd/install.sh --with-serve`, which installs a `factory-serve` unit with tight memory, CPU and filesystem limits. For a local check, run `factory serve --bind 127.0.0.1 --port <port>`. `python3 ci/visual_qa.py` captures every page in both themes and two sizes and checks overflow, contrast and render time. Full reference: [docs/web-ui.md](docs/web-ui.md).

## Herdr desktop dashboard

If you use the [Herdr app](https://herdr.dev), Hivemill adds a status bar and a dashboard tab to it. The dashboard shows alerts, budget and cost, the Claude and Cursor lanes, active goals and the factory's agents.

`/hivemill:setup` offers it as an optional step. Or run `python3 plugins/hivemill/scripts/install.py --herdr-app --dry-run` and then `--yes` on the machine where the app runs. Details: [docs/herdr-app-dashboard.md](docs/herdr-app-dashboard.md).

<p align="center">
  <img src="docs/film/herdr/panel-factory.png" width="420" alt="The Hivemill dashboard tab in the Herdr desktop app: lanes and tiles for the factory">
  <img src="docs/film/herdr/panel-status-bar.png" width="420" alt="The Hivemill status bar across the bottom of the Herdr desktop app">
</p>

## Status and limits

- An agent is a Claude Code or a Cursor Agent session, depending on its org, so it uses your Claude or Cursor usage. Claude is the default.
- The `hc` (herdr-core) terminal backend is the default (`terminal_backend = auto` prefers `hc`); the classic herdr terminal UI is still supported as an opt-in (`terminal_backend = herdr`) ([docs/terminal-backends.md](docs/terminal-backends.md)).
- It is built for a single box, not a cluster. State is one SQLite file.
- Agent isolation is a tripwire, not a sandbox. Hooks and permission settings stop honest mistakes and make bypasses visible; they do not contain a determined adversary. Read [SECURITY.md](SECURITY.md) for the threat model and the known limits before you point it at anything you cannot afford to lose.
- The worker sandbox is opt-in (`sandbox_roles`, off by default) and a tripwire, not a boundary: it has no egress filter ([docs/worker-sandbox.md](docs/worker-sandbox.md)).
- The web UI has no authentication; bind it to an address you trust. It is read-only on a LAN bind; its owner controls (settings, urgent stop, goal pause/resume/stop) work only on a loopback bind.

Not affiliated with Anthropic. Claude and Claude Code are products of Anthropic.

## Use it from your phone

Install [Moshi](https://getmoshi.app) on your phone, connect to your box over SSH, and run `herdr` there to reach the boss's pane. Moshi is a third-party app, not part of Hivemill.

## Resources

- [What's new in v0.5.0](docs/releases/v0.5.0-announcement.md): a short plain-English summary of the v0.5.0 release.
- [What's new in v0.4.0](docs/releases/v0.4.0-announcement.md): a short plain-English summary of this release.
- [docs/examples/](docs/examples/README.md): three walkthroughs with real output.
- [docs/README.md](docs/README.md): index of every docs page. [docs/SETUP.md](docs/SETUP.md): install and troubleshooting.
- [docs/finishing-coders.md](docs/finishing-coders.md): how coders finish. [Known gaps](docs/worker-guard.md) of the worker guard.
- [docs/worker-sandbox.md](docs/worker-sandbox.md): worker sandbox design, owner steps, rollout, rollback.
- [docs/adopt/ADOPT.md](docs/adopt/ADOPT.md): let your own Claude Code set it up.
- [CHANGELOG.md](CHANGELOG.md), [SECURITY.md](SECURITY.md), [THIRD_PARTY.md](THIRD_PARTY.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) first. A feature PR adds or edits its docs/<feature>.md page and does not edit this README. Small, well-scoped places to start are in [docs/STARTER_ISSUES.md](docs/STARTER_ISSUES.md). Report vulnerabilities as described in [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE). Third-party notices: [THIRD_PARTY.md](THIRD_PARTY.md).

<p align="right"><a href="#readme-top">back to top</a></p>
