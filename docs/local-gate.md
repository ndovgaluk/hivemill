# Local merge gate (steps 1-2: the runner and the judge wiring)

Owner rule (M8698): no paid GitHub Actions, every test runs on your own machine. The gate is a plain python process, not an agent:
`factory gate run` runs a project's gate command on the exact PR head (or on main) and records the result in the
`gate_runs` table. Step 1 (T-0515) builds and records; step 2 (T-0516, below) makes the judge, `judge_pr_ready` and the tick read it.

## Commands

| command | who | what |
|---|---|---|
| `factory gate run <task>` | boss, director, lead, owner (never a worker role) | gate the task's PR head |
| `factory gate run --main <project>` | same | gate the verified current main of the project |
| `factory gate show <task or run-id>` | anyone | one run (a task id shows its latest run) |
| `factory gate list [--project P] [--limit N]` | anyone | recent runs, newest first |
| `factory project update <id> --gate-cmd C --gate-count-cmd C --gate-timeout-s N` | director, owner | set the project's gate |

Exit code of `gate run`: 0 pass, 1 fail (the command exited non-zero), 5 error (infrastructure: no slot, timeout, head
mismatch, unreadable count). A project is in local mode once `gate_cmd` is set.

## What a run does

1. Row in `gate_runs` (status `queued`, runner pid recorded).
2. Verified fetch, as in `head_has_main`: private refs under `refs/factory-judge/`, hardened git flags, main compared with
   `gh api repos/<r>/commits/main`. The fetched PR head must equal the head GitHub reports, else `error` (also when `gh pr view` fails).
3. Result cache: a `pass` row of the same (project, head sha, main sha, `gate_cmd`) is reused (new row, note `cached: pass of run #N`,
   no slot, no run); fail/error are never reused. `gate run --no-cache` runs anyway.
4. Waits until fewer than `gate_max_parallel` runs are `running` (default 1, so one of the two test slots stays free for workers),
   then for a `tests/_slot.py` slot with `acquire(require=True)`: it never runs slot-less. No slot in time: status `error`, note
   `no slot`, and the command is not started.
5. `git worktree add --detach ~/.cache/factory-gate/<id>/head <sha>`; HEAD is asserted to be exactly that sha.
6. `projects.gate_cmd` (from the DB, never from a script in the PR tree) runs through `bash -c` in that worktree in its own
   process group, output to `logs/gate/<id>.log`. After `gate_timeout_s` (default 3600) the whole group is killed: status
   `error`. The child gets no `FACTORY_AGENT`, no gh/ssh credentials, a scratch empty `FACTORY_HOME`, `FACTORY_MAIN` (the checkout
   running `bin/factory`, for `$FACTORY_MAIN/ci/test_count_gate.py`) and `FACTORY_TEST_SLOT_HELD=1` (the suite must not take a
   second slot).
7. If `gate_count_cmd` is set, it prints the test count as its last line; it runs on the head and on the verified main (a second
   worktree; cached per main sha). An unreadable count is `error`, never `pass`. Without it, `gate show` says "not counted".
8. Record `pass`/`fail`/`error`, exit code, counts, log path. Worktrees are removed on every path (also SIGTERM and failures).
   A `queued` or `running` row whose runner pid is gone is marked `error` (`runner died`) by the next run.

A head that does not contain the verified main still runs; the row's note says the tested tree is not the merge result.

## Sharded suite

`tests/gate_shards.py` runs the full suite as N parallel `ci/shard.py` processes in the one worktree and under the one slot,
verifies that every module ran once, sums the test count and prints wall and CPU seconds (also in `$GATE_REPORT_DIR/summary.json`,
which the runner copies into the row's note and into `test_count` when there is no `gate_count_cmd`). Use it in the gate command
from the main checkout, so a PR cannot edit it: `python3 $FACTORY_MAIN/tests/gate_shards.py`. N is `gate_shards` (default 4)
capped by the CPU the load gate leaves free; the runner passes it as `$GATE_SHARDS`. Example for factory:
`python3 -m py_compile bin/factory bin/factory_cli.py && python3 $FACTORY_MAIN/tests/gate_shards.py && <go vet/test/build>`.

Known limit: the shards run the PR tree's own `ci/shard.py` (only the wrapper and the command are fixed), so the gate trusts the
PR's test runner, as CI did. The cache key is (project, head sha, main sha, `gate_cmd`).

## Config

| key | default | meaning |
|---|---|---|
| `gate_max_parallel` | 1 | runs at once |
| `gate_shards` | 4 | parallel shard processes per run (capped by free CPU) |
| `gate_post_status` | 0 | 1: mirror each PR result as commit status `factory/local-gate` (write only, never read back) |
| `gate_retry_error` | 1 | error (infra) runs of one head retried this many times by `judge_pr_ready` |

`factory res` shows the running gate runs. A run's log is `logs/gate/<id>.log` under the factory home.

## Judge wiring (step 2, T-0516)

A project is in **local mode** iff `projects.gate_cmd` is non-empty; every other project keeps the GitHub-checks path unchanged.
In local mode:

- `factory judge --merge` (`local_gate_problems`): the latest `gate_runs` row of this exact PR head decides. No row, `queued`,
  `running`, `fail`, `error` refuse; a pass never carries across a head change. A pass is also refused when its test count is below
  main's and the PR body has no `tests-removed: <reason>` line (same bypass line as `ci/test_count_gate.py`). A failing GitHub
  check still refuses (`checks_ok`), but `required_checks` is not asked for. With no run yet the judge enqueues one and waits
  (`judge_ci_wait_s`) for it, like it waits for CI.
- A stale head is refreshed by the judge as before; it then enqueues a gate run for the new head and exits `REQUEUED` without
  waiting (exit 0, nothing merged). The tick spawns a judge again once the run passes.
- `judge_pr_ready` (the tick's hold on a queued judge) reads `gate_runs` of the PR's current head: pass = ready, queued/running =
  not ready, none = enqueue one and not ready, fail = not ready plus one message to the team lead per run, error = retried up to
  `gate_retry_error` times, then like fail.
- The tick (`tick_gate`) reaps dead runners and launches queued runs that have no runner yet (`gate_runs.pid` NULL) as detached
  `factory gate run --run-id N` processes while fewer than `gate_max_parallel` are active. Enqueue is deduped per PR.

## Sandbox (`gate_sandbox`, T-0632)

`factory gate run` runs PR code as the owner uid. With `factory config gate_sandbox 1` the gate command and `gate_count_cmd`
run under `scout/gatebox.py` (the nsbox allow-list mode) instead of plain `bash -c`:

- `$HOME`, `$XDG_RUNTIME_DIR`, `/tmp`, `/var/tmp` and `/dev/shm` are empty tmpfs (credentials, the user bus, ssh-agent are not
  there). `/var/tmp` is disk-backed on the host, so it is hidden too: a PR must not leave files there for a later run.
- The checkout running `bin/factory` (`$FACTORY_MAIN`) and the repo's git common dir (hooks, config, refs, objects) are
  read-only; `$FACTORY_MAIN`'s `db`, `run`, `logs`, `worktrees`, `exports`, `state` are masked.
- Writable: the gate tree itself, `<wt_root>/reports` (`$GATE_REPORT_DIR`), `<wt_root>/factory-home` (scratch `$FACTORY_HOME`)
  and `<wt_root>/tmp` (`$TMPDIR`, disk-backed). The gate tree is rw because the suite writes into its own tree (`docs/demo/out`,
  rendered settings); that is acceptable because it is a throwaway detached checkout: every run makes a fresh
  `<gate_dir>/<run id>/head` with `git worktree add --detach` and removes it afterwards, so a write never reaches a later run
  or the result cache. The git common dir stays read-only even though the tree's `.git` file points into it.
- The box sets `FACTORY_GATEBOX=1`. The two nested-user-namespace tests that cannot observe what they assert inside the outer
  box (`test_skilleval_nsbox`: own pid namespace, hiding `.claude`) skip on it with the reason; unboxed runs and CI run them.
- No network (own net namespace, loopback only), own pid namespace, capabilities dropped. Only an allow-list of environment
  variables passes (no `GH_TOKEN`, no agent identity). The scratch `$FACTORY_HOME` is always the run's own; a caller's
  `FACTORY_HOME` never overrides it.
- The memory-backed tmpfs sizes are small (`$HOME` 8m, `/tmp` 64m, `/var/tmp` and `/dev/shm` 16m): anything the suite writes
  under `$HOME` is lost at the end of the run.

Fail closed: when user namespaces are unavailable, the sandbox cannot be built, or `gate_sandbox` is neither `0` nor `1`, the run
ends `error` with a note saying the command was **not run unsandboxed**; the command never runs outside the box. A boxed run's
note says `sandboxed`. The result cache is unchanged (same head, main and `gate_cmd`), so a `pass` from before the flag was
turned on is still reused; `gate run --no-cache` forces a boxed run.

Rollback: `factory config gate_sandbox 0` (the default). The next run is byte-identical to the unsandboxed gate.

The flip is proven end to end by `tests/test_gate_sandbox.py` `FlagRollback.test_on_then_rollback_then_on_again`: in a temp
`FACTORY_HOME` it runs a real unittest module (`test_nsbox_allow.GoldenDefaultsTests`) through `factory gate run` with
`gate_sandbox 1` (pass, note says `sandboxed`), then after `factory config gate_sandbox 0` (pass, no `sandboxed`), then with
`1` again (pass, `sandboxed`). The test skips with the reason where user namespaces are unavailable.

## Nothing waits for GitHub (`gate_ignore_pending_ci`, HM-52)

Config `gate_ignore_pending_ci` (`0` or `1`, default `0`) has an effect only for a project in local mode. With it on, the
head's local gate run is the one test run that anything waits for:

| Step | Key off (and every project not in local mode) | Key on, local mode |
|---|---|---|
| Merge gate (`factory judge`, the mechanical merger) | GitHub's checks must have finished green, and the local run must pass | the local run must pass; a GitHub check that has not finished is not waited for (`judge_wait_ci` does not poll it); a check that **finished red** still refuses |
| First review (`review_autospawn` with `coder_ci_handoff` on) | reviewer and QA start when GitHub's CI is green on the head | they start when the head's local run passed; with no run for the head one is queued; the wait is logged as a `review-autospawn-wait` event of kind `local-gate` |
| Coder restart on red (`coder_ci_resume_tick`) | a red GitHub head restarts the coder | a `fail` run of the head restarts it, once per head, with the failing tests read from the run's log (`FAIL:`/`ERROR:` lines) and `factory gate show <id>` in its kickoff; the `coder-ci-resume` event says `source: local-gate` and the run id |
| Coder pre-check (`factory prcheck` check 5) | runs `ci/affected.py --run` in the worktree | met by a `pass` run of `HEAD`; does not start `ci/affected.py`; with no run it queues one and fails with "local gate run queued; run factory done when it has passed" |

The gate runs themselves log `gate-queued`/`gate-enqueued`, `gate-launched`, `gate-pass`, `gate-fail` and `gate-error`
events on entity `gate` (see "What a run does"). Switch: `factory config gate_ignore_pending_ci 1`; off again with `0`.
Tests: `tests/test_gate_ignore_pending.py`.

## This factory (HM-51, measured 2026-11-15)

The `hivemill` project is **not** in local mode: its `gate_cmd` is empty and GitHub's CI clears its pull requests. The owner
decided to keep it that way after this measurement, because the local full suite is slower than CI on this machine.

Full suite through `python3 $FACTORY_MAIN/tests/gate_shards.py`, from a clean checkout of `main` at `e95bf31`, on the owner's
machine (12 threads, 32 GB), with no goal or engine run active:

| `GATE_SHARDS` | Wall | CPU | Tests | Peak memory used |
|---|---|---|---|---|
| 4 | 2622 s (44 min) | 11430 s | 7606 | 1.1 GB |
| 8 | 2300 s (38 min) | 16897 s | 7606 | 1.9 GB |
| 12 | 1788 s (30 min) | 16615 s | 7606 | 2.2 GB |

- The suite is CPU-bound here: the modules add up to about 17000 s, the 12 shards were evenly loaded (1327 to 1783 s each), so
  12 threads cannot go much below 24 min. GitHub's CI takes about 22 min on about 20 runners.
- Slowest modules: `test_screenshots` (591 s), `test_scout_fetch` (527 s), `test_worker_guard_push_pin` (442 s),
  `test_worker_guard_nopush_gitfile` (411 s), `test_routed_rest_selector` (383 s), `test_mech_merge` (349 s).
- Go checks that run locally: `gofmt -l` (0 s), `go vet ./...` (2 s), `go test -count=1 ./...` without `-race` (161 s, 15
  packages), `go build ./...` (1 s). `-race` needs cgo, and the machine has no C compiler.
- Test count: `python3 $FACTORY_MAIN/ci/test_count_gate.py count .` prints the same 7606 as the shard total.
- Four tests failed only on this machine (timezone, CPU count, no C compiler) and were fixed in HM-66; with them, the suite is
  meant to be green here. Two timing tests (`test_scrub_scan` "scans fast", `test_skilleval_vendor` "linear time") can fail
  when the machine is fully loaded.

To switch on later, with 12 shards and twice the measured wall time as the timeout:

```
factory config gate_shards 12
factory project update hivemill --gate-cmd 'python3 $FACTORY_MAIN/tests/gate_shards.py' \
  --gate-count-cmd 'python3 $FACTORY_MAIN/ci/test_count_gate.py count .' --gate-timeout-s 3600
factory gate run --main hivemill        # prove it: a pass row in `factory gate list`
```

To switch back: `factory project update hivemill --gate-cmd ""`. Local mode alone saves no time today: the judge and the
mechanical merger still wait for GitHub's checks to finish green and then also need the local pass, and the first review and
the coder's pre-check still use GitHub's CI (HM-51's code reading; HM-52 would change that).
