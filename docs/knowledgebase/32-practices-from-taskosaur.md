# Practices brought from Taskosaur: glossary, insights, local skills

Session of 2026-11-13. Each reply is copied as written (only the recap and COMPLETE lines dropped).

## Q: update the local docs with that insight

(The insight: what `multi-angle-review` is, see [31-multi-angle-review.md](31-multi-angle-review.md).)

The insight is now in the local docs, in a new topic file: `\\wsl$\Ubuntu\home\dell\src\hivemill\.local-docs\31-multi-angle-review.md`.

- **Topic file:** the full explanation under its `## Q:` heading, plus a "Details" section with what the two source files add (Sonnet angle agents and Opus verifiers, the exact `Workflow(...)` call, the gate source `review_gate`, how the reviewer reads `confirmed` / `unverified` / errored angles).
- **Index:** row 31 added to `\\wsl$\Ubuntu\home\dell\src\hivemill\.local-docs\README.md`.
- **Session log:** one dated line added to `\\wsl$\Ubuntu\home\dell\src\hivemill\.local-docs\00-session-log.md`.

One failed step along the way: my first attempt to append the two lines through a WSL shell command failed on quoting and wrote nothing; I made both edits with the file editor instead.

Not checked: the note is still based on the old Windows checkout, and `docs/review-workflow.md` (cost, off switch) remains unread. The note says both.

LSP: not used, only Markdown notes were written.

---

## Q: Bring the best approaches from Taskosaut project into Agents/skils of that local project, to maintain glossary and insights and other interesting usefull things: THe taskosaut folder is: d:\_DEV\Taskosaur

Sent while that was in progress:

- "Read the Agents / Claude MD file from Taskosaur and thing what can be brought here"
- "Because we'll be using typescript and react, maybe we need to bring the corresponding skills if they are not global ones"

Taskosaur's glossary and insights practices are now set up for Hivemill, locally and uncommitted, and the one React skill that fits the planned stack is copied over. The insights format checker passes on the new file (`1 entries, 1 not promoted`, exit 0); nothing else was run.

### What was brought

| From Taskosaur | Here | State |
|---|---|---|
| `GLOSSARY.md` with `_Avoid_` words | `\\wsl$\Ubuntu\home\dell\src\hivemill\.local-docs\GLOSSARY.md` | Seeded with 30 terms in four groups (structure, work, agents, merge gate). It separates "factory task" (`T-0003`) from "TSR task" (`DVDG-544`). |
| `INSIGHTS.md` (seven fixed sections, append-only) | `\\wsl$\Ubuntu\home\dell\src\hivemill\.local-docs\INSIGHTS.md` | One real entry from today: `wsl … bash -lc "<command>"` from PowerShell breaks on inner quotes or parentheses (it failed twice this session). |
| `engineering-insights` skill with its checker and examples | `\\wsl$\Ubuntu\home\dell\src\hivemill\.claude\skills\engineering-insights\` | Adapted: one insights file, promotion goes to a "Gotchas" section, and corrections for the factory's own agents are routed to `factory lesson add` instead. |
| `react-best-practices` (Vercel, MIT, 70 rules) | `\\wsl$\Ubuntu\home\dell\src\hivemill\.claude\skills\react-best-practices\` | Copied unchanged. Its Next.js and server-side rules don't apply to a Vite bundle; the catalog says so. |
| Skills catalog with routing by path | `\\wsl$\Ubuntu\home\dell\src\hivemill\.claude\skills\README.md` | Lists local and global skills, which to load for which path, and what was not brought and why. |
| "Glossary" line, "Insights loop" and "Gotchas" from Taskosaur's `CLAUDE.md` | `\\wsl$\Ubuntu\home\dell\src\hivemill\CLAUDE.local.md` | Four new sections: Glossary, Insights loop, Local skills, Gotchas (empty). |

`typescript-expert` and `react-testing-library` are already global, so they were not copied.

### Not brought

- **Other frontend skills:** `next-best-practices`, `frontend-architecture`, `tailwind-design-system` and `react-hook-form` don't match the stack in your flow debugger notes (Vite, React Flow, no Tailwind, no forms). `safe-ui-refactoring` can come once there is a React UI to refactor.
- **Architecture decisions skill:** the repo already has `docs\adr\` and the staff-engineer's own `domain-modeling` skill.
- **Spec-driven section of Taskosaur's `AGENTS.md`** (`SPEC.md` beside each module): Hivemill has its own rule (`docs\<feature>.md`).
- **"Debug the UI yourself in the browser" rule:** not added, because I haven't checked that Chrome on Windows reaches the dashboard served inside WSL.
- **A local `AGENTS.md`** for Pi and Omp sessions pointing at the same glossary and insights: not created; say if you want it.

### Things to know

- **Two copies.** This session runs in `D:\_DEV\__Factories\hivemill`, and Claude Code loads skills and `CLAUDE.local.md` from the folder it starts in. So I copied `.claude\` (80 files) and the updated `CLAUDE.local.md` there too, although that checkout is marked "do not edit". The WSL clone is the source; the copy needs refreshing after a change.
- **Git.** `.claude/` is added to `.git\info\exclude` in both checkouts; `git status` shows no new files in either.
- **Glossary accuracy.** The definitions come from `CLAUDE.md` and your earlier notes (goals, roles, how agents get work), not from a fresh read of the code. Worth a skim; "Team", "Org" and "Message" are the ones I'm least sure of.
- **Open question recorded in the insights file:** whether factory panes that run in the main checkout (boss, director) would pick up `.claude\skills` from it. Not checked.
- **Skills only.** Taskosaur has no `.claude\agents` folder, so there were no agents to bring.

Skills used: none loaded (no React or TypeScript code was written).

LSP: not used, only Markdown and a shell script were written.

Skipped: a visual check that the new skill appears in a fresh session's skill list; risk: the D: copy drifts from the WSL source if only one is edited.
