# Working on another project

## Q: I don't see a separate projects tab in herdr. How can I allocate tasks for another project?

herdr has no project view, and that's expected: the factory lays herdr out **by goal, not by project**. The `spaces` list shows **HQ** (boss, director, scout) and one workspace per goal (`G-001 Opt-in wor…`). Projects exist only in the factory's database. When a goal for another project starts, its own workspace (`G-002 …`) appears in the same list.

You also don't allocate tasks yourself: you give the boss a **goal for that project**, and the pm writes the tasks.

**Steps for a second project, e.g. Taskosaur:**
1. **Clone it inside Ubuntu** (agents can't work well on `D:\`):
   ```
   cd ~/src && git clone https://github.com/ndovgaluk/Taskosaur.git
   ```
2. **Register it** from a plain Ubuntu terminal (not an agent pane):
   ```
   factory project add taskosaur --name "Taskosaur" --repo ~/src/Taskosaur --gh ndovgaluk/Taskosaur --base master --required-checks "<its CI job name>"
   factory project list
   ```
   `--base master` because Taskosaur's main branch is `master`; `--required-checks` = the CI job(s) the judge must see green (check `.github/workflows/` for the job names; Actions must be enabled on that repo).
3. **Give the boss a goal for it:** "New goal for project taskosaur: …". The director staffs a team and a new herdr workspace appears.

**Before giving the factory Taskosaur or MTS, decide these:**
- **Shared ports and databases.** With mirrored networking, Ubuntu and Windows share `localhost`. Taskosaur's tests and dev stack use Postgres/Redis and ports 4000/4001; agents running them in WSL could **hit your real Windows databases** or clash with your running stack. Give the factory copy its own `.env` with a separate test database and different ports first.
- **Secrets.** The repo needs `.env` files that aren't in git; the factory's coders would need a safe, separate one.
- **Install cost.** Each coder task runs `npm install` in a fresh worktree until G-001 (worktree reuse) lands — a reason to finish G-001 first.
- **Two worlds.** You develop Taskosaur on Windows with your own agents (C1–C4, TSR flow); factory PRs would arrive on GitHub in parallel. Decide which work goes where to avoid both touching the same files.

**Also visible in the screenshot (G-001 progress):**
- `coder-t-0002` opened **PR #1** on the fork and was waiting for CI and `factory prcheck`. Its first two `git push` attempts were blocked by the worker guard because the command form wasn't exactly `git push origin HEAD:factory/t-0002`; that's the guard working as designed.
- The lead consulted the **staff-engineer**, who found two blockers in T-0003's spec; the lead fixed both specs and several T-0004 details before any coder started.

---

## Q: So the boss sits on top of all projects under src and identifies them by name, and I need to name the project each time I give the boss a new goal?

Almost. Two corrections, then the practical answer.

**1. The boss doesn't look at `~/src` at all.** It knows only the projects **registered in the factory's database** (`factory project list`). A folder under `~/src` is invisible to it until someone runs `factory project add`; a registered project's repo can live anywhere (hivemill's is `~/factory`, not under `~/src`). Each project has an **id** (e.g. `hivemill`), a repo path, a GitHub repo, a base branch and its required checks.

**2. The boss must put exactly one project on every goal.** Its role file (`roles/boss.md`) creates goals with `factory goal new --title … --project <id> …`, and step 1 is to check whether your request fits an **existing** goal first (then it updates that goal instead of creating a duplicate). It also says "a new repo or area needs `factory project add` first", so it won't invent a project.

**So, do you have to name the project each time?**
- **Best practice: yes**, start with it: *"New goal for project taskosaur: …"*. It's one word and removes all guessing.
- **If you don't**, the boss works it out from the request (with only `hivemill` registered there's nothing to choose), and its instructions say to ask you when the answer would change the outcome, which an ambiguous project does. I haven't seen how it handles an unclear project in practice, so naming it is the safe route.
- **Follow-ups on running work** don't need it: "for G-001, also …" already ties to that goal's project.

**One project per goal.** A change that spans two repos (e.g. a Taskosaur API change plus the MTS client using it) becomes **two goals**, one per project. Tell the boss they depend on each other so it says so to the director, who can order them.
