# The staff-engineer role

## Q: What's the purpose of the staff-engineer, in detail?

The **staff-engineer** is the factory's **on-demand senior engineer and architect**, a consultant for the people who run the work. Its role file sums it up: *"You advise and never decide. You write no code."*

**What it's for:**
- **Answering technical questions** from the code, PRs, CI logs and the factory's state. One short session per question.
- **Unblocking leads**, e.g. a CI failure nobody understands, a PR rejected for reasons the coder can't fix, or a tricky bug.
- **Reviewing plans and designs** on request, with a recommendation and reasons.
- **Helping the director decide** between options.
- **Language advice** follows ADR 0001: Go first, Rust only with an exception ADR.

**Who can call it and how:**
- Only the **lead, director and boss**: `factory msg staff-engineer "<question>" "<context>" --kind request`. Workers (coders, QA and so on) are refused by `factory msg`; they ask their lead.
- It's **not always running**. It's spawned when a question arrives and closed after it finishes (`factory done`).

**One session:**
1. It reads the question from its inbox.
2. It looks up what it needs: goals, tasks, plans, `gh pr view/diff/checks`, `git log/show`, `git show origin/<branch>:<file>`.
3. It **replies to the asker** in the format requested.
4. Advice worth keeping becomes an **ADR-style report** (context, options, recommendation, consequences) via `factory report`.
5. Questions that need research, builds or measurements aren't answered on the spot. It replies with a **proposed task** (goal, role, scope) for the director or lead to staff, and any code goes in as snippets inside a proposed coder task.

**Decisions stay with their owners:** merges → judge; staffing and priorities → director; task order → lead; specs → pm; verdicts → QA and reviewer.

**What it may never do:** write or edit files, commit, push, touch GitHub PRs, run checkouts or pulls in `~/factory`, merge, record verdicts, spawn agents, change config, or create goals, tasks or plans. Its settings block these as well.

**Its toolkit** is richer than other roles':
- vendored plugins: `feature-dev` (explore, clarify and architecture phases only), `pr-review-toolkit`, and `staff-engineer-skills` (systematic debugging, architecture improvement, domain modeling, codebase design, differential review);
- built-in skills: architecture, system design, code review, debugging, simplify;
- up to 3 parallel subagents.

**When it's useful for you:** before giving the boss a big or risky goal, you can say *"ask the staff-engineer whether this design is sound first"*. The boss forwards it, and you get a reasoned recommendation before any code is written.

**Seen in G-001:** the lead consulted it on T-0003/T-0004 before spawning their coders; it found two blockers in T-0003 (a race test that couldn't fail and a guard test that asked for something impossible), and the lead fixed both specs before any coder started.
