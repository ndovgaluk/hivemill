# Getting started: parts, stack, build and run

One page for a newcomer who wants to know what the repository contains, which technologies it uses, and how to install, build, test and run it. The authoritative install reference is [SETUP.md](SETUP.md); this page puts its steps in order and links to it for the details (configuration keys, troubleshooting, sandbox).

## 1. What Hivemill is

Hivemill is a self-hosted software factory. AI coding agents (Claude Code or Cursor Agent sessions) work in fixed roles: boss, director, lead, pm, coder, qa, reviewer, judge, cleaner, plus a few support roles. Each agent runs in its own pane of the [herdr](https://github.com/herdrdev/herdr) terminal multiplexer. They coordinate only through a SQLite database, using the `factory` CLI. A coder opens a pull request. A reviewer and QA give verdicts on it, and a judge merges only when both pass and CI is green. The factory develops itself the same way: its own PRs come from `factory/<task-id>` branches.

How a change flows: [lifecycle.md](lifecycle.md), [verdict-gates.md](verdict-gates.md).

## 2. Technology stack

| Layer | Technology | Notes |
|---|---|---|
| Core CLI, tick, web UI, tooling | **Python 3.11+, standard library only** | Nothing to `pip install`. CI runs Python 3.13. 3.11 is the floor (`datetime.fromisoformat` with `Z`, see [SETUP.md](SETUP.md#prerequisites)). |
| State | **SQLite** (WAL mode) through Python's `sqlite3` | One file: `<FACTORY_HOME>/db/factory.db` ([db-layout.md](db-layout.md)). |
| Optional worker guard port | **Go 1.27** (toolchain go1.27.3, stdlib only, no `go.sum`) | `go/`. Python is the default guard ([worker-guard-go.md](worker-guard-go.md), [go-toolchain.md](go-toolchain.md)). |
| Agent runtimes | **Claude Code** (default `claude` org), **Cursor Agent CLI** (optional `cursor` org) | [runtimes.md](runtimes.md). |
| Agent host | **herdr** terminal multiplexer, pinned release v0.9.5 for tests | One pane per agent. |
| GitHub | **git** and the **gh** CLI | One worktree (or clone) per task. PRs, CI status and merges go through gh. |
| Scheduling | **systemd user units** and a timer | `factory tick` every minute, boot recovery. |
| Sandbox (optional) | Linux user and mount namespaces (`unshare`, `setpriv`) | [worker-sandbox.md](worker-sandbox.md). |
| Web UI | Python `http.server`, server-rendered HTML, static CSS/JS in `web/static/` | Read-only, no auth. |
| Tests and CI | `unittest`, GitHub Actions (`.github/workflows/tests.yml`) | Offline suite with stubbed `herdr`, `gh` and `hc`. |
| Distribution | A Claude Code plugin (`.claude-plugin/marketplace.json`, `plugins/hivemill/`) | `/hivemill:setup` runs `plugins/hivemill/scripts/install.py`. |

**Platform.** The factory targets Linux (Debian or Ubuntu are tested). `bin/factory_cli.py` imports `fcntl` at module load, so the CLI and most tests do not run on native Windows or in Git Bash. On Windows, use WSL2 with Ubuntu ([section 6.0](#60-windows-set-up-wsl2-first)); a native port was assessed and set aside ([research/windows-port.md](research/windows-port.md)). macOS is not a documented target (systemd units, namespaces and `/proc` are Linux-only).

## 3. Repository map

| Path | What it holds |
|---|---|
| `bin/factory` | A 9-line launcher stub. It imports `bin/factory_cli.py` so Python caches the bytecode ([cli-layout.md](cli-layout.md)). |
| `bin/factory_cli.py` | The whole CLI in one module: DB schema (`SCHEMA`), defaults (`DEFAULT_CONFIG`), roles, every subcommand (`init`, `project`, `goal`, `task`, `spawn`, `judge`, `tick`, `serve`, `up`, ...). |
| `bin/flags.json` | Feature flags (`factory flags`). |
| `roles/` | Role prompts (`<role>.md`, shared `_common.md`), Claude settings templates (`settings/<role>.json.in`), per-role plugin skills (`plugins/<role>/`), hooks (`hooks/worker-guard.py`, the `worker-guard` shim, `boss-inbox.py`, the Cursor adapter). |
| `web/` | The read-only web UI: `server.py` (HTTP), `queries.py` (SQL), `views/` (one module per page), `static/` (CSS, fonts, theme script). |
| `scout/` | Sandboxing and trial infrastructure (`nsbox`, `workerbox`, `gatebox`, `egress`, `ghcred`, `testcg`), runtime/org helpers (`orgs.py`, `cursor_harness.py`) and the skill scout. |
| `skilleval/` | Tasks and controls for evaluating third-party skills. |
| `retro/` | The daily rejection retro (report and schedule). |
| `go/` | Go module `factory/go`: `cmd/worker-guard`, `cmd/factory-go-version`, `internal/guard`, `internal/shlex`, `internal/buildinfo`. |
| `ci/` | CI and release tooling: test selection (`affected.py`), CI tiers (`ci_tier.py`), sharding (`shard.py`), test-count gate, guard equivalence (`guard_diff.py`), public-text and scrub scanners, demo seeding and recording, fresh-box install test. |
| `systemd/` | User units (`herdr-server`, `factory-up`, `factory-tick` timer and service, `factory-serve`) and `install.sh`. |
| `plugins/hivemill/` | The Claude Code plugin: the `setup` skill and `scripts/install.py`. |
| `tests/` | The `unittest` suite, `harness.py` (throwaway `FACTORY_HOME`), `stubs/` (fake `herdr`, `gh`, `hc`), fixtures. |
| `docs/` | One page per feature; index in [README.md](README.md). |

Runtime layout of a live install (not in the repository): `<FACTORY_HOME>/db/factory.db` (database), `<FACTORY_HOME>/run/settings/<role>.json` (rendered role settings), `<FACTORY_HOME>/exports/` (markdown exports), `<FACTORY_HOME>/state/events.jsonl` (audit log). `FACTORY_HOME` defaults to `~/factory`, the clone itself.

## 4. Choose a path

| You want to | Go to | Needs |
|---|---|---|
| Look at the web UI and CLI on fictional data | [5. Demo without installing](#5-demo-without-installing) | Linux, Python 3.11+, git |
| Change the code and run the tests | [6. Development setup](#6-development-setup) | The above. Go 1.27 only for `go/` changes |
| Do any of this on Windows | [6.0 Windows: set up WSL2 first](#60-windows-set-up-wsl2-first) | Windows 10 or 11 with WSL2 |
| Run a real factory | [7. Full install](#7-full-install) | Linux box, Claude Code login, gh login, herdr |

## 5. Demo without installing

Nothing real runs here: no agent, no Claude usage. Run from the repository root:

```
git clone https://github.com/volekerb/hivemill.git
cd hivemill
python3 --version                                    # must be 3.11 or newer

export TRIAL=$(mktemp -d)
python3 ci/demo_seed.py --home "$TRIAL/demo" --now 2026-10-25T12:00:00+01:00
HOME=$TRIAL/demo/home FACTORY_HOME=$TRIAL/demo bin/factory serve --bind 127.0.0.1 --port 18624
```

Open <http://127.0.0.1:18624/>. In a second shell, run CLI commands against the same data:

```
HOME=$TRIAL/demo/home FACTORY_HOME=$TRIAL/demo bin/factory goal list
HOME=$TRIAL/demo/home FACTORY_HOME=$TRIAL/demo bin/factory agents
```

Keep the `HOME=` prefix: some pages read `~/.claude`, and without it they show your real usage. When done: Ctrl-C, then `rm -rf "$TRIAL"`. A version that also runs `factory init`, `project add` and `up` against the fake herdr is in [SETUP.md, "Try it without herdr"](SETUP.md#try-it-without-herdr). The demo data is described in [demo-data.md](demo-data.md).

## 6. Development setup

### 6.0 Windows: set up WSL2 first

WSL2 runs a real Ubuntu on Windows, so everything on this page works unchanged inside it. These steps are standard WSL usage. They are **not run in CI** and have not been verified by this project's tests.

1. In an administrator PowerShell, install it and reboot when asked:

   ```
   wsl --install -d Ubuntu
   ```

2. Open the Ubuntu terminal and create your Linux user. Run every later command on this page there, not in PowerShell or Git Bash.
3. Clone into the Linux filesystem (for example `~/factory` or `~/src/hivemill`), **not** under `/mnt/c` or `/mnt/d`. The tests and the factory rely on Linux file modes (`0600` token files), symlinks and file locks, which do not behave properly on a mounted Windows drive. A mounted drive is also slow for git.
4. For the systemd units ([section 7.5](#75-keep-it-running-systemd)), systemd must be on in WSL. Check with `systemctl --user status`. If it is off, put this in `/etc/wsl.conf`, then run `wsl --shutdown` from PowerShell and reopen Ubuntu:

   ```
   [boot]
   systemd=true
   ```

5. WSL2 limits its memory (by default to a share of the host's RAM). The spawn gate reads the memory WSL sees, so the limit decides how many agents fit. To change it, create `.wslconfig` in your Windows user folder with a `[wsl2]` section and a line such as `memory=16GB`, then `wsl --shutdown`.
6. The optional worker sandbox needs unprivileged user namespaces. Check with `unshare -r -n -m true && echo ok`, and read the AppArmor note in [SETUP.md](SETUP.md#prerequisites) for Ubuntu 24.04 and later.

Working from Windows:

- **Web UI:** `factory serve --bind 127.0.0.1` inside WSL is reachable from a Windows browser at `http://127.0.0.1:<port>/`.
- **Editing and debugging:** VS Code with the WSL extension opens the Linux folder from Windows (`code .` in the Ubuntu terminal) and runs the Python debugger inside WSL.
- **Claude Code:** install and log in inside WSL. A Windows install of Claude Code is a different environment and cannot run the factory.

### 6.1 Install the tools

On Debian or Ubuntu (including WSL2 Ubuntu):

```
sudo apt-get install -y git python3          # python3 must report 3.11+
git clone https://github.com/volekerb/hivemill.git
cd hivemill
```

There are no Python packages and no build step for the Python code. The CLI runs straight from the checkout: `python3 bin/factory --help`.

Go is needed only if you touch `go/`. Install the pinned toolchain at user level, as in [go-toolchain.md](go-toolchain.md):

```
cd "$(mktemp -d)"
curl -fsSLO https://go.dev/dl/go1.27.3.linux-amd64.tar.gz
echo "65efbc80fdc1fa2cd2631cad5b481777a68e8725f34e89f50fc6ac714e379b40  go1.27.3.linux-amd64.tar.gz" | sha256sum -c
rm -rf ~/.local/go && mkdir -p ~/.local
tar -C ~/.local -xzf go1.27.3.linux-amd64.tar.gz

export PATH=~/.local/go/bin:$PATH GOTOOLCHAIN=local GOFLAGS=-mod=readonly
go version                                   # go1.27.3
```

### 6.2 Build

Python has no build. The closest step is a compile check of the files you touched (CI does the same for the CLI):

```
python3 -m py_compile bin/factory bin/factory_cli.py
```

Go, from `go/`. These are the same four steps the `go` CI job runs:

```
cd go
test -z "$(gofmt -l .)"            # formatting
go vet ./...
go test -race -count=1 ./...
go build ./...
```

On a live install you do not build the guard binary by hand. When config `guard_impl` is not `python`, `factory tick` builds `go/cmd/worker-guard` into `~/.local/lib/factory/worker-guard` with `~/.local/go/bin/go` and stamps it with the tree id of `go/`. A stale or missing binary falls back to Python. Details: [worker-guard-go.md](worker-guard-go.md).

### 6.3 Test

The suite is offline. `tests/harness.py` runs `bin/factory` as a subprocess against a throwaway `FACTORY_HOME`, with `tests/stubs/` first on `PATH`, so it never touches a real factory.

```
# one module (the normal local run)
python3 -m unittest discover -s tests -p test_gate.py
python3 -m unittest tests.test_gate -k some_test_name

# only what your diff can affect, plus the smoke set, under 2 minutes
python3 ci/affected.py --base origin/main --quick --run

# which CI tier your branch gets (docs / normal / risky)
python3 ci/ci_tier.py classify --base origin/main

# the full suite (CI runs it in 10 shards)
python3 -m unittest discover -s tests -v
```

Rules that bite:

- A run that reports 0 tests is a failure.
- Your branch must not run fewer tests than `main`; the CI test-count gate enforces it.
- Do not export `GIT_DIR`, `GIT_WORK_TREE` or any other `GIT_*` variable around a test run: harness git calls would reach the real repository.
- A local full-suite run takes one of the host-wide test slots (`test_slots`, default 2) and may print `waiting for a test slot`.
- `tests/test_scrub_clean.py` and `tests/test_repo_hygiene.py` fail on real home paths, LAN addresses, non-example emails, token-shaped strings and conflict markers in tracked files. Write `/home/user`, `example.com` and similar placeholders.

The CI tiers, sharding and the Go/Python guard equivalence jobs are in [tests-and-ci.md](tests-and-ci.md). The local-versus-CI policy is in [testing.md](testing.md).

### 6.4 Run the code you changed

- CLI against a scratch home: `export FACTORY_HOME=$(mktemp -d) HOME=$(mktemp -d)`, then `python3 bin/factory init` and any command. Add `PATH=$PWD/tests/stubs:$PATH` and `FAKE_HERDR_STATE=...` to use the fake herdr, as in [SETUP.md](SETUP.md#try-it-without-herdr).
- Web UI: the demo in [section 5](#5-demo-without-installing).
- Before a PR: [CONTRIBUTING.md](../CONTRIBUTING.md), [coder-rules.md](coder-rules.md), [review-rules.md](review-rules.md), [pr-descriptions.md](pr-descriptions.md). Any change to install or setup also needs `sudo python3 ci/freshbox_test.py --repo <fork> --ref <branch>` ([SETUP.md, "Test a fresh install"](SETUP.md#test-a-fresh-install)).

## 7. Full install

This runs real agents and uses your Claude (or Cursor) usage. Use a dedicated Debian or Ubuntu machine or VM.

### 7.1 Prerequisites

| Tool | Check |
|---|---|
| Python 3.11+ | `python3 --version` |
| git | `git --version` |
| Claude Code, logged in | `claude --version`, then `claude` and `/login` |
| gh, logged in | `gh auth status` (run `gh auth login` and `gh auth setup-git` yourself) |
| herdr | `herdr --version` |
| systemd user session with linger (for boot units) | `loginctl show-user $USER -p Linger` prints `Linger=yes` |
| Optional: Cursor Agent CLI | `agent --version` (for the `cursor` org) |
| Optional: `unshare`, `setpriv`, user namespaces | `unshare -r -n -m true && echo ok` (only for the sandbox) |

Install herdr from the official repository and verify its checksum ([SETUP.md, "Install herdr"](SETUP.md#install-herdr)):

```
mkdir -p ~/.local/bin
HB=$(mktemp)
curl -fsSL -o "$HB" https://github.com/herdrdev/herdr/releases/download/v0.9.5/herdr-linux-x86_64
echo "14d9e8bc8b4a9e0118d77c32266f76d461f09b40342eb23752960bd89f59929d  $HB" | sha256sum -c -
install -m 755 "$HB" ~/.local/bin/herdr
```

### 7.2 Option A: the installer

In Claude Code:

```
/plugin marketplace add volekerb/hivemill
/plugin install hivemill
/hivemill:setup
```

Or the same installer from a terminal. It refuses to run as root or inside an agent pane:

```
git clone https://github.com/volekerb/hivemill.git
cd hivemill
python3 plugins/hivemill/scripts/install.py --check      # read-only report, suggests --max-agents
python3 plugins/hivemill/scripts/install.py --dry-run    # prints the plan, changes nothing
python3 plugins/hivemill/scripts/install.py --yes        # does it
```

It installs missing herdr, gh and Claude Code into `~/.local/bin`, then clones into `~/factory`, links `factory`, creates the DB and config, installs the systemd units and runs a smoke test. Exit 3 means you must do something first, such as a login; the command to run is printed, then rerun with `--resume`. The last line is `RESULT PASS ...` or `RESULT FAIL step=...`. All options and exit codes: [SETUP.md, "One-prompt install"](SETUP.md#one-prompt-install).

### 7.3 Option B: by hand

```
# 1. clone the latest release into the default home
git clone https://github.com/volekerb/hivemill.git ~/factory
cd ~/factory
git checkout "$(git tag --list 'v*' --sort=-v:refname | head -n 1)"

# 2. put the CLI on PATH
mkdir -p ~/.local/bin
ln -s "$PWD/bin/factory" ~/.local/bin/factory
factory --help

# 3. create the database and render the role settings
factory init                   # prints: initialised <FACTORY_HOME>/db/factory.db

# 4. register the repository the factory works on
factory project add myapp --name "My app" --repo ~/src/myapp --gh example-org/myapp
factory project list

# 5. optional: review the configuration
factory config                 # every key and value
factory config --check         # validates live values
```

For a home other than `~/factory`, export `FACTORY_HOME` everywhere and run `factory init --live-home <abs path>` once ([SETUP.md, "Install"](SETUP.md#install)). Configuration keys (agent caps, spawn gate, web port, required CI checks) are in [SETUP.md, "Configuration"](SETUP.md#configuration).

### 7.4 Start it

```
herdr server &                       # or: systemctl --user start herdr-server
herdr workspace list                 # exits 0 when herdr is up

factory up                           # starts boss, director (and scout), resumes active leads
factory agents                       # who is live or queued
factory res                          # spawn-gate state if something says QUEUED

factory serve --bind 127.0.0.1       # read-only web UI on http://127.0.0.1:8765/
```

Then open the boss's pane in herdr and describe what you want built. The boss is the only agent that talks to you. It turns your request into a goal, and the director staffs a team. The three walkthroughs in [examples/README.md](examples/README.md) show what follows, with real output.

### 7.5 Keep it running (systemd)

```
loginctl enable-linger $USER         # user units start at boot (changes your account)
bash systemd/install.sh --dry-run    # shows every action
bash systemd/install.sh              # links and enables the units; add --with-serve for the web UI
systemd-analyze --user verify systemd/*.service systemd/*.timer
```

Run it from the main checkout, not a worktree: the installed units are symlinks into the checkout. The units are `herdr-server.service`, `factory-up.service` (waits for herdr, then `factory up`), `factory-tick.timer` (every minute: reap, spawn, nudge, export) and optional `factory-serve.service`. Reboot behaviour and agent identity: [operations.md](operations.md).

### 7.6 Upgrade

```
cd ~/factory
git fetch --tags origin
git checkout "$(git tag --list 'v*' --sort=-v:refname | head -n 1)"
factory --version
```

The CLI migrates the DB schema on its first run. Read that release's upgrade notes first ([RELEASING.md](RELEASING.md)).

## 8. Where to read next

- Something fails: [SETUP.md, "Troubleshooting"](SETUP.md#troubleshooting).
- Containment and its limits: [../SECURITY.md](../SECURITY.md), [worker-guard.md](worker-guard.md), [worker-sandbox.md](worker-sandbox.md), [git-hardening.md](git-hardening.md).
- The web UI pages: [web-ui.md](web-ui.md).
- Every docs page: [README.md](README.md).
