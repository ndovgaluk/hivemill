# Boss plugin

`factory-boss` is loaded (via `--plugin-dir roles/plugins/boss`) only for agents with role `boss`.
`factory spawn` passes the directory when `roles/plugins/<role>/` exists, so the boss picks it up when it is relaunched.

All text here is factory-authored; nothing is copied from third parties.

## Skills
- `story-run`: start, follow and unblock a story run of the workflow engine (`factory wf start`), including batches of prepared task-manager tasks (DVDG-565).

## Adding a skill
Add `factory-boss/skills/<name>/SKILL.md` with front matter `name:` (equal to the directory name) and `description:` (what it does, plus a "Use when ..." trigger).
Text only: no hooks, MCP config, scripts, executables or HTML. `tests/test_plugins.py` enforces this.
