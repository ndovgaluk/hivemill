# Local docs

The full replies from the setup session of 2026-11-12/13 (Claude Code, Opus 5.5), each under the question that
prompted it (`## Q: …`), grouped by topic. Not committed (`.gitignore`). Facts were checked against the repo and the
live install at the time; anything marked "not verified" was not.

| # | File | Topic |
|---|---|---|
| – | [GLOSSARY.md](GLOSSARY.md) | The words of the factory (goal, factory task, role, agent, verdict, …) and the ones to avoid |
| – | [INSIGHTS.md](INSIGHTS.md) | Short rules learned the hard way; read at the start of every request, written by `/engineering-insights` |
| 00 | [00-session-log.md](00-session-log.md) | One line per turn: what was asked and done |
| 01 | [01-windows-wsl-setup.md](01-windows-wsl-setup.md) | WSL2 + Ubuntu setup, VS Code, terminal tips, admin mismatch |
| 02 | [02-fork-and-upstream.md](02-fork-and-upstream.md) | Fork, remotes, syncing upstream, `/com-tsr pulltofork` |
| 03 | [03-docker-and-database.md](03-docker-and-database.md) | No Docker, no DB server |
| 04 | [04-why-python-and-the-go-port.md](04-why-python-and-the-go-port.md) | Language choice, ADR 0001, other stacks |
| 05 | [05-wpf-and-linux-hosted-factory.md](05-wpf-and-linux-hosted-factory.md) | Building Windows apps (WPF) with a Linux factory |
| 06 | [06-native-windows-after-go-port.md](06-native-windows-after-go-port.md) | Will Go make it run on Windows without WSL? |
| 07 | [07-viewing-herdr-from-windows.md](07-viewing-herdr-from-windows.md) | Watching agents from Windows |
| 08 | [08-mcp-access.md](08-mcp-access.md) | MCP servers for Claude in WSL and in the factory |
| 09 | [09-installation-and-updates.md](09-installation-and-updates.md) | What the install does, how code changes take effect |
| 10 | [10-goals.md](10-goals.md) | What a goal is |
| 11 | [11-roles.md](11-roles.md) | All 14 roles |
| 12 | [12-who-creates-tasks.md](12-who-creates-tasks.md) | Boss vs director vs lead vs pm |
| 13 | [13-worktrees.md](13-worktrees.md) | Where agents change code, reuse, pnpm |
| 14 | [14-agent-communication.md](14-agent-communication.md) | Messages, inbox, nudges, chain of command |
| 15 | [15-herdr-integration.md](15-herdr-integration.md) | How the factory drives herdr |
| 16 | [16-permission-warnings.md](16-permission-warnings.md) | The "Deny rule … never matches" warnings |
| 17 | [17-tsr-tasks-and-attachments.md](17-tsr-tasks-and-attachments.md) | Feeding Taskosaur tasks to the boss, screenshots |
| 18 | [18-staff-engineer.md](18-staff-engineer.md) | The staff-engineer role in detail |
| 19 | [19-vscode-markdown.md](19-vscode-markdown.md) | Markdown viewer, preview as default, blue inline code |
| 20 | [20-multiple-projects.md](20-multiple-projects.md) | Working on another project; herdr has no project view |
| 21 | [21-where-interactions-are-defined.md](21-where-interactions-are-defined.md) | Where agent interactions are defined: prompts, skills, CLI, guard, docs |
| 22 | [22-how-agents-get-work.md](22-how-agents-get-work.md) | How an agent learns about new or changed tasks |
| 23 | [23-who-adds-projects.md](23-who-adds-projects.md) | Who may run `factory project add` / `update` |
| 24 | [24-testing-in-the-factory.md](24-testing-in-the-factory.md) | When tests run, affected vs full suite, CI tiers, local gate |
| 25 | [25-web-ui-walkthrough.md](25-web-ui-walkthrough.md) | Web UI pages and which roles they show; walkthrough Q&A |
| 26 | [26-forwarding-tsr-work-to-the-boss.md](26-forwarding-tsr-work-to-the-boss.md) | Message to the boss for DVDG-540/544 with manual TSR sync |
| 27 | [27-tsr-integration-and-models.md](27-tsr-integration-and-models.md) | Planned TSR integration (both epics), model per role, Windows/WSL folders |
| 28 | [28-goal-parameter-and-agent-errors.md](28-goal-parameter-and-agent-errors.md) | TSR skill `goal` parameter; reading guard blocks and API errors in agent panes |
| 30 | [30-flow-debugger-implementation.md](30-flow-debugger-implementation.md) | Flow debugger (DVDG-551): task order for a single agent, stack, hot reload, Agentation, reference keys, design concept |
| 31 | [31-multi-angle-review.md](31-multi-angle-review.md) | `multi-angle-review` workflow: 3 angle agents + 3 verifiers on gated PRs; reading its status line |
| 31 | [31-why-g-001-took-hours.md](31-why-g-001-took-hours.md) | Why goal G-001 ran for hours: where the time went, six workflow problems, what to do |
| 32 | [32-practices-from-taskosaur.md](32-practices-from-taskosaur.md) | Glossary, insights file, local skills and React skill brought from Taskosaur: what was brought, what was not, two copies |
| 33 | [33-stopping-the-factory-mid-goal.md](33-stopping-the-factory-mid-goal.md) | What survives a factory stop mid-goal, what comes back by itself, clean stop steps |
| 34 | [34-technical-walkthrough-goal-to-coder.md](34-technical-walkthrough-goal-to-coder.md) | Technical walk-through: agent, CLI, database; how an agent knows the CLI; state vs messages vs events; real G-001 trace with times |
| 35 | [35-worktree-files-prompt-budget-attempts.md](35-worktree-files-prompt-budget-attempts.md) | Role prompt budget (12000 / 11410 bytes) and where it comes from; the three-attempt limit between coder and reviewer; worktree reuse and local-only files; flow debugger times; `/hm master-local-deploy` |
