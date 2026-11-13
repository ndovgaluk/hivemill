# Windows + WSL2 setup

The full replies from the setup session, in order, each under the question that prompted it.

---

## Q: I have set the virtualization on in BIOS, let's continue

Hypervisor is present now. The `VirtualizationFirmwareEnabled=False` reading is normal once Hyper-V owns the CPU. Next step is installing Ubuntu (`wsl --install -d Ubuntu --no-launch`).

WSL2 is working now. Here's where things stand.

**Verified:**
- Ubuntu is installed and running as WSL **version 2**. It's Ubuntu 26.04.1 LTS.
- Python 3.14.4 and git 2.53.0 are already there, so no `apt-get` step is needed. The repo needs Python 3.11 or newer.
- systemd is already on (`systemctl is-system-running` returned `running`), so you can skip step 4 of `docs/getting-started.md` §6.0.
- WSL sees 12 CPUs and 31 GiB of RAM with the default limit. That's enough, so you don't need a `.wslconfig` for now.

**Your turn: create your Linux user.** This step asks you to type a password, so I can't do it for you. In PowerShell run:

```
wsl -d Ubuntu
```

Pick a username and password at the prompt.

**After that I'll:**
1. Clone the repo into the Linux filesystem (`~/src/hivemill`), not under `/mnt/d`. A fresh clone from GitHub won't include your uncommitted local changes: `CLAUDE.md`, `docs/getting-started.md`, `docs/research/windows-port.md` and the change to `docs/README.md`.
2. Run the sandbox check `unshare -r -n -m true` as your user. Ubuntu 24.04 and later may need the AppArmor tweak from SETUP.md.
3. Run a quick check, `python3 -m unittest tests.test_gate`.

---

## Q: All good, the user is dell and I have my password

The dev environment in WSL2 is ready, and one test module passes there.

**What I did:**
- **Sandbox check:** `unshare -r -n -m true` succeeded as your user `dell`, so the Ubuntu AppArmor tweak from SETUP.md isn't needed.
- **Clone:** the repo is at `~/src/hivemill`, which Windows Explorer shows as `\\wsl$\Ubuntu\home\dell\src\hivemill`. I cloned it from your D: checkout, so it starts at the same commit, `56da683 T-1262 (#553)`. Its `origin` points at `https://github.com/volekerb/hivemill.git`.
- **Uncommitted files:** I copied `CLAUDE.md`, `docs/getting-started.md`, `docs/README.md` and `docs/research/windows-port.md` over, so `git status` in WSL matches the D: copy. I left out `info.mhtml` and `info2.mhtml`, which look like scratch files.
- **Tests:** `py_compile` of the CLI passed, and `python3 -m unittest tests.test_gate` ran 49 tests, all OK, in 17.9 s. I haven't run the full suite or `ci/affected.py`.

**From now on, work inside WSL:**
```
wsl -d Ubuntu
cd ~/src/hivemill
code .            # VS Code with the WSL extension
```
You now have two separate checkouts: `D:\_DEV\__Factories\hivemill` and the WSL one. Edits in one don't show up in the other, so pick WSL as the one you work in.

Claude Code still has to be installed and logged in inside WSL, as the guide says. The Windows install can't run the factory. If you want to run a real factory (section 7), you'll also need `gh auth login` and herdr in WSL.

---

## Q: How to open the folder? What should I choose? (VS Code "Open Folder")

I installed VS Code's **WSL** extension (v1.104.7). Don't use **Open Folder**: on its own it browses Windows files, and Python, git and the tests would then run on Windows, where the CLI doesn't work.

**Option A, from the Ubuntu terminal (simplest):**
```
wsl -d Ubuntu
cd ~/src/hivemill
code .
```
The first run installs the VS Code server inside Ubuntu, which takes about a minute. Then a new window opens on the repo.

**Option B, from the VS Code window you have open:**
1. Restart VS Code so it loads the new extension.
2. Click the blue/green `><` button in the bottom-left corner, or press `F1` and pick **WSL: Connect to WSL using Distro… → Ubuntu**.
3. In the new window, choose **File → Open Folder**. Type `~/src/hivemill` (a Linux path, not `C:\...`), then click **OK**.

**How to tell it worked:** the bottom-left corner shows **WSL: Ubuntu**, and **Terminal → New Terminal** opens a bash prompt at `dell@MaximusX:~/src/hivemill$`.

When VS Code asks whether you trust the folder's authors, choose **Yes, I trust the authors**. That turns off the Restricted Mode shown in your screenshot.

---

## Q: (ran `code` and saw the VS Code server install)

The VS Code server installed fine and the compatibility check passed. But you ran `code` without the dot, so VS Code didn't open any folder (at most an empty window). Run it again with the dot, which means "this folder":

```
code .
```

A window should open on `hivemill`. In the bottom-left corner, check for **WSL: Ubuntu**. When asked whether you trust the authors, choose **Yes**.

If you don't want to type the full path again next time, VS Code keeps the folder under **File → Open Recent**. From the Ubuntu terminal, `cd ~/src/hivemill && code .` always works.

---

## Q: yes, all good now

Good, VS Code is now open on the WSL checkout, so the development setup is done. I also saved a note to memory: in later sessions, tests and commands run in WSL at `~/src/hivemill`, not in the D: checkout.

Two things are still left from the guide. You only need them to run a real factory (section 7), not for editing code and running tests:

1. **Claude Code inside WSL.** In the Ubuntu terminal run `curl -fsSL https://claude.ai/install.sh | bash`, then `claude` to log in. Your Windows install can't run the factory.
2. **GitHub CLI inside WSL.** Run `sudo apt-get install -y gh`, then `gh auth login`.

---

## Q: (Claude Code installed: "~/.local/bin is not in your PATH")

Claude Code is installed at `~/.local/bin/claude`, but your shell can't find it yet. Run the command the installer suggested in the Ubuntu terminal:

```
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
```

Then check it and log in:

```
claude --version
claude
```

Running `claude` the first time takes you through login. It shows a link to open in your Windows browser, and that works from WSL.

Do this in the terminal that's already open. I can't do it from here, because my shell has no effect on your open terminal. The `source` part makes the PATH change apply right away, and the `~/.bashrc` line keeps it for future terminals.

---

## Q: 2.1.322 (Claude Code)

`claude` now runs from your shell and reports version 2.1.322 (Claude Code).

Next:

1. **Log in:** run `claude`, follow the link in your Windows browser, then exit with `/exit`. Skip this if it already asked you to log in.
2. **GitHub CLI:**
   ```
   sudo apt-get install -y gh
   gh auth login
   ```
   Choose **GitHub.com → HTTPS → Login with a web browser**. When it asks, say **Yes** to using gh as git's credential helper, so `git push` from WSL works too.

---

## Q: All good now (Claude Code logged in)

Claude Code is logged in inside WSL: the screen shows Opus 5.5 · Claude Max in `~/src/hivemill`. The GitHub CLI isn't installed yet, though. I just checked and `gh: command not found` came back.

Open a second Ubuntu terminal, or exit Claude with `/exit`, and run:

```
sudo apt-get install -y gh
gh auth login
```

Choose **GitHub.com → HTTPS → Login with a web browser**, and **Yes** to using gh as git's credential helper.

---

## Q: how to open second Ubuntu terminal?

Any of these opens a second Ubuntu terminal:

- **Windows Terminal:** click the **˅** arrow next to the tabs and pick **Ubuntu**. You can also press `Ctrl+Shift+T` in an Ubuntu tab, which opens another tab of the same kind.
- **Start menu:** type `Ubuntu` and press Enter.
- **VS Code (the WSL window):** **Terminal → New Terminal**, or ``Ctrl+Shift+` ``. This is already Ubuntu, at `~/src/hivemill`.
- **Any PowerShell window:** type `wsl -d Ubuntu`.

New terminals usually open in your home folder (`~`). You can run `gh` from any folder, so that doesn't matter for this.

---

## Q: how to change dir?

Use `cd` followed by the folder:

```
cd ~/src/hivemill      # go to the repo
cd ~                   # go to your home folder (~)
cd ..                  # go up one level
cd -                   # go back to the previous folder
pwd                    # show the folder you're in now
```

To get to Windows drives, use `/mnt/c` and `/mnt/d`, for example `cd /mnt/d/_DEV`. Work on the repo itself in `~/src/hivemill`, though.

Press `Tab` to complete folder names: type `cd ~/src/hi` and press `Tab`.

---

## Q: (prompt shows /mnt/c/Users/Dell after `wsl -d Ubuntu`)

You're in Ubuntu now (`dell@MaximusX`). The prompt shows `/mnt/c/Users/Dell` because `wsl` keeps the Windows folder you started from. Go home and install gh:

```
cd ~
sudo apt-get install -y gh
gh auth login
```

`sudo` asks for the Linux password you set for `dell`. Nothing shows on screen while you type it; that's normal, so press Enter when you're done.

During `gh auth login`, choose **GitHub.com → HTTPS → Yes** (credential helper) **→ Login with a web browser**.

---

## Q: (E: Unable to locate package gh)

`gh` wasn't found because the package list on a fresh Ubuntu install is empty until you update it. Run the update first:

```
sudo apt-get update
sudo apt-get install -y gh
gh auth login
```

If it still says `Unable to locate package gh` after the update, add GitHub's own package source and install from there:

```
sudo mkdir -p -m 755 /etc/apt/keyrings
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
sudo apt-get update && sudo apt-get install -y gh
```

---

## Q: (gh: Logged in as ndovgaluk, credentials saved in plain text)

The GitHub CLI is set up in WSL. I checked:

- **gh 2.46.0** is logged in as **ndovgaluk**.
- git uses gh for credentials on `github.com`, so `git push` from `~/src/hivemill` will work.
- The "saved in plain text" warning is normal in WSL because there's no system keyring. The token is in `~/.config/gh/hosts.yml`, which only your Linux user can read.

**One thing to watch:** the token you pasted has very broad scopes, including `delete_repo`, `admin:org`, `admin:enterprise` and `admin:public_key`. That's fine for you working by hand. Before you run a real factory, where agents call `gh`, consider a token limited to `repo`, `workflow` and `read:org`. The repo's `scout/ghcred` module handles worker credentials, so read `docs/SETUP.md` on that first.

---

## Q: Can I change the key for interrupting you from ESC to something else, like Ctrl+Esc?

Yes. Esc no longer stops me; to interrupt, press **Ctrl+X, then Esc**. I set it up in both your Windows and Ubuntu Claude Code, but haven't tested the keys myself.

Ctrl+Esc isn't possible on Windows, because Windows opens the Start menu with it before the terminal sees the key. So I used a two-key sequence instead.

| Key | What it does |
|---|---|
| **Esc** | No longer interrupts me |
| **Ctrl+X, then Esc** (within 3 seconds) | Interrupts me (cancel) |
| **Ctrl+C** | Also interrupts. This is Claude Code's built-in interrupt key; I left it as is |
| **Ctrl+L** | Clears what you've typed in the input box |

**Files:**
- `C:\Users\Dell\.claude\keybindings.json`: added the two lines and kept your existing `ctrl+alt+g` binding.
- `\\wsl$\Ubuntu\home\dell\.claude\keybindings.json`: new file with the same two lines and nothing else. The `ctrl+alt+g` binding opens an Orca view, which I assumed only exists on Windows.

Both files are valid JSON. If Esc still interrupts, restart Claude Code so it reloads the file.

The binding I removed is Claude Code's "cancel" action on Esc. If you were also using Esc for something else in the input box, such as clearing the text, that stops too; use **Ctrl+L** to clear instead.

---

## Q: (`code .` → Permission denied)

From my session, interop is working: `cmd.exe /c ver` ran, and `Code.exe --version` started without an error. File permissions are fine too (`Code.exe` is `-rwxrwxrwx`, owner `dell`). So the problem is only in **that one terminal window**, not in WSL or VS Code generally.

**The likely cause is admin rights.** Your earlier VS Code screenshot had **[Administrator]** in its title bar, so you sometimes run things elevated. WSL keeps admin and normal sessions separate when it launches Windows programs. If that Ubuntu tab was opened from an **admin** Windows Terminal (or the other way round), launching Windows programs from it can fail with exactly this `Permission denied`.

**Quick test in that same terminal:**
```
cmd.exe /c ver
```
- **Also `Permission denied`:** that terminal's link to Windows is broken. Close it and open Ubuntu from a **normal**, non-admin Windows Terminal: Start menu → Terminal, not "Run as administrator". Then run `cd ~/src/hivemill && code .` again.
- **Prints the Windows version:** only VS Code is affected. Usually an elevated VS Code window is already running and blocks a normal launch. Close all VS Code windows, then run `code .` again.
- **Fails in every new terminal too:** run `wsl --shutdown` in PowerShell, then reopen Ubuntu. That restarts WSL and closes all Ubuntu sessions.

In general, don't run VS Code or Windows Terminal as administrator for this setup. Nothing here needs it, and mixing admin and normal windows causes errors like this one.

**Outcome:** you confirmed the terminal had been opened as administrator; with matching rights it worked.

---

## Q: How can I make the terminal to run as admin all the time?

Windows Terminal can do that for each profile:

1. Open Windows Terminal → **Settings** (`Ctrl+,`).
2. In the left sidebar, under **Profiles**, pick **Ubuntu**.
3. Turn on **Run this profile as Administrator** and click **Save**.

Do the same for **Windows PowerShell** if you want that elevated too. In `settings.json`, the same setting is `"elevate": true` in the profile.

**What changes:**
- Every new Ubuntu tab triggers a UAC prompt, and opens in a separate, elevated Windows Terminal window. Windows doesn't allow admin and normal tabs in the same window.
- `code .` from that terminal starts VS Code as administrator. That's consistent, so no `Permission denied`. But if a normal VS Code window is already open, you hit the same mismatch the other way round. Keep it all elevated or all normal.

**Things to weigh before doing it:**
- Inside Ubuntu, being "admin" changes nothing: you're still the `dell` user, and `sudo` works as before. Only **Windows programs started from WSL** (`code`, `cmd.exe`, `explorer.exe`) get admin rights.
- That matters for the factory. Agents run in WSL, and anything they start on the Windows side would run with admin rights. The factory's worker guard is built to keep agents inside Linux. Running elevated removes Windows' own safety net if something slips through.
- Nothing in this setup needs admin. If you only needed it for one task, run that one tab as admin (right-click → **Run as administrator**) and keep the default normal.

---

## Q: How can I make the Ubuntu in terminal open the hive factory folder by default instead of the root folder?

In Windows Terminal, set it on the Ubuntu profile:

1. **Settings** (`Ctrl+,`) → **Profiles → Ubuntu**.
2. Set **Starting directory** to:
   ```
   \\wsl$\Ubuntu\home\dell\src\hivemill
   ```
   Make sure **Use parent process directory** is unticked.
3. **Save**.

New Ubuntu tabs then open in `~/src/hivemill`.

**If it still opens in `~`:** some Ubuntu profiles launch through a command that ignores this setting. In that case, set the profile's **Command line** instead:
```
wsl.exe -d Ubuntu --cd ~/src/hivemill
```

**Alternative I wouldn't use:** adding `cd ~/src/hivemill` to `~/.bashrc` also works, but then *every* Ubuntu shell starts there, including VS Code terminals in other folders and `wsl` started from PowerShell. The Windows Terminal setting affects only that profile.

---

## Q: (coder-t-0002 blocked: "Author identity unknown", `go` not on PATH)

The coder hit two gaps in the WSL setup, both machine-level, so agents won't fix them themselves (correctly). The agents' PATH is fixed by the systemd units (`~/.local/bin:/usr/local/bin:/usr/bin:/bin`), and the factory's own Go build calls `~/.local/go/bin/go` directly.

I fixed both blockers. Its work is intact, and a respawned coder can continue.

| Blocker | Fix | Check |
|---|---|---|
| `git commit`: "Author identity unknown" | Set the WSL git identity to **`Nick <…+<your-login>@users.noreply.github.com>`**, your **GitHub no-reply address**. These commits go to your public fork, so I didn't use your private email | In the coder's worktree, `git var GIT_AUTHOR_IDENT` returns that identity |
| `go` not on PATH (needed to regenerate the Go defaults and goldens) | Installed **Go 1.27.3** exactly as `docs/go-toolchain.md` says (checksum `OK`, into `~/.local/go`), and linked `go` and `gofmt` into `~/.local/bin`, which is on the agents' systemd PATH | With the agents' exact PATH, `go version` → `go1.27.3 linux/amd64` |

**The coder's staged work is still there** in `~/factory/worktrees/G-001-T-0002`: `bin/factory_cli.py`, `bin/flags.json`, `go/internal/cli/cmd_s1.go`, `tests/test_flags.py`.

**Next step:** tell the factory the blockers are gone. In the **boss** pane, write:
> The git identity is set and Go 1.27.3 is installed and on the agents' PATH. coder-t-0002's blockers (M26) are fixed; please have the lead respawn the coder on T-0002.

**Not verified:** whether the factory gives coders their own git config. A recent upstream change (T-1264) makes it honour the owner's identity. My check ran in a normal shell, not inside an agent's environment, so the respawned coder's first commit will show whether it works.

Go install commands used (from `docs/go-toolchain.md`):
```
curl -fsSLO https://go.dev/dl/go1.27.3.linux-amd64.tar.gz
echo "65efbc80fdc1fa2cd2631cad5b481777a68e8725f34e89f50fc6ac714e379b40  go1.27.3.linux-amd64.tar.gz" | sha256sum -c
rm -rf ~/.local/go && mkdir -p ~/.local
tar -C ~/.local -xzf go1.27.3.linux-amd64.tar.gz
ln -sf ~/.local/go/bin/go ~/.local/bin/go
ln -sf ~/.local/go/bin/gofmt ~/.local/bin/gofmt
```
