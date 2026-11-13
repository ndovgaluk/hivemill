# Hivemill

Hivemill is a self-hosted software factory: AI coding agents in fixed roles plan, build, check and merge work on registered repositories. This glossary fixes the words used for the factory, and separates them from the same words in Taskosaur (TSR), where the owner's own tasks live.

Local file (not committed). Maintain it with the `domain-modeling` skill; this path replaces that skill's default of a root `GLOSSARY.md`. Definitions come from the repo docs and the notes in this folder as of 2026-11-13.

## Structure

**Factory**:
One Hivemill install: the `factory` CLI, one database and the agents it runs.
_Avoid_: Hive, swarm, system

**Factory home**:
The directory that holds one factory's database, worktrees and runtime files (`~/factory` by default).
_Avoid_: Live home (only for the real one, as opposed to a test or demo home), install dir

**Owner**:
The person the factory works for; talks to the boss and can override.
_Avoid_: User, admin, human

**Project**:
One repository registered with the factory; every goal belongs to exactly one.
_Avoid_: Repo (when the registration is meant), TSR project

**Org**:
One of the two agent organizations sharing a factory, named after its runtime (`claude`, `cursor`); every goal belongs to one.
_Avoid_: Organization (that is the TSR tenant), team

**Runtime**:
The agent program an org runs: Claude Code or Cursor Agent.
_Avoid_: Engine, backend, model

## Work

**Goal**:
One outcome the owner asks the factory for, with an intent and checkable success criteria (`G-001`).
_Avoid_: Epic, story, request, feature

**Success criterion**:
One numbered, checkable statement of a goal that must be true when the goal is done.
_Avoid_: Acceptance criterion (that belongs to a factory task), requirement

**Plan**:
The pm's breakdown of a goal into factory tasks with dependencies.
_Avoid_: Roadmap, backlog

**Factory task**:
One unit of work inside a goal, usually one PR (`T-0003`); say "factory task" whenever a TSR task could be meant.
_Avoid_: Ticket, issue, TSR task

**TSR task**:
A task in Taskosaur (`DVDG-544`), the owner's own tracker; not known to the factory.
_Avoid_: Factory task, ticket

**Spec**:
The text of a factory task that says what to build; it lives in the database and changes only with the worker stopped.
_Avoid_: Description, brief, prompt

**Acceptance criteria**:
The checkable items of one factory task that QA verifies.
_Avoid_: Success criteria (those belong to the goal)

**Audit**:
The pm's end-of-goal check of every success criterion against evidence; gaps become follow-up tasks.
_Avoid_: Review, QA, retro

**Lesson**:
A recorded correction for the factory's roles (`L-001`), kept in the factory database.
_Avoid_: Insight (that is a local note in `INSIGHTS.md`), rule

## Agents

**Role**:
A fixed job in the factory with its own prompt, permissions and default model (boss, lead, coder, …).
_Avoid_: Agent (that is one running instance), persona

**Agent**:
One running instance of a role, named after its work (`coder-t-0003`, `lead-g-001-a`).
_Avoid_: Role, bot, session

**HQ role**:
Boss, director or lead: a role that coordinates and never writes code.
_Avoid_: Manager, orchestrator

**Worker**:
A short-lived agent started for exactly one factory task (pm, coder, reviewer, qa, judge, cleaner).
_Avoid_: Subagent, HQ role

**Team**:
The lead and workers staffed on one goal (`g-001-a`).
_Avoid_: Org, squad

**Pane**:
The herdr terminal pane one agent runs in.
_Avoid_: Window, tab, session

**Spawn**:
Starting a worker for one factory task (`factory spawn`).
_Avoid_: Assign, launch, dispatch

**Tick**:
The factory's once-a-minute heartbeat that reaps, spawns, nudges and exports.
_Avoid_: Cron, loop, scheduler

**Nudge**:
A line the tick types into an agent's pane to make it read its inbox or run its cycle.
_Avoid_: Ping, notification

**Message**:
A row one agent sends another through the factory database (`M23`); the only way agents talk.
_Avoid_: Chat, mail, comment

## Merge gate

**Verdict**:
A recorded pass or fail on a factory task's PR from the reviewer, QA or the judge.
_Avoid_: Approval, review (when the record is meant)

**Merge gate**:
The rule that a PR merges only with a passing reviewer verdict, a passing QA verdict and green required checks, decided by the judge.
_Avoid_: Pipeline, approval flow

**Gated PR**:
A PR that touches guard, settings or CI paths or is over 500 changed lines, so its review runs the multi-angle-review workflow.
_Avoid_: Risky PR (that is the CI tier)

**Risk tier**:
The CI class of a branch (docs, normal or risky) that decides how much of the test suite runs.
_Avoid_: Gate, priority

**Worker guard**:
The hook that blocks an agent's out-of-role actions before they run.
_Avoid_: Sandbox (that is the separate isolation layer), firewall
