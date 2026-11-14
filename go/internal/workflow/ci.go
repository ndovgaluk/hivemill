package workflow

import "fmt"

// eventCIMode is the factory event start writes with the run's CI mode as its detail (HM-67).
const eventCIMode = "ci-mode"

// ciMode is the CI mode of a run being started: the --ci flag when given (validated by the caller), else config
// workflow_ci, else github. An unknown config value counts as github: a typo in the config never skips GitHub's checks.
func (e *Engine) ciMode(flagValue string) string {
	if flagValue != "" {
		return flagValue
	}
	var v string
	if e.Factory == nil || e.Factory.QueryRow("SELECT value FROM config WHERE key=?", cfgCI).Scan(&v) != nil || !contains(CIModes, v) {
		return defaultCI
	}
	return v
}

// runCI is the mode stored for the run; a plan made without one (tests, older callers) is github.
func (p *startPlan) runCI() string {
	if p.ci == "" {
		return defaultCI
	}
	return p.ci
}

// finishLocal is the end of a run in CI mode local. Until HM-54 builds it (affected tests, merge into main, push),
// the run stops for the owner once every child is reviewed: it never falls back to a pull request silently.
func (e *Engine) finishLocal(r Run) error {
	var state string
	if err := e.State.QueryRow("SELECT state FROM runs WHERE goal_id=?", r.GoalID).Scan(&state); err != nil || state != string(RunBuilt) {
		return err // the building step above may have stopped the run
	}
	kids, err := e.children(r.GoalID)
	if err != nil {
		return err
	}
	for _, c := range kids {
		if c.state != string(ChildReviewed) {
			return nil
		}
	}
	subject := fmt.Sprintf("story run %s: CI mode local is not built yet", r.GoalID)
	body := fmt.Sprintf("Every child of run %s is reviewed. The run was started in CI mode local (affected tests on this "+
		"machine, then a merge into main without a pull request), which HM-54 builds and which does not exist yet, so "+
		"the run stops here instead of opening a pull request. Finish it by hand, or cancel the goal and start the "+
		"stories again with factory wf start --ci github.", r.GoalID)
	return e.stopRun(r, Incident{Kind: KindEscalation, Cause: CauseCILocalNotBuilt, Actor: ActorEngine,
		Summary: "CI mode local is not built yet (HM-54)", Detail: map[string]any{"ci": r.CI}}, subject, body)
}
