# Running natively on Windows once the Go port is done?

## Q: Once the transformation to Go is completed, will I be able to run the factory on a Windows machine without WSL or Linux?

Not automatically. Moving to Go removes one obstacle (Python's Linux-only imports such as `fcntl`), but most of the reasons the factory is Linux-only have nothing to do with the language. The research doc in this repo (`docs/research/windows-port.md`) lists them, and a Go version would still face all of these:

| Linux dependency | Why Go alone doesn't fix it |
|---|---|
| **Worker sandbox** (Linux namespaces: `unshare`, nsbox) | Windows has no equivalent. The doc's decision: "containment gets weaker". |
| **Worker guard rules** | Written for **bash** commands. Agents on Windows run PowerShell, so the rules would need rewriting. The doc says that work "has no clear upper bound". |
| **systemd** units and timer (`tick` every minute, `up` at boot) | Would need Task Scheduler instead. |
| **`/proc`, process trees, file modes (`0600` tokens), file locks** | Go can do these on Windows, but only if the port is written to be cross-platform on purpose. |
| **herdr** (the terminal host for the agents) | It has a Windows build, but uses named pipes instead of Unix sockets. Whether its output matches the Linux version is listed as **not verified**. |

**Is anyone working on Windows support?** Not that I can see in the repo:
- The research doc's decision is **option A: WSL2**. It rates the full Windows port at **4–8 weeks**, with high risk: "a Windows fork of a fast-moving codebase, with weaker containment".
- The Go migration goal (G-041 in ADR 0001) is about language, speed and safety. It doesn't mention Windows.
- `CLAUDE.md` says: "Do not add Windows compatibility shims unless asked."

**So:**
- Once the Go port is done, a Windows version becomes *easier*: one compiled `.exe` and no Python. It still needs its own project (sandbox, PowerShell guard rules, scheduler, herdr pipes), and that project isn't planned.
- If you want it, you could carry it in your fork, but you'd be keeping a Windows variant in step with an upstream that changes daily.
- **WSL2 remains the practical answer.** It *is* running on your Windows machine; only the factory lives in the Linux layer. Your apps, browser and VS Code stay on Windows.

What I can't tell you: whether the upstream owner plans Windows support later. Nothing in the repo says so either way.
