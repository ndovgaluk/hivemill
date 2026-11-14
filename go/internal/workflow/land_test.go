package workflow

import (
	"strings"
	"testing"
)

// builtCI is a built run (every child reviewed, the builder done) in CI mode ci.
func builtCI(t *testing.T, ci string) *startRig {
	t.Helper()
	r := built(t)
	st, _ := OpenState(StatePath(r.home))
	st.Exec("UPDATE runs SET ci=?", ci)
	st.Close()
	return r
}

func (r *startRig) incidents(t *testing.T, cause Cause) int {
	t.Helper()
	st, _ := OpenState(StatePath(r.home))
	defer st.Close()
	var n int
	st.QueryRow("SELECT count(*) FROM incidents WHERE cause=?", string(cause)).Scan(&n)
	return n
}

// assertLanded checks one plain push of the fake merge commit to main, the merged event, the task done and the run done.
func assertLanded(t *testing.T, r *startRig) {
	t.Helper()
	ok := 0
	for _, p := range r.git.pushes() {
		for _, a := range p {
			if a == "--force" || a == "-f" || strings.HasPrefix(a, "+") {
				t.Fatalf("forced push: %v", p)
			}
		}
		if strings.Join(p, " ") == "push origin "+fakeLandSHA+":refs/heads/main" {
			ok++
		}
	}
	if ok != 1 {
		t.Fatalf("pushes %v", r.git.pushes())
	}
	var detail, status string
	r.fdb.QueryRow("SELECT detail FROM events WHERE entity='task' AND entity_id='T-0001' AND action='merged'").Scan(&detail)
	r.fdb.QueryRow("SELECT status FROM tasks WHERE id='T-0001'").Scan(&status)
	if !strings.HasPrefix(detail, "@"+fakeLandSHA) || status != taskStatusDoneArg {
		t.Fatalf("merged event %q, task %s", detail, status)
	}
	if r.state(t) != string(RunDone) {
		t.Fatalf("run %s", r.state(t))
	}
	if n := len(r.callsLike("msg coder-t-0001")); n != 0 { // no "open the pull request" mail
		t.Fatalf("%d mails to the builder: %v", n, r.factory.calls)
	}
}

func TestNoneMergesAndPushesWithoutAPullRequestAndWithoutTests(t *testing.T) {
	r := builtCI(t, CINone)
	r.tick(t)
	assertLanded(t, r)
	if len(r.tests.starts) != 0 {
		t.Fatalf("tests ran: %v", r.tests.starts)
	}
	found := false
	for _, c := range r.tracker.comments {
		if strings.Contains(c, "without a pull request and without tests") {
			found = true
		}
	}
	if !found {
		t.Fatalf("no story comment says it went untested: %v", r.tracker.comments)
	}
}

func TestNoneWithAChildStillFixingDoesNothing(t *testing.T) {
	r := builtCI(t, CINone)
	st, _ := OpenState(StatePath(r.home))
	st.Exec("UPDATE children SET state='fixing' WHERE child_key='C-2'")
	st.Close()
	r.tick(t)
	if len(r.git.pushes()) != 0 || r.state(t) != string(RunBuilt) {
		t.Fatalf("state %s pushes %v", r.state(t), r.git.pushes())
	}
}

func TestLocalRunsTheAffectedTestsOfTheHeadThenLands(t *testing.T) {
	r := builtCI(t, CILocal)
	r.tick(t) // starts the tests
	if len(r.tests.starts) != 1 || r.tests.starts[0] != "python3 ci/affected.py --base origin/main --run" || r.state(t) != string(RunGating) {
		t.Fatalf("starts %v state %s", r.tests.starts, r.state(t))
	}
	if len(r.git.pushes()) != 0 {
		t.Fatal("pushed before the tests ended")
	}
	r.tick(t) // reads the pass
	assertLanded(t, r)
	if len(r.tests.starts) != 1 {
		t.Fatalf("tests started again: %v", r.tests.starts)
	}
}

func TestLocalRedTestsGoBackToTheBuilderWithTheFailingTests(t *testing.T) {
	r := builtCI(t, CILocal)
	r.tests.code, r.tests.log = 1, "FAIL: test_x (mod.Case.test_x)\nERROR: test_y (mod.Case.test_y)\nRan 3 tests in 1s\nFAILED\n"
	r.tick(t)
	r.tick(t)
	if r.state(t) != string(RunBuilding) || len(r.git.pushes()) != 0 {
		t.Fatalf("state %s pushes %v", r.state(t), r.git.pushes())
	}
	mails := r.callsLike("msg coder-t-0001")
	if len(mails) != 1 || r.incidents(t, CauseLocalTestsFailed) != 1 {
		t.Fatalf("mails %v incidents %d", mails, r.incidents(t, CauseLocalTestsFailed))
	}
	body := r.factory.stdins[len(r.factory.stdins)-1]
	if !strings.Contains(body+mails[0], "mod.Case.test_x, mod.Case.test_y") {
		t.Fatalf("failing tests not named: %q %q", mails[0], body)
	}
}

func TestTheThirdRedRunStopsForTheOwner(t *testing.T) {
	r := builtCI(t, CILocal)
	r.tests.code, r.tests.log = 1, "FAIL: test_x (mod.Case.test_x)\nRan 1 test in 1s\n"
	r.tick(t)
	for i := 0; i < MaxLocalTestFailures; i++ {
		r.tick(t) // reads the red result (the same head: the result file is still there)
		if i < MaxLocalTestFailures-1 {
			st, _ := OpenState(StatePath(r.home))
			st.Exec("UPDATE runs SET state='built'") // the builder ran factory wf built again
			st.Close()
		}
	}
	if r.state(t) != string(RunBlocked) || r.incidents(t, CauseLocalTestsLimit) != 1 || len(r.git.pushes()) != 0 {
		t.Fatalf("state %s limit %d pushes %v", r.state(t), r.incidents(t, CauseLocalTestsLimit), r.git.pushes())
	}
}

func TestALoadRefusalIsRetriedNotFailed(t *testing.T) {
	r := builtCI(t, CILocal)
	r.tests.code = affectedExitLoad
	r.tick(t)
	r.tick(t) // reads exit 5: drops the result
	r.tick(t) // starts again
	if len(r.tests.starts) != 2 || r.incidents(t, CauseLocalTestsFailed) != 0 || r.state(t) != string(RunGating) {
		t.Fatalf("starts %v failed %d state %s", r.tests.starts, r.incidents(t, CauseLocalTestsFailed), r.state(t))
	}
}

func TestAMovedBaseIsNotMergedAndGoesBackToTheBuilder(t *testing.T) {
	r := builtCI(t, CINone)
	r.git.baseMoved = true
	r.tick(t)
	if len(r.git.pushes()) != 0 || r.state(t) != string(RunBuilding) || r.incidents(t, CauseLandRefused) != 1 {
		t.Fatalf("state %s pushes %v refused %d", r.state(t), r.git.pushes(), r.incidents(t, CauseLandRefused))
	}
	if m := r.callsLike("msg coder-t-0001"); len(m) != 1 {
		t.Fatalf("builder mails %v", m)
	}
}

func TestARefusedPushIsRetriedOnTheNextTickAndPushesOnce(t *testing.T) {
	r := builtCI(t, CINone)
	r.git.pushFail = 1
	r.tick(t)
	if r.state(t) != string(RunLanding) || r.incidents(t, CausePushRefused) != 1 {
		t.Fatalf("state %s refused %d", r.state(t), r.incidents(t, CausePushRefused))
	}
	r.tick(t)
	if len(r.git.pushes()) != 2 {
		t.Fatalf("pushes %v", r.git.pushes())
	}
	r.git.argv = r.git.argv[:0] // keep only the successful push for assertLanded
	r.git.argv = append(r.git.argv, []string{"push", "origin", fakeLandSHA + ":refs/heads/main"})
	assertLanded(t, r)
}

func TestADirtyOrUnpushedCheckoutIsRefusedOnceAndNothingRuns(t *testing.T) {
	for _, c := range []struct {
		name string
		set  func(*fakeGit)
	}{{"dirty", func(g *fakeGit) { g.dirty = true }}, {"unpushed", func(g *fakeGit) { g.unpushed = true }}} {
		t.Run(c.name, func(t *testing.T) {
			r := builtCI(t, CILocal)
			c.set(r.git)
			r.tick(t)
			r.tick(t)
			if len(r.tests.starts) != 0 || len(r.git.pushes()) != 0 || r.state(t) != string(RunBuilt) {
				t.Fatalf("starts %v pushes %v state %s", r.tests.starts, r.git.pushes(), r.state(t))
			}
			if r.incidents(t, CauseLandRefused) != 1 || len(r.callsLike("msg coder-t-0001")) != 1 {
				t.Fatalf("refused %d mails %v", r.incidents(t, CauseLandRefused), r.callsLike("msg coder-t-0001"))
			}
		})
	}
}

func TestAGithubRunStillAsksForThePullRequest(t *testing.T) {
	r := builtCI(t, CIGithub)
	r.tick(t)
	if len(r.git.pushes()) != 0 || len(r.tests.starts) != 0 || r.state(t) != string(RunMerging) {
		t.Fatalf("state %s pushes %v", r.state(t), r.git.pushes())
	}
}
