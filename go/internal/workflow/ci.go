package workflow

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
