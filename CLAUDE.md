# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Hivemill is a self-hosted "software factory": AI coding agents (Claude Code or Cursor Agent) in fixed roles (boss, director, lead, pm, coder, qa, reviewer, judge, cleaner, ...) run in herdr terminal panes and coordinate through one SQLite DB via the `factory` CLI. The factory builds itself: its own changes arrive as `factory/<task-id>` branches and PRs that a separate reviewer + QA check and a judge merges. Commit/PR titles carry the factory task id (`T-1262: ...`).

Python 3.11+, **standard library only** (nothing to pip install). Go is used only for an optional port of the worker guard.

**Linux only.** `bin/factory_cli.py` imports `fcntl`/`pwd` at load and uses `/proc`, `os.statvfs`, systemd and namespaces, so the CLI and most tests do not run on native Windows or Git Bash. On Windows, work inside WSL2 Ubuntu with the clone in the Linux filesystem, not under `/mnt/<drive>` (`docs/getting-started.md` section 6.0). A native Windows port was assessed and set aside: `docs/research/windows-port.md`. Do not add Windows compatibility shims unless asked.

## Commands

```
# Lint touched Python
python3 -m py_compile bin/factory bin/factory_cli.py

# One test module (preferred locally)
python3 -m unittest discover -s tests -p test_gate.py
python3 -m unittest tests.test_gate            # equivalent; add -k name for one test

# Tests a diff can affect + smoke set, < 2 min (what roles run instead of the full suite)
python3 ci/affected.py --base origin/main --quick --run
python3 ci/ci_tier.py classify --base origin/main   # docs / normal / risky CI tier of the branch

# Full suite (CI runs it sharded; locally it takes a host-wide test slot)
python3 -m unittest discover -s tests -v
python3 ci/shard.py run --shard 1 --total 10 --out <file>.json   # one CI shard

# Go worker guard (from go/)
cd go && test -z "$(gofmt -l .)" && go vet ./... && go test -race -count=1 ./... && go build ./...

# Web UI on seeded demo data (nothing real runs)
export TRIAL=$(mktemp -d)
python3 ci/demo_seed.py --home "$TRIAL/demo" --now 2026-10-25T12:00:00+01:00
HOME=$TRIAL/demo/home FACTORY_HOME=$TRIAL/demo bin/factory serve --bind 127.0.0.1 --port 18624
```

Testing rules (`docs/testing.md`):
- A run that reports 0 tests is a failure. A PR must not run fewer tests than `main` (CI test-count gate; an intentional drop needs a `tests-removed: <reason>` line in the PR body).
- Never export `GIT_DIR`, `GIT_WORK_TREE` or other `GIT_*` vars around a test run: harness git calls would hit the real repo.
- The suite is offline: `tests/harness.py` runs `bin/factory` as a subprocess against a throwaway `FACTORY_HOME` with `herdr`, `gh` and `hc` stubbed from `tests/stubs/`. Tests must never touch a live home (`~/factory`).

## Architecture

- **CLI** — `bin/factory` is a 9-line stub that imports `bin/factory_cli.py` (~18.5k lines, one file, all commands; subcommands registered near the end via `sp.add_parser`). Read/import code from `factory_cli.py`, never from the stub (`tests/harness.py`: `FACTORY_SRC` vs `FACTORY`). Top-level literals such as `SCHEMA`, `DEFAULT_CONFIG`, `ROLES`, `MODELS` live there; tests read them with `ast` rather than importing. `bin/flags.json` holds feature flags. Details: `docs/cli-layout.md`.
- **State** — one SQLite DB at `$FACTORY_HOME/db/factory.db` (`FACTORY_HOME` defaults to `~/factory`), resolved only through `web/dbpath.py`. Only `factory init` creates it. Goals, plans, tasks, messages, verdicts and an append-only event log are rows; `factory export` writes markdown to the `state` branch. `docs/db-layout.md`.
- **Heartbeat** — `factory tick`, run every minute by `systemd/factory-tick.timer`: reaps, spawns (behind a resource gate on RAM/load/claude process count, `docs/spawn-queue.md`), nudges, exports. `systemd/` holds all user units and `install.sh`.
- **Roles** — `roles/<role>.md` prompts plus shared `roles/_common.md`; `roles/settings/<role>.json.in` permission templates; `roles/plugins/<role>/` per-role skills; `roles/hooks/worker-guard.py` is the PreToolUse guard that blocks out-of-role actions (Go port in `go/cmd/worker-guard`, selected by config `guard_impl`; CI checks Python/Go equivalence with `ci/guard_diff.py`). `_common.md` + any one role file must stay under 12000 bytes (`tests/test_repo_hygiene.py`); move detail into a role plugin skill instead. Prompt changes reach only newly spawned agents.
- **Merge gate** — coder opens PR → reviewer verdict + QA verdict → `factory judge` merges only on both passing and green required checks. `docs/verdict-gates.md`, `docs/lifecycle.md`.
- **Runtimes/orgs** — a `claude` org and a `cursor` org share one box and DB; each goal belongs to one org. `scout/orgs.py`, `scout/cursor_harness.py`, `docs/runtimes.md`.
- **`scout/`** — sandboxing and trial infrastructure (nsbox, workerbox, gatebox, egress, ghcred, testcg) plus the skill scout/skilleval pipeline (`skilleval/` holds eval tasks).
- **`web/`** — read-only, unauthenticated stdlib HTTP UI (`factory serve`): `server.py`, `queries.py`, one module per page in `web/views/`.
- **`ci/`** — CI and release tooling: `affected.py` (test selection), `ci_tier.py`, `shard.py` + `shard_timings.json`, `test_count_gate.py`, guard corpus/golden/diff, public-text and scrub scanners, demo seeding/recording.
- **`plugins/hivemill/`** — the Claude Code plugin that installs the factory (`/hivemill:setup`).

## Rules for changes

- One task, one PR; no drive-by refactors (list unrelated finds in the PR body). Feature docs go in `docs/<feature>.md` and a link in `docs/README.md`, not new README sections. PR body follows `.github/pull_request_template.md` (`docs/pr-descriptions.md`).
- **Guard changes** (hook rule, settings deny rule, CLI refusal, CI check) need a test it must reject and a test it must accept, both through the real entry point (hook as invoked, CLI as subprocess). Never loosen a guard silently. `docs/planning-rules.md`.
- Quality bar for code: `docs/coder-rules.md` / `roles/coder.md` (deterministic outcome tests, a new test shown failing without the fix, fail-closed errors, no live-home paths).
- **Public text**: tracked files are scanned (`tests/test_scrub_clean.py`, `ci/scrub_scan.py`, `tests/test_repo_hygiene.py`) for real home paths, LAN addresses, non-example emails, tokens and conflict markers. Use placeholders like `/home/user`, `example.com`, `your-box`.
- Touching risky paths (`.github/`, `roles/hooks/`, role settings, `systemd/`, sandbox modules in `scout/`, CI gate scripts, or judge/gate/`SCHEMA`/`DEFAULT_CONFIG` code in `factory_cli.py`) makes CI run the full suite (`docs/tests-and-ci.md`). Install/setup changes also need `ci/freshbox_test.py` (`CONTRIBUTING.md`).
