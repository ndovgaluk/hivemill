# "Deny rule … never matches" warnings in agent panes

## Q: (boss pane: ⚠ Deny rule Advisor matches no tool; Write(…) never matches · use Edit(…); auto mode notice)

Those are warnings printed by Claude Code 2.1.322 when it loaded the factory's per-role settings file. These warnings are **harmless**: nothing is left unprotected.

**What I checked** in the rendered boss settings (`~/factory/run/settings/boss.json`, 49 deny rules): every path in the warnings **also has an `Edit(...)` deny rule**.

| Protected path | Deny rules present |
|---|---|
| `factory.db*`, `db/**`, `exports/**`, `state/**`, `bin/**`, `roles/**`, `run/settings/**` | `Edit` + `Write` |
| `run/guard-export.json*` | `Edit` + `Write` + `MultiEdit` + `NotebookEdit` |

**What the warnings mean:**
- **`Write(...) never matches · use Edit(...)`**: in this Claude Code version, one `Edit(path)` rule covers every file-writing tool (Write, Edit, NotebookEdit). The `Edit(...)` rules are already there, so these paths stay blocked; the `Write(...)` copies are redundant here.
- **`MultiEdit ... matches no tool`**: that tool no longer exists in Claude Code. Redundant too, and the same path has `Edit`.
- **`Advisor matches no tool`**: a deny rule for a tool that isn't in this Claude Code version. Nothing to block, so no effect.
- On top of these rules, the worker-guard hook checks every Bash command (`PreToolUse` on `Bash`).

**The other two notices:**
- **Auto mode:** the factory starts its agents in Claude Code's auto permission mode (`--permission-mode auto`). That's by design, so the agents don't stop to ask you for each tool call. The deny rules and the worker guard are its safety net.
- **The API credits line** is a Claude plan notice, unrelated to the factory.

---

## Q: What are these warnings? Can we get rid of them?

These warnings are **cosmetic**, and the rules behind them are **deliberate**. I wouldn't just delete them.

**What they are:** when an agent starts, Claude Code 2.1.322 checks the agent's permission rules and warns about any rule it considers useless in its own version (see above).

**Why they're there anyway** (what I found in `~/factory`):
- **The Cursor runtime.** The factory runs Cursor agents from the same role settings, and Cursor's permission system uses `Write(…)` and `Shell(…)` rules. `tests/test_cursor_pilot.py` checks that the pm template keeps `Write(**)` and `Shell(sudo…)`. Removing the `Write` rules would **loosen the guard for Cursor agents**.
- **The Advisor rule.** `tests/test_advisor_deny.py` exists so an Advisor tool, in Claude Code versions that have one, can't read secrets.
- **The extent.** The redundant `Write(…)` rules number from 8 (boss) to 59 (qa) per role template, and 5 test modules check them. The repo's rules say guard changes need accept and reject tests and must never loosen silently.

**Your options:**
1. **Leave it (my recommendation for now).** The warnings appear once when an agent starts, the agents ignore them, and protection is unaffected.
2. **Fix it properly as a factory goal:** render the settings **per runtime**. Claude agents get only `Edit(…)` rules plus whatever their Claude Code version actually has; Cursor agents keep `Write(…)`/`Shell(…)`. Tests would show nothing is loosened for either runtime. Medium-sized, touches risky paths — a fit for a later goal once G-001 is merged.

Deleting the rules by hand in `~/factory` won't work either: those files are protected from edits, and the tick fast-forwards `~/factory` to `main`, which would undo any local edit.
