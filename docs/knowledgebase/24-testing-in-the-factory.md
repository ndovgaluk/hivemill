# When tests run in the factory, and how much

## Q: Running the e2e tests: when does it happen, and does the whole suite run or only the tests relevant to the task?

Short answer: **locally, agents run only the tests the change can affect (plus a small smoke set); the full suite runs in CI (or in a local merge gate), never by an agent by hand.** The policy is "local fast, CI full" (`docs/testing.md`, `docs/tests-and-ci.md`). Hivemill has no browser e2e suite; its whole test suite is `unittest` (run as 10 CI shards). For another project, "e2e" is whatever that project's CI or gate command runs.

**Who runs what, and when** (from the role files):

| When | Who | What runs |
|---|---|---|
| While building, before the PR | **coder** | lint, build, and `python3 ci/affected.py --base origin/main --quick --run`: only the test modules the diff can affect plus the smoke set, within a 120 s budget. It also writes new tests proving each acceptance criterion (C1–C6: outcome-based, deterministic, never the live home; a new guard or bug fix must be shown failing without the fix). **Never the full suite: the guard refuses it** |
| On the PR | **GitHub Actions CI** (`tests.yml`) | Depends on the change's **tier** (`ci/ci_tier.py`, taken from the base commit so a PR can't lower its own tier): **docs** = only link/fence checks; **normal** = each of the 10 shards runs its share of the affected modules; **risky** (`.github/`, hooks, role settings, sandbox, CI gates, judge/gate code, …) = **full suite**. If `affected.py` answers `FULL` (e.g. `SCHEMA`, `DEFAULT_CONFIG` or a widely used function changed), the full suite runs too. A push to `main` always runs the full suite |
| Reviewing | **reviewer** | Judges the diff and CI (`gh pr checks`, `gh run view --log-failed`); locally at most the same `affected.py --quick --run` or the one failing module. Checks that the tests really prove the criteria |
| Verifying | **qa** | Same quick affected run + the build on the PR head, then verifies **each acceptance criterion** by running and observing, tries edge cases. Records a `## Gates` section with real exit codes. **Fails the PR** if 0 tests ran, if the test count drops below `main`, or a criterion is untested |
| Merge decision | **judge** | Reads both verdicts and CI; merges only when the required checks (here `unittest`) are green. With a **local gate** (`gate_cmd` set on the project, `docs/local-gate.md`) the full suite runs on your machine on the exact PR head instead of relying on paid CI ("the cost is one rejection, not a broken main") |

**Always enforced, every tier:**
- **Test-count gate:** a PR may not run fewer tests than `main` (an intentional drop needs a `tests-removed: <reason>` line).
- **0 tests = failure**, even with exit code 0.
- **Load cap:** if the machine is busy (load ≥ `gate_max_load_ratio` × CPUs), agents skip local runs and rely on CI — not a failure.
- **Test slots:** full-suite runs on the host take one of `test_slots` (default 2).

**Your install:** project `hivemill` relies on GitHub Actions (`required_checks unittest`) and has **no `gate_cmd`**, so there's no local full-suite gate. The upstream factory runs with a local gate (`docs/CUTOVER.md`: "switched on for project `factory`"). You could add one later with `factory project update hivemill --gate-cmd … --gate-count-cmd …` (director/owner only), e.g. to avoid Actions minutes on a private repo.

**For a Node project like Taskosaur** the same roles apply, but "affected tests" and e2e are what that project provides: the coder and QA run the task's relevant tests, and the **full e2e suite would run in that project's CI job(s) you list as `--required-checks`** (or its `gate_cmd`). That's where you'd put the Playwright/backend e2e run, and where the shared-database caveat matters most.

**Not the same as your TSR skill:** in `working-with-taskosaur` the default is also "only the task's own e2e specs", with a full e2e run only on request (`e2e` parameter). The factory has no such parameter; it decides by tier and leaves the full run to CI or the gate.

---

## Q: what is CI in this case and how long does it take?

(Reply of 2026-11-13, as written. Context: the coder of factory task T-0003 was waiting for CI on PR #3.)

CI here is the GitHub Actions workflow `tests` on your fork (`ndovgaluk/hivemill`), which runs on GitHub's servers for every pull request to `main`. On a successful run it has taken 12 to 18 minutes today.

**What it runs** (`.github\workflows\tests.yml`, 19 jobs on PR #3):

| Jobs | What they check |
|---|---|
| `unittest-shard (1)`–`(10)` | The Python test suite, split into 10 parallel parts |
| `go` | The Go port of the worker guard (format, vet, tests, build) |
| `guard-unittest-shard (1)`–`(3)` | The guard's own tests, in 3 parts |
| `guard-diff`, `guard-equiv`, `guard-equiv-rest`, `guard-self-compare`, `guard-evaluator-home-loosen` | That the guard still blocks what it must, and that the Python and Go guards agree |
| `unittest` | The final summary job: passes only if all the others did, and checks that the PR has no fewer tests than `main` |

`unittest` is the one check that counts for the merge; it starts only after all the others finish. The judge will not merge without it green (when config `required_checks` is set to it, which I did not check on your install).

**How long:** measured from today's runs on the fork (start to last update):

| Run | Result | Duration |
|---|---|---|
| `factory/t-0003`, earlier attempt | success | 12 min 37 s |
| `factory/t-0004` | success | 15 min 41 s |
| `factory/t-0004` | success | 18 min 05 s |
| `dvdg-544-task-flow` (two runs) | failure | about 21 min each |

The ordinary test parts finish in about a minute each. The guard jobs are the slow part.

**The current run on PR #3** started at 04:43:08 and had been going about 6 minutes when I looked (04:49). All 10 test parts, `go`, `guard-diff` and both `guard-equiv` jobs had passed; the five remaining guard jobs were running. Going by the runs above, it should finish between about 04:56 and 05:01.

**A correction to my previous answer:** I said those five guard jobs "have not started". That was wrong. The check list shows them as "pending" with 0 seconds, but the run details show each started between 04:43 and 04:45 and is in progress. So they are not waiting for a runner, and there is nothing for you to look at unless the run goes well past 20 minutes.

Two other workflows exist and are not part of this wait: `install` (an install smoke test) and `release`.

LSP: not used, only a workflow file, a doc and GitHub run data were read.

Skipped: reading what each guard job does step by step, and your install's `required_checks` setting; risk: the finish estimate is from three successful runs, so it is a rough range.
