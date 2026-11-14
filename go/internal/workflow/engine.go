package workflow

import (
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"

	"factory/go/internal/identity"
)

// ActorEngine is the actor of what the engine does on its own.
const ActorEngine = "engine"

// EventEntity is events.entity of the factory events the engine writes.
const EventEntity = "workflow"

const tsLayout = "2006-01-02T15:04:05-07:00"

// Engine holds the open databases of one engine command.
type Engine struct {
	Env     identity.Env
	Home    string
	State   *sql.DB // workflow.db
	Factory *sql.DB // factory.db: read, plus events through Env.EventAs
	Deps    *Deps   // Taskosaur, the factory CLI, git; nil when they could not be set up (depsErr says why)
	depsErr error
}

// deps returns the dependencies or why they are missing.
func (e *Engine) deps() (*Deps, error) {
	if e.Deps == nil {
		if e.depsErr == nil {
			e.depsErr = errors.New("no dependencies")
		}
		return nil, e.depsErr
	}
	return e.Deps, nil
}

// Run is one row of runs.
type Run struct {
	GoalID, StoryKey, Workflow, TaskID string
	State                              RunState
}

// Incident is one rejection, failure, warning or escalation, with everything known at that moment in Detail.
// Empty strings and a zero Round are stored as NULL.
type Incident struct {
	GoalID, ChildKey string
	Kind             Kind
	Cause            Cause
	Actor            string
	Round            int
	BaseSHA, HeadSHA string
	Summary          string
	Detail           map[string]any
}

func null(s string) any {
	if s == "" {
		return nil
	}
	return s
}

// Record stores the incident and writes exactly one factory event for it (entity workflow, entity id the goal,
// action the kind, detail "cause=<cause> incident=<id>"). No free text goes into the event: the events table is shown
// by a UI without login. Every later step records its rejections, failures, warnings and escalations through here.
func (e *Engine) Record(inc Incident) (int64, error) {
	if inc.Detail == nil {
		inc.Detail = map[string]any{}
	}
	detail, err := json.Marshal(inc.Detail)
	if err != nil {
		return 0, fmt.Errorf("incident detail: %w", err)
	}
	var round any
	if inc.Round > 0 {
		round = inc.Round
	}
	res, err := e.State.Exec(`INSERT INTO incidents(goal_id, child_key, kind, cause, actor, round, base_sha, head_sha,
		summary, detail, created) VALUES(?,?,?,?,?,?,?,?,?,?,?)`, inc.GoalID, null(inc.ChildKey), string(inc.Kind),
		string(inc.Cause), inc.Actor, round, null(inc.BaseSHA), null(inc.HeadSHA), inc.Summary, string(detail),
		e.Env.Now().Format(tsLayout))
	if err != nil {
		return 0, err
	}
	id, err := res.LastInsertId()
	if err != nil {
		return 0, err
	}
	return id, e.Env.EventAs(e.Factory, inc.Actor, EventEntity, inc.GoalID, string(inc.Kind),
		fmt.Sprintf("cause=%s incident=%d", inc.Cause, id))
}

// advance moves one run forward by one step. A variable, so tests can make it fail.
var advance = func(e *Engine, r Run) error {
	switch r.State {
	case RunBuilding:
		return e.advanceBuilding(r)
	case RunBuilt: // late fixes still run; when every child is reviewed the builder opens the PR
		if err := e.advanceBuilding(r); err != nil {
			return err
		}
		return e.openPR(r)
	case RunMerging:
		return e.advanceMerging(r)
	case RunLinking, RunReporting, RunClosing, RunAnnouncing:
		return e.finish(r)
	}
	return nil
}

// Runs lists the runs, oldest first; goal "" means all.
func (e *Engine) Runs(goal string) ([]Run, error) {
	rows, err := e.State.Query(`SELECT goal_id, story_key, workflow, COALESCE(task_id, ''), state FROM runs
		WHERE ?1 = '' OR goal_id = ?1 ORDER BY created, goal_id`, goal)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Run
	for rows.Next() {
		var r Run
		if err := rows.Scan(&r.GoalID, &r.StoryKey, &r.Workflow, &r.TaskID, &r.State); err != nil {
			return nil, err
		}
		out = append(out, r)
	}
	return out, rows.Err()
}

// Tick advances every run once. A run whose step fails or panics gets an engine-error incident and the others still
// run. The error returned is only about reading the runs or recording an incident.
func (e *Engine) Tick() error {
	runs, err := e.Runs("")
	if err != nil {
		return err
	}
	for _, r := range runs {
		if stepErr := safeAdvance(e, r); stepErr != nil {
			if _, err := e.Record(Incident{GoalID: r.GoalID, Kind: KindFailure, Cause: CauseEngineError,
				Actor: ActorEngine, Summary: "advance failed: " + firstLine(stepErr.Error()),
				Detail: map[string]any{"error": stepErr.Error(), "run_state": string(r.State), "story": r.StoryKey,
					"workflow": r.Workflow, "task_id": r.TaskID}}); err != nil {
				return fmt.Errorf("recording the failure of %s: %w", r.GoalID, err)
			}
		}
	}
	return nil
}

func safeAdvance(e *Engine, r Run) (err error) {
	defer func() {
		if p := recover(); p != nil {
			err = fmt.Errorf("panic: %v", p)
		}
	}()
	if e.Deps != nil { // queued comments, marks and mails first, each once
		if err := e.runPending(r); err != nil {
			return err
		}
	}
	return advance(e, r)
}

func firstLine(s string) string {
	for i, c := range s {
		if c == '\n' {
			return s[:i]
		}
	}
	return s
}
