package workflow

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
)

// The finish of a story run without a pull request (HM-54, CI modes local and none). After every child is reviewed:
// the builder's checkout must be clean and pushed; a local run then runs the affected tests of that exact head
// (gating); a none run runs nothing. Landing merges the branch into the base with a merge commit and pushes the base,
// plainly (never --force), then the usual finish steps (linking, reporting, closing, announcing) take over.

const (
	affectedScript    = "ci/affected.py"
	taskStatusDoneArg = "done"
	eventLanded       = "landed" // factory event on the run's goal: the merge commit and the CI mode
	stopReasonLanded  = "story run landed on the base branch"
)

var (
	ranTestsRE   = regexp.MustCompile(`(?m)^Ran (\d+) tests?`)
	failedTestRE = regexp.MustCompile(`(?m)^(?:FAIL|ERROR): \S+ \(([\w.]+)\)`)
)

// allReviewed is true when the run is still built and every child passed review.
func (e *Engine) allReviewed(r Run) (bool, error) {
	var state string
	if err := e.State.QueryRow("SELECT state FROM runs WHERE goal_id=?", r.GoalID).Scan(&state); err != nil || state != string(RunBuilt) {
		return false, err // the building step before this may have stopped the run
	}
	kids, err := e.children(r.GoalID)
	if err != nil {
		return false, err
	}
	for _, c := range kids {
		if c.state != string(ChildReviewed) {
			return false, nil
		}
	}
	return len(kids) > 0, nil
}

// startLanding is the end of building for CI modes local and none: once every child is reviewed and the builder's
// checkout is clean and pushed, a local run goes to gating and a none run straight to landing.
func (e *Engine) startLanding(r Run) error {
	if ok, err := e.allReviewed(r); err != nil || !ok {
		return err
	}
	wt, branch, _, err := e.taskCheckout(r.TaskID)
	if err != nil {
		return err
	}
	head, why, err := e.checkoutReady(wt, branch)
	if err != nil {
		return err
	}
	if why != "" {
		return e.refuseLanding(r, head, why, fmt.Sprintf("Commit and push every change on %s (git status clean, HEAD "+
			"equal to origin/%s), then run factory wf built.", branch, branch))
	}
	next := RunLanding
	if r.CI == CILocal {
		next = RunGating
	}
	if err := e.setRunState(r.GoalID, next); err != nil {
		return err
	}
	r.State = next
	if next == RunGating {
		return e.advanceGating(r)
	}
	return e.advanceLanding(r)
}

// checkoutReady fetches origin and returns the builder's HEAD and why it may not land yet ("" when it may).
func (e *Engine) checkoutReady(wt, branch string) (head, why string, err error) {
	g := e.Deps.Git
	if _, err := g.Run(wt, "fetch", "-q", "origin"); err != nil {
		return "", "", err
	}
	if st, err := g.Run(wt, "status", "--porcelain", "--untracked-files=no"); err != nil {
		return "", "", err
	} else if strings.TrimSpace(st) != "" {
		head, _ = g.Run(wt, "rev-parse", "HEAD")
		return head, "the builder's worktree has uncommitted changes", nil
	}
	if head, err = g.Run(wt, "rev-parse", "HEAD"); err != nil {
		return "", "", err
	}
	if remote, err := g.Run(wt, "rev-parse", "origin/"+branch); err != nil || remote != head {
		return head, fmt.Sprintf("HEAD %s is not pushed to origin/%s", short(head), branch), nil
	}
	return head, "", nil
}

// refuseLanding records why the run cannot land, once per head and cause, mails the builder once with what to do,
// and leaves the run where it is (built) or sends it back to building when the builder must change the branch.
func (e *Engine) refuseLanding(r Run, head, why, todo string) error {
	var n int
	e.State.QueryRow("SELECT count(*) FROM incidents WHERE goal_id=? AND cause=? AND head_sha=? AND summary=?", r.GoalID,
		string(CauseLandRefused), head, why).Scan(&n)
	if n > 0 {
		return nil
	}
	detail := map[string]any{"ci": r.CI, "head": head}
	if b, found, err := e.agent("", r.TaskID, roleCoder); err == nil && found {
		mail, err := e.mail(r, b.name, mailRequest, fmt.Sprintf("story run %s cannot land yet", r.GoalID),
			fmt.Sprintf("Run %s (CI mode %s) cannot merge into the base branch yet: %s. %s", r.GoalID, r.CI, why, todo))
		detail["mail"] = mail
		if err != nil {
			detail["mail_error"] = err.Error()
		}
	}
	_, err := e.Record(Incident{GoalID: r.GoalID, Kind: KindWarning, Cause: CauseLandRefused, Actor: ActorEngine,
		HeadSHA: head, Summary: why, Detail: detail})
	return err
}

// testFiles are the log, exit-code and pass-marker paths of the affected run of one head.
func (e *Engine) testFiles(goal, head string) (dir, logPath, rcPath, okPath string) {
	dir = filepath.Join(e.Home, "run", "workflow", goal)
	base := filepath.Join(dir, "affected-"+short(head))
	return dir, base + ".log", base + ".rc", base + ".ok"
}

// advanceGating runs the affected tests of the builder's head (CI mode local): it starts them once, reads their
// result on a later tick, and then lands, sends the failures to the builder, or retries a run refused for load.
func (e *Engine) advanceGating(r Run) error {
	wt, branch, base, err := e.taskCheckout(r.TaskID)
	if err != nil {
		return err
	}
	head, why, err := e.checkoutReady(wt, branch)
	if err != nil {
		return err
	}
	if why != "" { // the builder changed the branch meanwhile: back to built until it is pushed again
		if err := e.setRunState(r.GoalID, RunBuilt); err != nil {
			return err
		}
		return e.refuseLanding(r, head, why, "Push it, then run factory wf built.")
	}
	dir, logPath, rcPath, okPath := e.testFiles(r.GoalID, head)
	rc, err := os.ReadFile(rcPath)
	if err != nil {
		if st, serr := os.Stat(logPath); serr == nil { // started, not finished
			if e.Env.Now().Sub(st.ModTime()) < affectedStaleAfter {
				return nil
			}
			os.Remove(logPath)
			return e.testsError(r, head, fmt.Sprintf("the affected tests of %s gave no result in %s", short(head), affectedStaleAfter))
		}
		if err := os.MkdirAll(dir, 0o700); err != nil {
			return err
		}
		if err := os.WriteFile(logPath, nil, 0o600); err != nil { // the started marker, before the run can write to it
			return err
		}
		if err := e.Deps.Tests.Start(wt, logPath, rcPath, []string{"python3", affectedScript, "--base", "origin/" + base, "--run"}); err != nil {
			os.Remove(logPath)
			return e.testsError(r, head, "the affected tests could not start: "+err.Error())
		}
		return e.Env.EventAs(e.Factory, ActorEngine, EventEntity, r.GoalID, "local-tests-started", short(head))
	}
	code, _ := strconv.Atoi(strings.TrimSpace(string(rc)))
	out, _ := os.ReadFile(logPath)
	if code == affectedExitLoad { // refused for load: try again next tick
		os.Remove(rcPath)
		os.Remove(logPath)
		return nil
	}
	ran := 0
	for _, m := range ranTestsRE.FindAllStringSubmatch(string(out), -1) {
		n, _ := strconv.Atoi(m[1])
		ran += n
	}
	if code == 0 && ran > 0 {
		if err := os.WriteFile(okPath, []byte(head+"\n"), 0o600); err != nil {
			return err
		}
		if err := e.Env.EventAs(e.Factory, ActorEngine, EventEntity, r.GoalID, "local-tests-passed",
			fmt.Sprintf("%s ran=%d", short(head), ran)); err != nil {
			return err
		}
		if err := e.setRunState(r.GoalID, RunLanding); err != nil {
			return err
		}
		r.State = RunLanding
		return e.advanceLanding(r)
	}
	return e.testsFailed(r, head, code, ran, string(out), logPath)
}

// testsError records an infrastructure problem with the affected run (warning) and retries next tick.
func (e *Engine) testsError(r Run, head, why string) error {
	_, err := e.Record(Incident{GoalID: r.GoalID, Kind: KindWarning, Cause: CauseLocalTestsError, Actor: ActorEngine,
		HeadSHA: head, Summary: why, Detail: map[string]any{"ci": r.CI}})
	return err
}

// testsFailed sends a red affected run back to the builder, or stops the run at MaxLocalTestFailures.
func (e *Engine) testsFailed(r Run, head string, code, ran int, out, logPath string) error {
	var failed []string
	for _, m := range failedTestRE.FindAllStringSubmatch(out, -1) {
		if !contains(failed, m[1]) && len(failed) < failedTestsMax {
			failed = append(failed, m[1])
		}
	}
	why := fmt.Sprintf("the affected tests of %s failed (exit %d, %d tests ran)", short(head), code, ran)
	if ran == 0 && code == 0 {
		why = fmt.Sprintf("the affected tests of %s ran no test", short(head))
	}
	n, err := e.countSince(r.GoalID, "", CauseLocalTestsFailed)
	if err != nil {
		return err
	}
	detail := map[string]any{"ci": r.CI, "exit_code": code, "ran": ran, "failed": failed, "log": logPath}
	if _, err := e.Record(Incident{GoalID: r.GoalID, Kind: KindRejection, Cause: CauseLocalTestsFailed, Actor: ActorEngine,
		HeadSHA: head, Summary: why, Detail: detail}); err != nil {
		return err
	}
	if n+1 >= MaxLocalTestFailures {
		return e.stopRun(r, Incident{Kind: KindEscalation, Cause: CauseLocalTestsLimit, Actor: ActorEngine, HeadSHA: head,
			Summary: fmt.Sprintf("%d failed affected runs", n+1), Detail: detail},
			fmt.Sprintf("story run %s: the affected tests failed %d times", r.GoalID, n+1),
			fmt.Sprintf("The affected tests of run %s failed %d times (last: %s; log %s). The run waits: fix it with the "+
				"builder, then factory wf resume --goal %s.", r.GoalID, n+1, strings.Join(failed, ", "), logPath, r.GoalID))
	}
	if err := e.setRunState(r.GoalID, RunBuilding); err != nil {
		return err
	}
	b, found, err := e.agent("", r.TaskID, roleCoder)
	if err != nil || !found {
		return err
	}
	_, err = e.mail(r, b.name, mailRequest, fmt.Sprintf("story run %s: the affected tests failed", r.GoalID),
		fmt.Sprintf("%s. Failing tests: %s. Log: %s. Fix what the run caused, commit, push, then run factory wf built; "+
			"the tests run again on the new head.", why, strings.Join(failed, ", "), logPath))
	return err
}

// devdigestLandingCheck is the call site HM-61 fills: before a run without a pull request merges, every child's last
// DevDigest gate review must pass or be waived. Until HM-61 exists it allows the merge.
func (e *Engine) devdigestLandingCheck(Run) error { return nil }

// advanceLanding merges the branch into the base branch and pushes it: one merge commit (the base and the branch as
// parents, the branch's tree), pushed as a fast-forward of the base; never --force. A refused push is retried next tick.
func (e *Engine) advanceLanding(r Run) error {
	if sha, err := e.mergeSHA(r.TaskID); err == nil && sha != "" { // landed earlier: only the finish steps are left
		return e.toLinking(r)
	}
	wt, branch, base, err := e.taskCheckout(r.TaskID)
	if err != nil {
		return err
	}
	head, why, err := e.checkoutReady(wt, branch)
	if err != nil {
		return err
	}
	if why != "" {
		if err := e.setRunState(r.GoalID, RunBuilt); err != nil {
			return err
		}
		return e.refuseLanding(r, head, why, "Push it, then run factory wf built.")
	}
	if r.CI == CILocal {
		if _, _, _, okPath := e.testFiles(r.GoalID, head); !fileExists(okPath) { // a new head since the tests passed
			if err := e.setRunState(r.GoalID, RunGating); err != nil {
				return err
			}
			r.State = RunGating
			return e.advanceGating(r)
		}
	}
	if err := e.devdigestLandingCheck(r); err != nil {
		return err
	}
	g := e.Deps.Git
	if _, err := g.Run(wt, "merge-base", "--is-ancestor", "origin/"+base, "HEAD"); err != nil {
		if err := e.setRunState(r.GoalID, RunBuilding); err != nil {
			return err
		}
		return e.refuseLanding(r, head, fmt.Sprintf("origin/%s moved and %s does not contain it", base, short(head)),
			fmt.Sprintf("Merge it: git fetch origin && git merge origin/%s, run the tests, push, then run factory wf built.", base))
	}
	kids, err := e.children(r.GoalID)
	if err != nil {
		return err
	}
	ss, err := e.stories(r, kids)
	if err != nil {
		return err
	}
	body := fmt.Sprintf("Story run %s (%s), merged by the workflow engine without a pull request, CI mode %s.",
		r.GoalID, strings.Join(keysOf(ss), ", "), r.CI)
	sha, err := g.Run(wt, "commit-tree", "HEAD^{tree}", "-p", "origin/"+base, "-p", "HEAD", "-m", prTitle(r.TaskID, ss), "-m", body)
	if err != nil {
		return err
	}
	if _, err := g.Run(wt, "push", "origin", sha+":refs/heads/"+base); err != nil {
		var n int
		e.State.QueryRow("SELECT count(*) FROM incidents WHERE goal_id=? AND cause=? AND head_sha=?", r.GoalID,
			string(CausePushRefused), head).Scan(&n)
		if n == 0 {
			_, rerr := e.Record(Incident{GoalID: r.GoalID, Kind: KindWarning, Cause: CausePushRefused, Actor: ActorEngine,
				HeadSHA: head, Summary: "push of the merge refused; retried next tick", Detail: map[string]any{"error": err.Error(), "ci": r.CI}})
			return rerr
		}
		return nil
	}
	if err := e.Env.EventAs(e.Factory, ActorEngine, "task", r.TaskID, eventMerged, fmt.Sprintf("@%s by=engine ci=%s", sha, r.CI)); err != nil {
		return err
	}
	if err := e.Env.EventAs(e.Factory, ActorEngine, EventEntity, r.GoalID, eventLanded, fmt.Sprintf("@%s ci=%s", short(sha), r.CI)); err != nil {
		return err
	}
	if _, err := e.Deps.Factory.Run("", "task", "update", r.TaskID, "--status", taskStatusDoneArg, "--note",
		fmt.Sprintf("merged by the workflow engine without a pull request (CI mode %s) as %s", r.CI, short(sha))); err != nil {
		return err
	}
	if b, found, _ := e.agent("", r.TaskID, roleCoder); found && !ended(b.status) {
		e.Deps.Factory.Run("", "stop", b.name, "--reason", stopReasonLanded) // best effort: its work is merged
	}
	return e.toLinking(r)
}

func (e *Engine) toLinking(r Run) error {
	if err := e.setRunState(r.GoalID, RunLinking); err != nil {
		return err
	}
	r.State = RunLinking
	return e.finish(r)
}

func fileExists(p string) bool {
	_, err := os.Stat(p)
	return err == nil
}
