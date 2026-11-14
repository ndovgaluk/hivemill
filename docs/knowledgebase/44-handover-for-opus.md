# Handover for Opus 5.5 (written 2026-11-14 23:30 by Fable 5.2)

The owner must finish the project tomorrow and has no Fable until about 2026-11-19. This file is the work order. Read it fully, then `CLAUDE.local.md` (rules), `GLOSSARY.md` (section Workflows) and `INSIGHTS.md` in this folder.

## State right now

- `main` of the fork `ndovgaluk/hivemill` is at `e95bf31` and green on GitHub at `7736174`/`75e0b2b` (later pushes not checked). The installed factory `~/factory` fast-forwards itself to `main` within a minute of every push.
- The factory is idle: only boss and director are alive, no open goal. `workflow_engine` is `on`, `worktree_reuse` 1, project `hivemill` points at `~/factory` and `ndovgaluk/hivemill`.
- The workflow engine works for: start, one builder, build each child, a review per child (run G-006: two children built and reviewed in 8 minutes). Never run for real: a review that asks for changes, and the steps after a merge (commit links, story comment, Done, mail to the boss).
- Uncommitted in `~/src/hivemill` (branch `main`): this folder's notes of tonight, `GLOSSARY.md`. Commit them with the first docs push.

## Rules that override habits (all in `CLAUDE.local.md`)

1. No goal through the old workflow and no story run that ends in the old pull-request gate until HM-34 is done. If the boss proposes a goal: "record it, do not start it".
2. Local work: local tests green, then merge into `main` in the WSL clone and `git push origin main`. No pull request, no waiting for GitHub Actions. Never force-push, never push to `upstream`.
3. Commit and push only when the owner asks. Say in the reply which tests ran and which did not.
4. Never write into `~/factory` (the tick alerts within a minute). Work in `~/src/hivemill` or a worktree beside it (`git worktree add ~/src/hivemill-<name> -b <branch> origin/main`). Other sessions use the same clone: never switch the branch of a worktree you did not create.
5. Every feature must be trackable in the web UI; say so in the task when it is left out.
6. Do not copy the Windows global Claude config into WSL `~/.claude`: the factory's agents share it.
7. Commands from Windows: write a script and run `wsl -d Ubuntu -u dell -- bash <script>`. Go is `~/.local/go/bin/go`; no C compiler, so no `-race`. LSP does not resolve Go over `\wsl$`; use the compiler, `go vet` and the tests.

## Work order for tomorrow

Do them in this order. Each TSR task is self-contained; read it with all its comments first.

1. **HM-51** (in progress with another Opus session): measure the local gate at 4, 8 and 12 shards, switch project `hivemill` to local mode, prove a pass and a fail, write "This factory" in `docs/local-gate.md`. Its step-1 comment is done and is good.
2. **HM-52**: nothing waits for GitHub in local mode (merge gate, first review, the coder's pre-check). Include the two extra findings from HM-51's comment: `judge_wait_ci` still polls pending checks, and a failed local run must reach the coder or builder, not only the lead. This is the big time saver: in run G-006 the pre-check ran the full suite serially for 47 minutes because `ci/affected.py` answered FULL for a Go test file.
3. **HM-54**: the engine finishes without a pull request (config `workflow_finish` = `push`). It needs one agent text, `workflows/prompts/builder-gate-failed.md`. Fable is not available: write it yourself in the style of `workflows/prompts/builder-findings.md`, keep it under 20 lines, and say in the task comment that Opus wrote it.
4. **Boss wake bug** (no TSR task yet; create one under DVDG-539 first): `has_unsent_input` in `bin/factory_cli.py` treats an old sent prompt line and the empty prompt above Claude Code's status bar as a draft, so the tick never wakes the boss (director's message M682 has the pane text). Fix: only the last prompt line counts, status-bar lines below it are ignored; test built from that real pane text in `tests/test_boss_wake.py`; a draft must still block (test it).
5. **First full story run** with `workflow_finish push` on a small prepared story: watch it to Done in Taskosaur. Start with `factory wf start --story KEY` (the project is taken by default). Follow with `factory wf status --goal G` and `factory wf incidents`. To abandon a run: `factory goal status G cancelled` and `factory task update T --status cancelled`; the engine closes it on the next tick.
6. **HM-53** (Settings rows for the merge gate), then the UI tasks in this order: HM-47 (clear states), HM-50 (diagram per workflow), HM-44 (urgent stop), HM-42 (goal controls), HM-45 (TSR links). HM-47, HM-50 and HM-42 begin with design questions for the owner: ask them in one message, with a recommendation for each.

Not for tomorrow: HM-46 (waiting and polling analysis), HM-29, TSK-597, TSK-588, TSK-589.

## Known engine defects not fixed

- The engine's Go module is not fetched on a fresh factory (build fails offline); worked around by hand with `go mod download` into `~/.local/lib/factory/go/mod`.
- `factory stop --now` can fail with `close-failed` when an agent sits in a long foreground wait; the tick retries every 300 s.
- `factory wf resume` refuses a run that is `building`; there is no `factory wf cancel`.
- Commit links in Taskosaur work per epic now (TSK-604 is live); the Hivemill epic DVDG-539 has its repository set.

## What to tell the owner at the end of each task

What changed, the commit hash, which tests ran, what is live in the factory, and the one next step. Use `/me` when asked whether you need them.
