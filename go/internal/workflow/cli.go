package workflow

import (
	"database/sql"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"syscall"

	"factory/go/internal/buildinfo"
	"factory/go/internal/factorydb"
	"factory/go/internal/identity"
)

// Bin is the name of the built engine (bin/factory_cli.py WORKFLOW_BIN).
const Bin = "factory-workflow"

const usage = "usage: factory wf {version | status [--goal ID] | tick | incidents [--goal ID] [--kind KIND] [--json] | " +
	"start --story KEY [--story KEY ...] [--workflow simple|medium|huge] [--project ID] | resume --goal ID [--fresh-builder] | " +
	"blocked CHILD --reason TEXT | built | review CHILD pass|changes --notes FILE | tsr ...}"

// Exit codes, as the Python CLI's die().
const (
	exitOK     = 0
	exitErr    = 1
	exitUsage  = 2
	exitRefuse = 3
)

// Main runs one engine command and returns its exit code.
func Main(args []string, env identity.Env, stdout, stderr io.Writer) int {
	if len(args) == 0 {
		fmt.Fprintln(stderr, usage)
		return exitUsage
	}
	home := env.Home()
	fail := func(code int, err error) int {
		fmt.Fprintf(stderr, "factory wf: %v\n", err)
		return code
	}
	cmd, rest := args[0], args[1:]
	switch cmd {
	case "tsr":
		return tsrMain(rest, env, stdout, stderr)
	case "start", "resume", "blocked", "built", "review":
		return runMain(cmd, rest, env, stdout, stderr)
	}
	fs := flag.NewFlagSet("factory wf "+cmd, flag.ContinueOnError)
	fs.SetOutput(stderr)
	goal := fs.String("goal", "", "only this goal")
	var kind *string
	var asJSON *bool
	if cmd == "incidents" {
		kind = fs.String("kind", "", "only this kind")
		asJSON = fs.Bool("json", false, "print the full detail as JSON")
	}
	if err := fs.Parse(rest); err != nil || fs.NArg() > 0 {
		fmt.Fprintln(stderr, usage)
		return exitUsage
	}
	switch cmd {
	case "version":
		fmt.Fprintf(stdout, "%s %s\n", Bin, buildinfo.Version)
		return exitOK
	case "status":
		st, err := OpenState(StatePath(home))
		if err != nil {
			return fail(exitErr, err)
		}
		defer st.Close()
		se := &Engine{Env: env, State: st}
		if fdb, err := factorydb.Open(factorydb.ResolvePath(home)); err == nil { // best effort: origin and PR
			defer fdb.Close()
			se.Factory = fdb.DB
		}
		runs, err := se.Runs(*goal)
		if err != nil {
			return fail(exitErr, err)
		}
		if len(runs) == 0 {
			fmt.Fprintln(stdout, "no runs")
		}
		for _, r := range runs {
			wf := r.Workflow
			if o := se.workflowOrigin(r.GoalID); o != "" {
				wf += " (" + o + ")"
			}
			fmt.Fprintf(stdout, "%s %s %s %s\n", r.GoalID, r.StoryKey, wf, r.State)
			if contains([]string{string(RunMerging), string(RunLinking), string(RunReporting), string(RunClosing),
				string(RunAnnouncing), string(RunDone)}, string(r.State)) {
				if pr := prURL(se.Factory, r.TaskID); pr != "" {
					fmt.Fprintf(stdout, "  pr: %s\n", pr)
				}
			}
			kids, err := se.children(r.GoalID)
			if err != nil {
				return fail(exitErr, err)
			}
			if counts := storyCounts(kids); len(counts) > 1 { // a batch; a single story prints as before
				for _, s := range counts {
					fmt.Fprintf(stdout, "  story %s: %d of %d children reviewed\n", s.key, s.done, s.total)
				}
			}
			if *goal == "" {
				continue
			}
			for _, c := range kids {
				fmt.Fprintf(stdout, "  %s %s rounds=%d\n", c.key, c.state, c.rounds)
			}
		}
		return exitOK
	case "tick":
		// the engine's steps run with the owner's rights, so only the owner (the factory's tick) may start them
		if _, code, err := requireRole(env, home); err != nil {
			return fail(code, fmt.Errorf("factory wf tick is for the owner (the factory tick) only: %v", err))
		}
		unlock, held, err := lock(filepath.Join(home, "run", "workflow.lock"))
		if err != nil {
			return fail(exitErr, err)
		}
		if held {
			return exitOK // another tick is running; it covers this minute
		}
		defer unlock()
		e, closeAll, err := open(env, home)
		if err != nil {
			return fail(exitErr, err)
		}
		defer closeAll()
		if err := e.Tick(); err != nil {
			return fail(exitErr, err)
		}
		return exitOK
	case "incidents":
		if _, code, err := requireRole(env, home, roleBoss); err != nil {
			return fail(code, err)
		}
		if *kind != "" && !validKind(Kind(*kind)) {
			return fail(exitUsage, fmt.Errorf("unknown kind %q; one of %v", *kind, Kinds))
		}
		st, err := OpenState(StatePath(home))
		if err != nil {
			return fail(exitErr, err)
		}
		defer st.Close()
		if err := printIncidents(st, *goal, *kind, *asJSON, stdout); err != nil {
			return fail(exitErr, err)
		}
		return exitOK
	}
	fmt.Fprintln(stderr, usage)
	return exitUsage
}

func validKind(k Kind) bool {
	for _, x := range Kinds {
		if x == k {
			return true
		}
	}
	return false
}

// open opens workflow.db and factory.db for a command that may write events.
func open(env identity.Env, home string) (*Engine, func(), error) {
	st, err := OpenState(StatePath(home))
	if err != nil {
		return nil, nil, err
	}
	fdb, err := factorydb.Open(factorydb.ResolvePath(home))
	if err != nil {
		st.Close()
		return nil, nil, err
	}
	e := &Engine{Env: env, Home: home, State: st, Factory: fdb.DB}
	if d, err := newDeps(env); err == nil {
		e.Deps = d
	} else {
		e.depsErr = err
	}
	return e, func() { fdb.Close(); st.Close() }, nil
}

// lock takes the engine's non-blocking lock file; held reports that another process has it.
func lock(path string) (unlock func(), held bool, err error) {
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return nil, false, err
	}
	f, err := os.OpenFile(path, os.O_CREATE|os.O_RDWR, 0o600)
	if err != nil {
		return nil, false, err
	}
	if err := syscall.Flock(int(f.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
		f.Close()
		if errors.Is(err, syscall.EWOULDBLOCK) {
			return nil, true, nil
		}
		return nil, false, err
	}
	return func() { f.Close() }, false, nil
}

// Factory roles the engine's commands admit (the owner always passes).
const (
	roleOwner         = "owner"
	roleBoss          = "boss"
	roleCoder         = "coder"
	roleReviewer      = "reviewer"
	roleQA            = "qa"
	roleStaffEngineer = "staff-engineer"
)

// requireRole lets the owner and the listed factory roles through: exit 3 otherwise, failing closed when the role is
// unknown. It returns the caller's name.
func requireRole(env identity.Env, home string, allowed ...string) (string, int, error) {
	path := factorydb.ResolvePath(home)
	var fdb *factorydb.DB
	defer func() {
		if fdb != nil {
			fdb.Close()
		}
	}()
	openDB := func() (*factorydb.DB, error) {
		if fdb == nil {
			d, err := factorydb.Open(path)
			if err != nil {
				return nil, err
			}
			fdb = d
		}
		return fdb, nil
	}
	who, err := env.Resolve(openDB)
	var ee *identity.ExitError
	if errors.As(err, &ee) {
		return "", ee.Code, err
	}
	if err != nil {
		return "", exitRefuse, fmt.Errorf("cannot resolve the caller's identity: %v", err)
	}
	if who == roleOwner {
		return who, exitOK, nil
	}
	role := identity.Unknown
	if d, err := openDB(); err == nil {
		var r string
		if d.QueryRow("SELECT role FROM agents WHERE name=?", who).Scan(&r) == nil {
			role = r
		}
	}
	for _, a := range allowed {
		if role == a {
			return who, exitOK, nil
		}
	}
	return "", exitRefuse, fmt.Errorf("role '%s' (%s) may not do this; allowed: %s", role, who, strings.Join(allowed, ", "))
}

func printIncidents(st *sql.DB, goal, kind string, asJSON bool, w io.Writer) error {
	rows, err := st.Query(`SELECT id, goal_id, COALESCE(child_key, ''), kind, cause, actor, COALESCE(round, 0),
		COALESCE(base_sha, ''), COALESCE(head_sha, ''), summary, detail, created FROM incidents
		WHERE (?1 = '' OR goal_id = ?1) AND (?2 = '' OR kind = ?2) ORDER BY id DESC`, goal, kind)
	if err != nil {
		return err
	}
	defer rows.Close()
	type out struct {
		ID      int64           `json:"id"`
		Goal    string          `json:"goal"`
		Child   string          `json:"child,omitempty"`
		Kind    string          `json:"kind"`
		Cause   string          `json:"cause"`
		Actor   string          `json:"actor"`
		Round   int             `json:"round,omitempty"`
		BaseSHA string          `json:"base_sha,omitempty"`
		HeadSHA string          `json:"head_sha,omitempty"`
		Summary string          `json:"summary"`
		Detail  json.RawMessage `json:"detail"`
		Created string          `json:"created"`
	}
	all := []out{}
	for rows.Next() {
		var o out
		var detail string
		if err := rows.Scan(&o.ID, &o.Goal, &o.Child, &o.Kind, &o.Cause, &o.Actor, &o.Round, &o.BaseSHA, &o.HeadSHA,
			&o.Summary, &detail, &o.Created); err != nil {
			return err
		}
		o.Detail = json.RawMessage(detail)
		all = append(all, o)
	}
	if err := rows.Err(); err != nil {
		return err
	}
	if asJSON {
		enc := json.NewEncoder(w)
		enc.SetIndent("", " ")
		return enc.Encode(all)
	}
	if len(all) == 0 {
		fmt.Fprintln(w, "no incidents")
	}
	for _, o := range all {
		child := o.Child
		if child == "" {
			child = "-"
		}
		fmt.Fprintf(w, "%d %s %s %s %s/%s %s: %s\n", o.ID, o.Created, o.Goal, child, o.Kind, o.Cause, o.Actor, o.Summary)
	}
	return nil
}
