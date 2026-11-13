# Windows port: feasibility assessment

Status: **reviewed 2026-11-11; decision: use WSL2, no native port for now.** Written from a read of the code plus one probe run on Windows (finding 6). No port was built. Claims are marked **measured** (from a command that was run), **read** (seen in the code or docs, with a location) or **inference** (not verified).

## Decision

Development on Windows happens inside **WSL2 Ubuntu** ([getting-started.md, section 6.0](../getting-started.md#60-windows-set-up-wsl2-first)). A native port is set aside. Reasons:

1. **Upstream moves too fast for a fork.** 544 commits in the 15 days from the first commit (2026-10-28) to 2026-11-11, and 187 of them touch `bin/factory_cli.py`, the file a port edits throughout (**measured**: `git log --since="30 days ago"`). A Windows fork would conflict on nearly every sync.
2. **Containment gets weaker.** The namespace sandbox has no Windows equivalent, and the worker guard would need new rules for PowerShell (finding 3).
3. **Cost.** WSL2 takes hours and has no ongoing cost. A full port takes weeks and then needs maintenance (see Options).

Revisit if upstream decides to support Windows, or if only the read-only core (CLI queries and the web UI) is wanted on Windows (option B).

## Question

Can Hivemill run natively on Windows (no WSL, no Linux VM), and what would it take?

## Trigger

On a Windows 11 machine (Python 3.14, Git Bash, no WSL, no Docker), `factory init` against a temporary `FACTORY_HOME` fails at import:

```
File "...\bin\factory_cli.py", line 14, in <module>
    import fcntl
ModuleNotFoundError: No module named 'fcntl'
```

**Measured.** The CLI cannot start at all, so not even `init`, `config` or `serve` work. On the same machine `wsl -l -v` reports that WSL is not installed and `docker` is not on `PATH` (**measured**).

## Short answer

A staged port is feasible. The original concern was herdr, the terminal multiplexer that hosts every agent pane. It turns out not to be a blocker, because herdr ships a Windows build (below). The remaining work is a set of POSIX-specific spots in the Python code, the boot and timer units, and the namespace sandbox. The sandbox has no Windows equivalent and would stay Linux-only. The effort is large, not a rewrite: the CLI is one ~18.5k-line module (**measured**: `wc -l bin/factory_cli.py` = 18494) with a test suite that assumes Linux.

## Finding 1: herdr supports Windows

- The herdr v0.9.5 release (<https://github.com/herdrdev/herdr/releases>) has a `herdr-windows-x86_64.zip` asset next to the Linux and macOS binaries (**read**, from a release-page screenshot the owner provided).
- In a local herdr checkout (`Cargo.toml` version 0.9.5, `git describe` = `preview-2026-10-12-6d697e1e75ff-39-gee5bfb50`), **read**:
  - `src/platform/windows.rs` and `src/platform/windows/` hold the platform code. `AGENTS.md` requires the Windows zip to contain `herdr.exe` "and its app-local ConPTY runtime".
  - On Windows the server listens on a **named pipe**, not a Unix socket (`docs/next/CHANGELOG.md`: "`herdr server stop` now stops Windows named-pipe servers ...").
  - `CHANGELOG.md` lists recent Windows fixes, among them Claude Code session tracking with non-ASCII user folders, sessions kept across a Windows shutdown, and the rule that an elevated server accepts only administrator clients unless `allow_unelevated_clients` is set.
- `HERDR_SOCKET_PATH` is herdr's documented override for the API socket (`docs/next/website/src/content/docs/cli-reference.mdx`, **read**).
- herdr is not installed on the assessed machine: no `herdr` on `PATH` and no `target/release/*.exe` in the checkout (**measured**).

### How Hivemill talks to herdr

Hivemill never opens the herdr socket itself. It runs the `herdr` CLI as a subprocess and pins `HERDR_SOCKET_PATH` (**read**):

- `herdr_socket()` at `bin/factory_cli.py:1072` resolves config `herdr_socket` (default `~/.config/herdr/herdr.sock`).
- The subprocess env sets `HERDR_SOCKET_PATH` (`bin/factory_cli.py:1196-1199`). `herdr(*args, ...)` at `:1409` is the call wrapper, with `herdr_agents`, `herdr_workspaces`, `herdr_tabs` and `herdr_panes` after it.
- Workers get a deliberately dead `HERDR_SOCKET_PATH` (`DEAD_SOCKET`, e.g. `:10451`) so a herdr call by hand inside a worker cannot reach the live server.

**Inference:** most of the ~600 herdr-related lines should carry over unchanged, provided herdr's CLI output (JSON) is the same on Windows. Two parts must change:

1. The default `herdr_socket` value. A filesystem `.sock` path becomes a named-pipe name on Windows. The exact form herdr expects in `HERDR_SOCKET_PATH` on Windows is **not verified**.
2. `DEAD_SOCKET` and `_is_live_socket()` (`:1293`). Both reason about socket paths and need a named-pipe equivalent, so the worker isolation still holds.

## Finding 2: POSIX dependencies in the Python code

Counts are matching **lines** from `grep -rEc` over `bin web scout ci retro roles tests plugins` (`*.py`) (**measured**). They are rough: some patterns over-count (for example, `bash` matches in prose and test data).

| Dependency | Lines (files) | Used for (read) | Windows option (inference) |
|---|---|---|---|
| `fcntl` | 51 (14) | Imported at top level (`bin/factory_cli.py:14`). Used for flock locks: tick lock, test slots (`tests/_slot.py`), Go guard build lock (`:2525`) | `msvcrt.locking`, or lock files with `os.open(O_CREAT\|O_EXCL)`. The semantics differ: the lock is on a byte range, not advisory. Must at least be imported lazily |
| `pwd` | 94 (38) | Passwd home lookup, imported at top level (`:24`). Live-home detection uses the real passwd home, not `$HOME` | `os.path.expanduser` / `USERPROFILE`. The "passwd home vs `$HOME`" safety distinction needs a Windows definition |
| `os.getuid` / `geteuid` / `fchmod` / `chown` | 148 (62) | Owner checks, `0600` token-file checks, atomic writes with a mode | No uid on Windows. Mode checks mean little there and would need ACL logic or a documented relaxation |
| `/proc/` | 77 (32) | Spawn gate (count `claude` processes), reaping, cwd and open-fd checks in the `/tmp` sweep | `Get-CimInstance Win32_Process` through PowerShell, or `ctypes` with Toolhelp32. `psutil` would break the stdlib-only rule. The cwd and open-fd checks have no cheap equivalent |
| `os.killpg`, `setsid`, `start_new_session` | 36 (12) | Kill whole process groups on timeout (e.g. `_run_build`, `:2473`) | `CREATE_NEW_PROCESS_GROUP` plus `taskkill /T /F`, or Job Objects |
| `signal.SIGKILL` / `SIGHUP` / ... | 28 (12) | Hard stops, exit-code mapping (137 = SIGKILL in the guard shim) | `TerminateProcess`. The exit-code conventions need a Windows mapping |
| `systemctl` / `loginctl` / `journalctl` | 99 (17) | Boot units, linger checks, serve unit drift, install | Task Scheduler (tick every minute, start at logon). The installer and its tests change |
| `unshare` / `setpriv` / `nsenter` | 157 (25) | Worker sandbox (`scout/nsbox.py`, `workerbox.py`, `gatebox.py`, `egress.py`) | None. Keep Linux-only and refuse `sandbox_roles` on Windows (it is off by default) |
| `os.symlink` / `symlink_to` | 146 (68) | CLI link in `~/.local/bin`, unit links, tests | Needs Developer Mode or admin on Windows. Use copies or `.cmd` launchers |
| `/tmp` literals | 355 (60) | Scratch dirs, test homes, sweep patterns | `tempfile.gettempdir()`. The sweep's name patterns stay valid |
| `sh -c` / `"sh"` / `bash` | 456 (95) | Hook shim `roles/hooks/worker-guard` (sh), settings templates, tests | See finding 3 |
| `grp` / `termios` / `resource` | 8 (7) | Misc | Lazy import plus a fallback |

## Finding 3: hooks and the worker guard

- The 10 worker settings templates call `sh <live home>/roles/hooks/worker-guard --role <role>`. The 3 HQ templates call `python3 .../worker-guard.py --hq` (`docs/worker-guard-go.md`, **read**).
- **Inference:** Claude Code on Windows runs hook commands through Git Bash when it is installed, so the `sh` shim may work unchanged. **Not verified.**
- The guard parses shell commands (`go/internal/shlex`, `roles/hooks/worker-guard.py`). Its rules assume POSIX paths, a POSIX shell and Linux tools: write-protected trees, `~/.local/lib/factory`, `/tmp`. Claude Code on Windows gives an agent a PowerShell tool next to the Bash (Git Bash) tool (**measured**: both were present in the Claude Code session on the assessed machine). **Inference:** a Windows worker could act through PowerShell unchecked until the guard gains PowerShell rules, which is new security-critical code and not only a review. This is the riskiest part of the port, because the guard is the main containment.
- The Go guard port (`go/`) builds with `CGO_ENABLED=0` and a fixed env (`guard_build_env`, `:2463`). Its `PATH` is `/usr/bin:/bin` and the toolchain path is `~/.local/go/bin/go` (`:2458`), both Linux-shaped (**read**).

## Finding 4: tests and CI

- `tests/harness.py` runs `bin/factory` as a subprocess with stub `herdr`, `gh` and `hc` scripts from `tests/stubs/` on `PATH` (**read**). The stubs are extensionless scripts. **Inference:** on Windows they would need `.cmd` or `.py` launchers to be found and run.
- On the assessed machine (**measured**):
  - `test_scrub_clean.py` errors on `import fcntl`.
  - `test_readme_sections.py` errors with `UnicodeDecodeError` (a cp1252 default encoding reading `README.md`).
  - `test_repo_hygiene.py` has 2 failures, also on a clean tree. One is the role-prompt byte budget. **Inference:** CRLF line endings from `core.autocrlf` inflate the byte count.
- CI runs only `ubuntu-latest` with Python 3.13 (`.github/workflows/tests.yml`, **read**). A Windows port needs a `windows-latest` job, or it will regress silently.

## Finding 5: project fit

- Hivemill is a public upstream project (`volekerb/hivemill`). Its docs target "a fresh Debian or Ubuntu machine" and it describes itself as "built for a single box" (README, **read**). A Windows port either goes upstream as a series of PRs, each through the factory's own reviewer, QA and judge gate, or it becomes a fork that drifts.
- `CONTRIBUTING.md` asks for an issue first for anything larger than a small fix, and for one change per PR (**read**).

## Finding 6: probe on Windows with stand-ins

To see how far the CLI gets, it was run on the assessed machine against a temporary `FACTORY_HOME`, with throwaway stand-ins on `PYTHONPATH`: a `fcntl` module whose `flock` does nothing, a `pwd` module built from the environment, and `os.getuid`/`geteuid` returning a constant. `FACTORY_AGENT=owner` was set because the identity guard takes a Claude Code shell for an agent pane. The stand-ins are **not** a port (the locks lock nothing), and no repository file was changed. All **measured**:

| Command | Result |
|---|---|
| `factory --help`, `init`, `config max_live_agents`, `project list`, `goal list`, `agents`, `whoami` | Work. `init` printed `initialised ...\db\factory.db` and the file exists |
| `factory res` | `FileNotFoundError: '\\proc\\meminfo'` |
| `factory tick` | `AttributeError: module 'os' has no attribute 'statvfs'` |
| `python3 ci/demo_seed.py --home <temp>` | `ValueError: path is on mount 'C:', start on mount 'D:'` (`relpath` across drives) |

Without the uid stand-in, every command fails in `derive_live_homes` (`bin/factory_cli.py:743`, `os.getuid()`). So the read-only core is close to working, and everything that runs the factory (spawn gate, tick, agents) is not.

## Options

Effort figures are estimates (**inference**), assuming an AI coding agent writes the code and the owner reviews it.

| Option | Result | One-time effort | Ongoing cost |
|---|---|---|---|
| **A. WSL2 Ubuntu** (chosen) | Everything works as designed, with no code changes | 1-2 hours to a database and the demo UI; about half a day more for herdr and the Claude and GitHub logins | None |
| B. Port the CLI core only | `init`, `project`, `goal`, `task`, `config`, `serve`, demo data on Windows. No agents | 2-4 days; 1-2 weeks more to get a useful share of the 392 test modules passing on Windows | Merge conflicts on each upstream sync unless upstream takes the changes |
| C. Full port, staged | Agents run on Windows through herdr. Sandbox stays Linux-only | 4-8 weeks; the PowerShell guard work has no clear upper bound | High: a Windows fork of a fast-moving codebase, with weaker containment |

## Proposed staging for option C

Not planned; kept for the record. Each stage is verified before the next.

1. **Import and core commands.** Lazy or fallback `fcntl`, `pwd`, `grp`, `termios` and `resource`. Make `factory init` create `db/factory.db` and get `project`, `config` and `serve` working on the demo data. Add a `windows-latest` CI job running a small module subset.
2. **herdr on Windows.** Install `herdr-windows-x86_64.zip`, then settle the named-pipe `herdr_socket` default and the `DEAD_SOCKET` / `_is_live_socket` equivalents. Then process listing (spawn gate, reaping), process-tree kill, and `factory up` / `factory agents` against the real herdr.
3. **Scheduling.** Task Scheduler entries for `factory tick` (every minute) and `factory up` (at logon), replacing `systemd/`.
4. **Hooks and guard.** Confirm the `sh` shim runs under Claude Code on Windows. Review every guard rule for Windows paths and shells, with reject and accept tests through the real hook entry point (`CONTRIBUTING.md`, "Guard changes").
5. **Sandbox.** Refuse `sandbox_roles` on Windows with a clear message. Document the reduced containment in `SECURITY.md`.

## Open questions for review

1. What exact `HERDR_SOCKET_PATH` value does herdr accept on Windows: a pipe name such as `\\.\pipe\...`, or a path it maps itself?
2. Is herdr's CLI JSON output (agents, workspaces, tabs, panes) identical on Windows?
3. Does Claude Code on Windows run hooks through Git Bash reliably for every role, including PreToolUse with stdin JSON?
4. Is a guard without the namespace sandbox acceptable on Windows, given that the guard is "a tripwire, not a sandbox" (`SECURITY.md`)?
5. Upstream or fork: will the maintainer accept Windows support, or is this a local fork?
6. ~~Is option A (WSL2) acceptable instead?~~ Answered: yes, chosen (see Decision). Questions 1-5 stay open and matter only if the port is revisited.

## Method

- Grep counts: `grep -rEc <pattern> --include=*.py bin web scout ci retro roles tests plugins`, summed per pattern.
- Code locations: Grep and Read on `bin/factory_cli.py` and the docs. No language server was used (none installed for Python).
- herdr facts: Grep over the local herdr checkout's `AGENTS.md`, `CHANGELOG.md` and `docs/`, plus the release-page screenshot.
- Probe (finding 6): stand-in modules in a scratch directory outside the repository, on `PYTHONPATH`.
- Not done: no real Windows port of Hivemill, no Windows build or run of herdr, no test of hooks under Claude Code on Windows, no review of each guard rule.
