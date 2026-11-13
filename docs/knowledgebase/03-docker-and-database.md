# Docker and the database

## Q: Can we run Docker containers for the factory in Ubuntu? Do we need to install anything else, like a DB server?

No to both: you don't need Docker or a database server. Two small pieces were still missing in Ubuntu at that point (herdr and the "linger" setting), plus one decision about the fork.

**Docker:** the factory doesn't use containers. Agents run as Claude Code processes in herdr terminal panes, one pane per agent, and its optional sandbox uses Linux user namespaces, which already work in your Ubuntu. The repo has no Dockerfile or compose file. Its own design notes (`docs/adr/0002-sandbox-runtime-v3.md`) treat Docker as a **risk**: an agent that can reach `/run/docker.sock` effectively has root on the machine. So it's better to leave Docker uninstalled in this Ubuntu.

**Database:** it's **SQLite**, a single file at `~/factory/db/factory.db` that Python's standard library reads and writes. There's no server to install or run, and `factory init` creates the file.

**Status of the requirements for a real factory** (section 7.1 of `docs/getting-started.md`, checked in Ubuntu):

| Needed | Status (then) |
|---|---|
| Python 3.11+, git | ✅ 3.14.4, 2.53.0 |
| Claude Code, logged in | ✅ 2.1.322 |
| gh, logged in | ✅ ndovgaluk |
| systemd | ✅ running |
| User namespaces (sandbox) | ✅ ok |
| **herdr** (the terminal multiplexer that hosts the agents) | ❌ not installed → later installed (0.9.5, checksum OK) |
| **Linger** (keeps your user's services running with no terminal open) | ❌ `Linger=no` → later `sudo loginctl enable-linger dell` |

**One decision before installing: the fork.** The installer clones **volekerb's** repo into `~/factory` by default, which becomes a second, live copy separate from your dev clone `~/src/hivemill`. To have the factory build **your fork**, pass `--repo-url https://github.com/ndovgaluk/hivemill.git` (the installer supports it).

**Also keep in mind:**
- A real factory runs many Claude agents and uses up your Claude Max usage.
- WSL2 shuts down when nothing is using it, which stops the factory. It needs a terminal open, or a keep-alive.

---

## Q: (install herdr, enable linger, run install.py --check)

All three steps are done, and the installer's read-only check passed.

1. **herdr** downloaded from its official release, checksum verified (`sha256sum -c` → `OK`), installed to `~/.local/bin/herdr` → `herdr 0.9.5`.
2. **Linger** is on (`loginctl show-user dell -p Linger` → `Linger=yes`).
3. **`install.py --check`** finished with `exit=0` and changed nothing:

| Check | Result |
|---|---|
| python3, git, gh, gh-auth | ok |
| herdr 0.9.5 | ok |
| claude 2.1.322, credentials | ok |
| systemd user session | ok |
| RAM 31.3 GiB, 12 CPUs | ok, **suggested max agents: 6** |
| go | warn: not found. It's optional; the worker guard then uses the Python version (later installed for G-001) |

herdr install commands (from the guide):
```
mkdir -p ~/.local/bin
HB=$(mktemp)
curl -fsSL -o "$HB" https://github.com/herdrdev/herdr/releases/download/v0.9.5/herdr-linux-x86_64
echo "14d9e8bc8b4a9e0118d77c32266f76d461f09b40342eb23752960bd89f59929d  $HB" | sha256sum -c -
install -m 755 "$HB" ~/.local/bin/herdr
```
