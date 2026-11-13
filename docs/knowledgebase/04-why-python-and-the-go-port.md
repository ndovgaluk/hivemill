# Why Python, and the move to Go

## Q: Why was Python chosen for the implementation? Could another stack be used for the same?

The repo doesn't record why Python was picked in the first place. What it does record is that the project is **already moving off Python, to Go**. Here's what's documented, then my own view.

**What's documented** (`docs/adr/0001-language-policy.md`):
- **27 Oct 2026:** the owner asked for "more performant and safer code, go or rust". The decision was **Go** for performance- and security-sensitive parts, starting with the worker guard, the hook that runs on *every* agent Bash call. Measured: about 40 ms per call in Python, against a 10 ms floor just to start the interpreter. Rust was rejected as "heavier toolchain and slower builds, and no need that Go cannot meet."
- **11 Nov 2026 amendment (goal G-041):** the owner decided "all the code I want to write in go not python". The CLI, tick, web UI, scout and CI scripts are being ported to Go in stages. **No new Python files** are allowed in CI from that date. Python stays the default until each stage switches over.
- That's what most of the 27 upstream commits pulled during setup are: `T-1360: Go CLI registry, golden parity harness…`, `T-1361: Go task list…`, `T-1363`, `T-1364`, `T-1368`. The ADR also approves a pure-Go SQLite driver (`modernc.org/sqlite`) for this.
- The ADR is honest about the trade-off. A Go port alone doesn't fix the guard's security gaps, because they're logic bugs, not memory bugs. The real gain is the *differential gate*: both implementations must make identical allow/block decisions on a test corpus.

**Why Python probably came first.** This is my inference; nothing in the repo states it.
- **Nothing to install:** Python's standard library only, including built-in `sqlite3`, `argparse`, `http.server` and `subprocess`. On any Linux box you `git clone` and it runs, with no build step.
- **The work is mostly glue:** the factory calls git, gh, herdr and claude, writes SQLite rows, and serves a small web page. Python is quick to write for that.
- **Agents write the code:** the factory builds itself, and Claude writes and reviews plain Python well.

**Could another stack do it?** Yes. Nothing in the design is tied to a language: it's processes, one SQLite file, a timer and an HTTP page. Each option has costs:

| Stack | Fits well | Watch out for |
|---|---|---|
| **Go** (the chosen direction) | One static binary, fast start (matters for the per-call guard), easy concurrency, pure-Go SQLite | More verbose. Regex differences mean every guard pattern must be re-tested; the ADR's whole port plan is about this |
| **Rust** | Fastest, strongest safety | Slower to build and to write. The ADR requires a separate exception decision |
| **TypeScript/Node** | Large ecosystem; agents write it well | Needs a runtime and npm dependencies, against the "nothing to install" goal; slow start for the guard |
| **C#/.NET** | Strong typing; single-file publish | Large runtime. Linux-specific parts (namespaces, `/proc`, `fcntl`) need native calls |

Whatever the language, these stay the same: Linux only (systemd, namespaces, `/proc`), SQLite as the single state file, and the existing Python test suite as the reference that every port must match ("golden parity").
