# Fork and upstream

The full replies, in order, each under the question that prompted it.

---

## Q: I'll be making changes to that repo and will push the changes to a remote repo. Fork the repo or create my own remote repo?

**I recommend a fork.** Here's what I found:

- `volekerb/hivemill` is public, MIT-licensed, and your account (`ndovgaluk`) only has **READ** access. You can't push to it, so you need your own remote either way.
- You don't have a fork yet.

**Why a fork fits best:**
- It keeps the link to the original repo, so you can pull in new releases (`gh repo sync`) and send changes back as pull requests if you ever want to.
- One command sets it up. `gh repo fork` creates the fork, renames your current `origin` to `upstream` and adds your fork as `origin`. After that, a plain `git push` goes to your copy.

**When your own new repo is better:** if the code must be **private**. A fork of a public repo is always public on GitHub. A private repo works the same way locally: you'd have `origin` pointing at your private repo and `upstream` at volekerb. You just lose the GitHub "fork" link and the one-click sync.

**Two things to know for Hivemill specifically:**
- If you later run the factory against your copy, it opens its own PRs and merges them there. Both options support that.
- GitHub turns off Actions on new forks by default. You'd need to enable them in the fork's **Actions** tab, or the CI checks the merge gate waits for will never run.

---

## Q: Ok, let's do the fork

The fork exists and the remotes are set up (gh 2.46 doesn't rename an existing `origin` itself, so I set them by hand):

| Remote | Points to | Used for |
|---|---|---|
| `origin` | `https://github.com/ndovgaluk/hivemill.git` (your fork) | `git push` and `git pull` |
| `upstream` | `https://github.com/volekerb/hivemill.git` | pulling in the original author's updates |

- Local `main` tracks `origin/main`. `gh` defaults to your fork (`gh repo set-default` → `ndovgaluk/hivemill`), so `gh pr create` opens PRs on your fork, not upstream.
- The fork's Actions setting reads `enabled: true` through the API. GitHub sometimes still wants a one-time click on **"I understand my workflows, go ahead and enable them"** in the fork's **Actions** tab.

**Your local copy is 27 commits behind.** Upstream has moved on since your D: checkout (latest is `8d616f6 T-1368 …`). One of those commits changes `docs/README.md`, which you also edited locally and haven't committed. To update while keeping your edits:

```
git pull --autostash
```

If both sides changed the same lines, git marks a conflict in `docs/README.md` and keeps your edits in the stash, so nothing is lost.

**Day to day:**
```
git checkout -b my-change          # work on a branch
git push -u origin my-change       # goes to your fork
gh pr create                       # PR inside your fork
git fetch upstream && git merge upstream/main   # pick up upstream updates
```

---

## Q: Update the project agents file to deal with the Ubuntu repository and when committing/pushing code do that to the remote fork repo

I added the rules in a new `CLAUDE.local.md` instead of editing `CLAUDE.md`. Claude Code reads it alongside `CLAUDE.md`, but it stays out of git, because these rules contain your fork name and `~` paths, which the repo's public-text scanner (`tests/test_scrub_clean.py`) flags in tracked files.

The same file is in both copies:
- `\\wsl$\Ubuntu\home\dell\src\hivemill\CLAUDE.local.md`, which Claude Code started in WSL will use.
- `D:\_DEV\__Factories\hivemill\CLAUDE.local.md`, which Windows sessions use.

**What it tells agents:**
- **Work in Ubuntu:** the working copy is `~/src/hivemill` in WSL. Edit, test, commit and push only there, not in the D: checkout. From a Windows session, run repo commands through `wsl -d Ubuntu -u dell --cd ~/src/hivemill -- bash -lc "..."`.
- **Push to your fork:** push only to `origin` (`ndovgaluk/hivemill`) and never to `upstream` (`volekerb/hivemill`, fetch only). Open PRs on your fork, and take upstream updates with `git fetch upstream` plus a merge.

**Keeping it out of git:** added to `.git/info/exclude` in both copies; `git check-ignore` confirms it's ignored.

---

## Q: Will I be able later to get latest changes from upstream main into my fork?

Yes. Your clone has `upstream` set to `volekerb/hivemill`, so you can pull in their changes whenever you like. There are three ways.

**1. From the WSL terminal (the usual way):**
```
cd ~/src/hivemill
git checkout main
git fetch upstream
git merge upstream/main        # or: git rebase upstream/main
git push origin main           # update your fork on GitHub
```

**2. With gh, in one command:** this updates your fork on GitHub directly, then you pull it locally.
```
gh repo sync ndovgaluk/hivemill --source volekerb/hivemill
git pull
```

**3. On the GitHub website:** open your fork and click **Sync fork → Update branch**, then run `git pull` locally.

**What to expect:**
- If you haven't changed the same lines as upstream, the merge just goes through.
- If you have, git stops and marks a conflict in those files. You choose which version to keep, then commit.
- Do your own work on branches (`git checkout -b my-feature`) and keep `main` close to upstream. Then syncing `main` stays clean, and you merge it into your branches when you need it.
- Option 2 works only while your fork's `main` hasn't diverged from upstream. Once you commit your own changes to `main`, gh refuses unless you pass `--force`, which would throw away your commits. Use option 1 then.

---

## Q: Can we add an extension for the /com-tsr skill: "pulltofork" that syncs upstream into the current fork on disk?

I added a `pulltofork` mode to the `/com-tsr` skill and put the skill in Ubuntu as well.

**Usage**, in Claude Code inside `~/src/hivemill`:
```
/com-tsr pulltofork          # bring upstream's main into your local main
/com-tsr pulltofork push     # same, then push main to your fork on GitHub
```

**What it does:**
1. Checks that `upstream` exists and fetches it.
2. Makes sure you're on the default branch (`main`).
3. Merges `upstream/main` into your local `main`. It fast-forwards when it can, and otherwise makes a merge commit. It never rebases, resets or force-pushes.
4. With `push`, it pushes to `origin` (your fork), never to `upstream`.

It stops and asks you when there's no `upstream` remote, you're on another branch, a file you've changed locally is also changed upstream, the merge has a conflict, or the push is refused. It doesn't use Taskosaur and doesn't need a `.tsr` file.

---

## Q: /com-tsr pulltofork push

Your local copy is now level with upstream. The push had nothing to send: your fork on GitHub was already at upstream's latest commit.

| Step | Result |
|---|---|
| Upstream | `upstream` = `volekerb/hivemill`, default branch `main` |
| Pulled | `56da683..8d616f6`, **27 commits**, fast-forward with no merge commit. Latest: `8d616f6 T-1368: write-mode golden harness…`, `789d7c0 T-1363: Go inbox read forms…`, `763a6e9 T-1361: Go task list, task ready, goal list` |
| Push | `git push origin main` → "Everything up-to-date", fork stays at `8d616f6` |
| Your edits | Still uncommitted and back in place. `docs/README.md` has your 2 added links plus upstream's new v0.4.0 link |

**What I changed along the way:** your local `docs/README.md` edit overlapped the upstream change, so the skill stopped and asked. Your real edit was 2 lines; the file only looked fully rewritten because it had Windows (CRLF) line endings from the D: copy. With your OK I converted the copied docs to Linux (LF) endings, stashed the README edit, fast-forwarded, and re-applied the edit cleanly.
