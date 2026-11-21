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

## Q: Do the upstream changes since 2026-11-16 05:27 (our `a2232ea6`) contradict our workflow optimization? Is it safe to pull them and merge into our fork?

Answer of 2026-11-22. Checked with `git fetch upstream` and a trial merge in a throwaway worktree (removed afterwards); nothing merged, committed or pushed.

**Size.** `upstream/main` has 210 commits that our `main` lacks (the last common commit is `3eee0228` of 2026-11-13); 135 of them are from after 2026-11-16 05:27. About 936 files change. Most of it is Go-port work (parity tests, Go tick and spawn, `go/internal/store`) that our code does not touch.

**Conflicts.** 18 files conflict: `bin/factory_cli.py` (22 places), `bin/flags.json`, `.github/workflows/tests.yml`, `docs/README.md`, `docs/local-gate.md`, `go/internal/cli/cmd_s1.go`, `go/internal/factorydb/factorydb.go`, `go/internal/store/defaults_gen.go`, five Go goldens, `tests/test_db_layout.py`, `test_flags.py`, `test_mech_merge.py`, `test_shard.py`, `test_task_merged_externally.py`.

**Where upstream overlaps our workflow changes:**

| Area | Ours | Upstream | Verdict |
|---|---|---|---|
| Merge gate and GitHub checks | HM-52 `gate_ignore_pending_ci`: in local mode nothing waits for GitHub (judge, first review, coder restart, prcheck) | T-1634: in local mode only the checks named in `projects.required_checks` are waited for; T-1772 `judge_ci_gate=none` (judge reads no PR check); T-1802 `judge_review_gate=green` | Same goal, same lines of the judge (`judge` wait loop, mechanical merger). Not a contradiction, but has to be merged by hand with a defined order: `judge_ci_gate=none` first, then our key, then T-1634. Upstream only covers the judge; our key also covers first review, coder restart and prcheck. |
| Workspaces | T-0002..T-0010 worktree pool (`worktree_reuse`) | `task_clones` (a `git clone --shared` per task, off by default), T-1544 QA clone `<goal>-<task>-qa`, `factory clean` rewritten for clones | Real design clash: the pool is built on `git worktree`; with `task_clones=1` it does not apply. Our slug regexes (`worktrees_real()`) must take upstream's `-qa` suffix, and the `factory clean` pool step must sit inside upstream's new clone/QA cleanup. Safe while `task_clones=0` (default). |
| Hand-merged PRs | HM-65 `close_merged_externally` + `hand_merge_accept` | `task merged-externally` now calls `run_after_merge` and words the line "merge on main" | Compatible: ours already calls `run_after_merge`; keep ours, take the wording. |
| Schema | `SCHEMA_VERSION = 3` (goals.hold, HM-42), `worktree_pool` table | `SCHEMA_VERSION = 4` (`schedules` table) | Both must be kept: version 5 with both, in Python and `go/internal/factorydb`, plus the Go goldens and `base.sql` regenerated. |
| Tick | new steps: `tick_workflow` (engine), HM-38 boss wake, HM-44 halt, HM-42 hold, HM-65 hand merges, stale-unread alert | `TICK_UNITS` table and an optional Go tick (`tick_impl=go`, default `python`) | Fine with the Python tick (default). Under `tick_impl=go` our steps would not run; leave `tick_impl` at `python`. |
| Config/flags | `workflow_engine`, `workflow_ci`, `tsr_web_url`, `factory_halt`, `worktree_*`, `hand_merge_accept`, `coder_self_review` | `merged_go_proof`, `block_conditions`, `tick_impl`, `judge_*`, `task_clones`, ... | Only textual: both key lists are kept. |

Nothing upstream removes or reverts our engine (`go/internal/workflow`, `go/cmd/workflow` merge without conflict). All new upstream behaviour is behind switches that default to the old behaviour (`task_clones=0`, `tick_impl=python`, `judge_ci_gate=pr`, `judge_review_gate=passpass`).

**Is it safe?** Not as a plain pull: it does not merge cleanly. It is safe as a planned merge:

1. Work on `main` in the WSL clone with no goal or engine run active (a push to `main` is live in `~/factory` within a minute).
2. `git merge upstream/main`, resolve the 18 files by the table above; regenerate the Go defaults and goldens.
3. The merge touches risky paths (`SCHEMA`, `DEFAULT_CONFIG`, judge code, `.github/`), so run the full suite (sharded, about 30-44 min on this box, see `docs/local-gate.md`) and the Go checks, not just `ci/affected.py --quick`.
4. Push to `origin` only when green; keep `task_clones`, `tick_impl`, `judge_ci_gate`, `judge_review_gate` at their defaults until each is checked against our workflow.

Not checked: whether the merged tree passes the tests (no resolution was attempted), and whether upstream's `-qa` clone conflicts with our engine's builder naming (`coder-<task>`).

## Q: Did the upstream commits merged on 2026-11-22 bring performance improvements, and what was their purpose?

Answer of 2026-11-22, from the commit messages of `3eee0228..upstream/main` (210 commits; not measured on this box).

Yes, several, but most of the 210 commits are not about speed. About 55 are the Go port (Go versions of CLI commands, tick steps and web views, plus parity tests); the rest are safety and gate options. The speed and cost changes:

| Commit | What | Purpose |
|---|---|---|
| `86547b48` Token discipline | every role but the boss starts with a 200k context window (`CLAUDE_CODE_DISABLE_1M_CONTEXT`), compaction at 60%, command output capped at 20,000 chars, file reads at 15k tokens, MCP output at 8k; the boss keeps 1M; `hm-spend` reports cost by role and model | one day had used a week of the Claude budget: agents re-read 100k-1.7M tokens of context every turn |
| `348d80be` T-1777 | a `model_<role>` key for every role; judge, pm and researcher default to Sonnet | cheaper roles that don't need Opus |
| `2e31d10b` CI ~10 min | `ci/shard.py` runs 4 modules at a time per shard (`--jobs`, `SHARD_JOBS`); Python-vs-Go guard comparison and `go test -race` only in a weekly deep run; a push to main is classified against the previous head instead of always the full suite | a PR used 26 jobs, about 165 runner-minutes, and waited hours in the queue |
| `5c1e0c9b` T-1427 | a docs-only PR skips the heavy CI jobs | less CI for docs changes |
| `a6cab85f` lead handoffs | workers hand work to each other directly (cc the lead); the lead dispatches at once when idle workers sit next to waiting PRs | 20 panes sat idle while a PR waited, because every handoff went through the lead's 15-minute loop |
| `c96ff8c6` T-1622 / T-1599 | an idle-progress watchdog (`idle_watchdog`, default shadow): nudge, then relaunch fresh, then alert; a Cursor kickoff that was never accepted is resent | agents that stall without anyone noticing |
| `932c05a3` T-1552 | stuck-PR check with one status read per PR, no CI polling | fewer GitHub calls |
| `88afd4b1` T-1677 | the tick's PR title scan moves from GraphQL to REST; `gh_call_trace` logs GitHub calls per caller | GitHub API budget |
| `1eeff5f7` T-1772, `0b071a19` T-1802 | `judge_ci_gate=none` (the judge does not wait for PR checks), `judge_review_gate=green` (merge a green PR without reviewer/QA PASS) | shorter merge path; both off by default |
| `ab00766e` T-1679 | local gate run dir on disk, job count capped by RAM | the local gate passing on a green main |
| `5230e9ac` T-1698 | workers get on-disk Go/pnpm caches; the tick sweeps go-build leftovers | faster builds, no full /tmp |
| `1a9954bd` T-1641, `8eec4e1b` T-1585 | after a Claude usage cap, wait for three fresh below-cap readings; place workers by free RAM and load | fewer failed spawns |

What it does **not** fix: `ci/affected.py` is unchanged, so our engine's `--ci local` step still runs the selected modules one after another (INSIGHTS 2026-11-16). The new `ci/shard.py --jobs` shows how it could be run in parallel.

Effect on this fork once pushed: the context limits and the Sonnet defaults apply to agents started after the push (they are in the role settings and `DEFAULT_CONFIG`); the gate modes, `idle_watchdog=on` and `task_clones` stay off until switched on.

## Q: Will these upstream improvements be used in our new optimized workflow (the workflow engine)?

Answer of 2026-11-22, from the merged code (`46733ef2`). The engine (`go/internal/workflow`) starts its agents through `factory spawn coder` (builder) and `factory spawn reviewer` (`build.go`, `review.go`, `start.go`) and merges itself; it uses no lead, PM, QA or judge.

| Upstream change | Used by the engine? | Why |
|---|---|---|
| Token discipline: 200k window, compaction at 60%, output caps | **Yes, automatically** | in `roles/settings/coder.json.in` and `reviewer.json.in`, applied by `factory spawn` to every new builder and reviewer |
| On-disk Go/pnpm caches for workers (T-1698) | **Yes** | set at spawn for every worker |
| Usage-cap reopen after 3 readings (T-1641), workers placed by RAM/load (T-1585) | **Yes** | the spawn gate every `factory spawn` passes |
| `model_<role>` keys (T-1777) | **Available, nothing changes** | the defaults it changed are judge, PM, researcher, which the engine doesn't use; builder stays Sonnet, reviewer Opus. `factory config model_reviewer claude-sonnet-5-5` would make reviews cheaper (owner decision) |
| Idle watchdog (T-1622) | **Watches, does nothing** | covers coder and reviewer, but default `shadow` writes events only. Not checked: whether `on` (relaunch --fresh) would clash with the engine's own tracking of its builder; test before switching on |
| Faster GitHub CI (`ci/shard.py --jobs`, deep run, docs lane) | **Only with `--ci github`** | `--ci local` and `none` don't use GitHub CI |
| Judge gate modes (T-1772, T-1802), stuck-PR check, REST PR scan | **No** | the engine merges without the judge and, in local/none mode, without a PR |
| Direct handoffs / lead dispatch (`a6cab85f`) | **No** | the engine has no lead; it already hands work over itself |

Not improved: the engine's local test step (`go/internal/workflow/land.go` runs `ci/affected.py --run`, one module after another). Using `ci/shard.py --jobs` style parallelism there is a separate fork change.
