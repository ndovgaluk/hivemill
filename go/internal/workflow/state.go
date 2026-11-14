// Package workflow is the story workflow engine (TSR story DVDG-565, docs/workflow-engine.md): it runs a Taskosaur
// story with one builder, a review per child and one PR. It keeps its own state in <home>/db/workflow.db and only
// reads factory.db; its one write there is an events row through identity.Env.EventAs.
package workflow

import (
	"database/sql"
	"errors"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"time"

	_ "modernc.org/sqlite" // pure-Go SQLite driver, as factorydb
)

// RunState is runs.state.
type RunState string

// ChildState is children.state.
type ChildState string

const (
	RunNew      RunState = "new"
	RunStarting RunState = "starting" // goal made, builder not started yet
	RunBuilding RunState = "building"
	RunBlocked  RunState = "blocked"
	RunBuilt    RunState = "built"
	RunFailed   RunState = "failed" // start stopped part-way; see the incident
	// After every child is reviewed: the builder opens the one PR and the factory's gate merges it. Each finish step is
	// a state of its own, so a step that succeeded is never repeated after a failure later on (the done_step counter).
	RunMerging    RunState = "merging"    // the builder was told to open the PR; the factory's gate has it
	RunLinking    RunState = "linking"    // merged: linking commits (idempotent in Taskosaur)
	RunReporting  RunState = "reporting"  // commenting on the story (once)
	RunClosing    RunState = "closing"    // moving children, then stories, to Done
	RunAnnouncing RunState = "announcing" // telling the boss (once)
	RunDone       RunState = "done"

	ChildTodo      ChildState = "todo"
	ChildInReview  ChildState = "in_review" // built; waiting for a reviewer
	ChildReviewing ChildState = "reviewing" // a reviewer is on it
	ChildReviewed  ChildState = "reviewed"  // passed
	ChildFixing    ChildState = "fixing"    // changes requested; back with the builder
	ChildStuck     ChildState = "stuck"     // MaxFixRounds reached; the run waits for factory wf resume
	ChildBlocked   ChildState = "blocked"
	ChildReported  ChildState = "reported" // merged; its story's closing comment is posted (so a retry skips that story)
	ChildDone      ChildState = "done"     // merged and Done in Taskosaur
)

// Limits by convergence (owner decision of 2026-11-13); cost is never a stop.
const (
	MaxFixRounds           = 5 // changes results per child before the run stops
	MaxBuilderResumes      = 3 // early ends of the builder the engine resumes per run
	MaxSilentReviewerEnds  = 2 // a reviewer ending without a result: retried once, the second stops the run
	ReviewerSessionFresh   = "fresh"
	ReviewerSessionKeep    = "keep"
	cfgReviewerSession     = "workflow_reviewer_session"
	defaultReviewerSession = ReviewerSessionFresh
)

// Workflow names (`factory wf start --workflow`); HM-27 chooses one from size and complexity.
const (
	WorkflowSimple = "simple"
	WorkflowMedium = "medium"
	WorkflowHuge   = "huge"
)

// Workflows lists the accepted names.
var Workflows = []string{WorkflowSimple, WorkflowMedium, WorkflowHuge}

// Kind is incidents.kind: what went wrong, in four classes.
type Kind string

const (
	KindRejection  Kind = "rejection"
	KindFailure    Kind = "failure"
	KindWarning    Kind = "warning"
	KindEscalation Kind = "escalation"
)

// Kinds lists every Kind, for validating --kind.
var Kinds = []Kind{KindRejection, KindFailure, KindWarning, KindEscalation}

// Cause is incidents.cause: a short structured reason. Later steps add theirs here.
type Cause string

const (
	CauseEngineError    Cause = "engine-error"
	CauseStartFailed    Cause = "start-failed"    // a start step after the goal was made failed
	CauseSpawnRefused   Cause = "spawn-refused"   // factory spawn of the builder failed
	CauseBuilderBlocked Cause = "builder-blocked" // factory wf blocked

	CauseReviewChanges          Cause = "review-changes"           // a reviewer asked for changes; detail holds the notes
	CauseRoundLimit             Cause = "round-limit"              // MaxFixRounds reached on one child
	CauseReviewerEndedSilently  Cause = "reviewer-ended-silently"  // a reviewer ended without factory wf review
	CauseReviewerResumeFallback Cause = "reviewer-resume-fallback" // keep mode could not resume; this review ran fresh
	CauseBuilderResumed         Cause = "builder-resumed"          // the builder ended early and was resumed
	CauseBuilderResumeLimit     Cause = "builder-resume-limit"     // MaxBuilderResumes used, no session id, or resume refused
	CauseOwnerResumed           Cause = "owner-resumed"            // factory wf resume: the counters of early ends start over
	CauseTaskosaurError         Cause = "taskosaur-error"          // a finish step failed and is retried next tick
	CauseStaleMerging           Cause = "stale-merging"            // merging with no agent, no PR, no change for StaleMergingAfter
	CauseStartRefused           Cause = "start-refused"            // factory wf start refused before anything was made
	CauseBuilderWoken           Cause = "builder-woken"            // an ended builder resumed to get new work; not limited
	CauseSpawnRetryLimit        Cause = "spawn-retry-limit"        // MaxSpawnRetries refusals in a row for one agent name
	CauseClosedWithoutMerge     Cause = "closed-without-merge"     // the run's task is done with no merged event
	CausePendingFailed          Cause = "pending-failed"           // a queued comment, mark or mail failed; retried next tick
)

// MaxSpawnRetries is how many refusals in a row for the same agent name are retried before the engine acts: a spawn
// refusal often clears by itself (the resource gate, an old pane not yet confirmed closed).
const MaxSpawnRetries = 5

// StaleMergingAfter is how long a merging run may sit with no agent, no open PR and no change before the boss is told.
const StaleMergingAfter = 2 * time.Hour

// UserVersion is the PRAGMA user_version of workflow.db. The schema below is its shape for the first version (runs,
// run_stories, children, incidents; child_commits, pending and counters added by HM-35 before any release).
const UserVersion = 1

const schema = `
CREATE TABLE runs(goal_id TEXT PRIMARY KEY, story_key TEXT NOT NULL, workflow TEXT NOT NULL, task_id TEXT,
  state TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE run_stories(goal_id TEXT NOT NULL, story_key TEXT NOT NULL, position INTEGER NOT NULL,
  PRIMARY KEY(goal_id, story_key));
CREATE TABLE children(goal_id TEXT NOT NULL, story_key TEXT NOT NULL, child_key TEXT NOT NULL, position INTEGER NOT NULL,
  state TEXT NOT NULL, rounds INTEGER NOT NULL DEFAULT 0, base_sha TEXT, head_sha TEXT, updated TEXT NOT NULL,
  PRIMARY KEY(goal_id, child_key));
CREATE TABLE incidents(id INTEGER PRIMARY KEY AUTOINCREMENT, goal_id TEXT NOT NULL, child_key TEXT, kind TEXT NOT NULL,
  cause TEXT NOT NULL, actor TEXT NOT NULL, round INTEGER, base_sha TEXT, head_sha TEXT, summary TEXT NOT NULL,
  detail TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE child_commits(goal_id TEXT NOT NULL, child_key TEXT NOT NULL, sha TEXT NOT NULL, subject TEXT NOT NULL,
  round INTEGER NOT NULL, position INTEGER NOT NULL, PRIMARY KEY(goal_id, child_key, sha));
CREATE TABLE pending(id INTEGER PRIMARY KEY AUTOINCREMENT, goal_id TEXT NOT NULL, child_key TEXT, action TEXT NOT NULL,
  payload TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE counters(goal_id TEXT NOT NULL, name TEXT NOT NULL, value INTEGER NOT NULL, PRIMARY KEY(goal_id, name));
`

// ErrStateVersion means workflow.db is not a database of UserVersion.
var ErrStateVersion = errors.New("workflow: workflow.db has an unexpected user_version")

// StatePath is <home>/db/workflow.db.
func StatePath(home string) string { return filepath.Join(home, "db", "workflow.db") }

// OpenState opens workflow.db, creating it (mode 0600, schema, user_version 1) when missing, with the pragmas of
// factorydb.Open. A database of another user_version, or an unversioned one that already holds tables, is refused.
func OpenState(path string) (*sql.DB, error) {
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return nil, err
	}
	if f, err := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600); err == nil {
		f.Close()
	} else if !errors.Is(err, os.ErrExist) {
		return nil, err
	}
	q := url.Values{}
	q.Set("mode", "rw")
	q.Add("_pragma", "busy_timeout(30000)")
	q.Add("_pragma", "journal_mode(WAL)")
	q.Add("_pragma", "foreign_keys(1)")
	d, err := sql.Open("sqlite", (&url.URL{Scheme: "file", Path: path, RawQuery: q.Encode()}).String())
	if err != nil {
		return nil, err
	}
	d.SetMaxOpenConns(1) // one connection, so BEGIN IMMEDIATE below and the statements after it share it
	if err := initState(d); err != nil {
		d.Close()
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	return d, nil
}

// initState creates the schema on a new file under a write lock (two first runs cannot both create it), then checks
// user_version.
func initState(d *sql.DB) (err error) {
	if _, err = d.Exec("BEGIN IMMEDIATE"); err != nil {
		return err
	}
	defer func() {
		if err != nil {
			d.Exec("ROLLBACK")
		}
	}()
	var v, tables int
	if err = d.QueryRow("PRAGMA user_version").Scan(&v); err != nil {
		return err
	}
	if err = d.QueryRow("SELECT count(*) FROM sqlite_master").Scan(&tables); err != nil {
		return err
	}
	switch {
	case v == 0 && tables == 0:
		if _, err = d.Exec(schema); err != nil {
			return err
		}
		if _, err = d.Exec(fmt.Sprintf("PRAGMA user_version = %d", UserVersion)); err != nil {
			return err
		}
	case v != UserVersion:
		return fmt.Errorf("%w: has %d (%d tables), engine expects %d", ErrStateVersion, v, tables, UserVersion)
	}
	_, err = d.Exec("COMMIT")
	return err
}
