package workflow

import (
	"database/sql"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"factory/go/internal/factorydb"
	"factory/go/internal/factorydb/dbtest"
	"factory/go/internal/identity"
	"factory/go/internal/tsr"
)

// repoRoot is the checkout this test runs in: the real HM-31 templates are loaded from it.
func repoRoot(t *testing.T) string {
	wd, _ := os.Getwd()
	return filepath.Join(wd, "..", "..", "..")
}

type fakeTracker struct {
	tasks    map[string]tsr.Task
	children map[string][]string
	comments []string // "taskID|markdown"
	checks   []string // "taskID|kind|result|agent|ref"
	statuses []string // "taskID|statusID"
	links    []string // "taskID|sha"
	writes   int      // Comment, SetStatus and LinkCommit calls so far
	failOn   int      // that write (1-based) answers 500 once; 0 = never
}

// write counts one write and fails it when it is the one failOn names.
func (f *fakeTracker) write() error {
	f.writes++
	if f.writes == f.failOn {
		return &tsr.Error{Method: "POST", Path: "/x", Status: 500, Message: "Internal server error"}
	}
	return nil
}

func (f *fakeTracker) Comment(id, md string) error {
	if err := f.write(); err != nil {
		return err
	}
	f.comments = append(f.comments, id+"|"+md)
	return nil
}

func (f *fakeTracker) Statuses(string) ([]tsr.Status, error) {
	review := tsr.UserActionReview
	return []tsr.Status{{ID: "s-todo", Category: tsr.CategoryTodo, Position: 1},
		{ID: "s-prog", Name: "In Progress", Category: tsr.CategoryInProgress, Position: 2},
		{ID: "s-rev", Name: "In Review", Category: tsr.CategoryInProgress, Position: 3, UserAction: &review},
		{ID: "s-done", Name: "Done", Category: tsr.CategoryDone, Position: 4}}, nil
}

// SetStatus records the move and applies it to the stored task, as Taskosaur would.
func (f *fakeTracker) SetStatus(id, status string) error {
	if err := f.write(); err != nil {
		return err
	}
	f.statuses = append(f.statuses, id+"|"+status)
	sts, _ := f.Statuses("")
	for k, t := range f.tasks {
		if t.ID != id {
			continue
		}
		for _, s := range sts {
			if s.ID == status {
				t.Status = s
			}
		}
		f.tasks[k] = t
	}
	return nil
}

func (f *fakeTracker) LinkCommit(ids []string, sha, _ string) error {
	if err := f.write(); err != nil {
		return err
	}
	for _, id := range ids {
		f.links = append(f.links, id+"|"+sha)
	}
	return nil
}

func (f *fakeTracker) AgentCheck(id string, kind tsr.CheckKind, res *tsr.CheckResult, agent, ref string) error {
	if err := f.write(); err != nil {
		return err
	}
	r := "null"
	if res != nil {
		r = string(*res)
	}
	f.checks = append(f.checks, strings.Join([]string{id, string(kind), r, agent, ref}, "|"))
	return nil
}

func (f *fakeTracker) TaskByKey(k string) (tsr.Task, error) {
	t, ok := f.tasks[k]
	if !ok {
		return t, &tsr.Error{Method: "GET", Path: "/tasks/key/" + k, Status: 404, Message: "not found"}
	}
	return t, nil
}

func (f *fakeTracker) Children(s tsr.Task) ([]tsr.Task, error) {
	var out []tsr.Task
	for _, k := range f.children[s.Key] {
		row := f.tasks[k] // as Taskosaur's list does: a row has no description and no tests field
		row.Description, row.E2ETests = "", ""
		out = append(out, row)
	}
	return out, nil
}

// fakeFactory plays bin/factory against the test factory.db.
type fakeFactory struct {
	t         *testing.T
	db        *sql.DB
	calls     []string
	stdins    []string
	spawnFail bool
	org       string
	refuse    int // the next n spawns are refused (a refusal that clears by itself)
	mailFail  int // the next n mails fail
	mailsOK   map[string]int
}

func (f *fakeFactory) Run(stdin string, args ...string) (string, error) {
	f.calls = append(f.calls, strings.Join(args, " "))
	f.stdins = append(f.stdins, stdin)
	switch args[0] + " " + args[1] {
	case "goal new":
		f.db.Exec("INSERT INTO goals(id, org, project_id) VALUES('G-001', ?, 'p1')", f.org)
		return "G-001\n", nil
	case "task add":
		f.db.Exec(`INSERT INTO tasks(id, goal_id, branch, worktree, status, updated)
			VALUES('T-0001', 'G-001', 'factory/t-0001', '/wt', 'todo', '2026-11-14T12:00:00+01:00')`)
		return "warning: T-0001 title has no [SCn] tag\nT-0001\n", nil
	case "spawn coder", "spawn reviewer":
		if f.refuse > 0 {
			f.refuse--
			return "", &CmdError{Cmd: "factory spawn", Err: errors.New("exit status 2"),
				Stderr: "factory: its old pane could not be confirmed closed\n"}
		}
		if f.spawnFail {
			return "", &CmdError{Cmd: "factory spawn", Err: errors.New("exit status 2"), Stderr: "factory: spawn gate: no memory\n"}
		}
		name := flagValue(args, "--name")
		if flagValue(args, "--resume") != "" { // a resumed session: the same row, live again
			f.db.Exec("UPDATE agents SET status='live' WHERE name=?", name)
			return "SPAWNED " + name + " (resumed)\n", nil
		}
		f.db.Exec(`INSERT INTO agents(name, role, task_id, status, session_id) VALUES(?, ?, 'T-0001', 'live', ?)
			ON CONFLICT(name) DO UPDATE SET status='live', session_id=excluded.session_id`, name, args[1], "sess-"+name)
		return "SPAWNED " + name + "\n", nil
	}
	if args[0] == "msg" {
		if f.mailFail > 0 {
			f.mailFail--
			return "", &CmdError{Cmd: "factory msg", Err: errors.New("exit status 1"), Stderr: "factory: database is locked\n"}
		}
		if f.mailsOK == nil {
			f.mailsOK = map[string]int{}
		}
		f.mailsOK[args[1]]++
		return "M1 → boss\n", nil
	}
	return "", fmt.Errorf("unexpected factory call %v", args)
}

func flagValue(args []string, flag string) string {
	for i, a := range args {
		if a == flag && i+1 < len(args) {
			return args[i+1]
		}
	}
	return ""
}

// fakeMergeSHA is the full hash the fake repository resolves the merged event's prefix to.
const fakeMergeSHA = "0abc1234eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"

// fakeGit plays the builder's worktree: a branch whose commits are `log`, oldest first, pushed unless unpushed.
type fakeGit struct {
	calls    []string
	log      []commit // the branch since the run started, oldest first
	dirty    bool
	unpushed bool
}

func (g *fakeGit) commit(sha, subject string) {
	g.log = append(g.log, commit{sha: sha, subject: subject})
}

func (g *fakeGit) head() string {
	if len(g.log) == 0 {
		return "base0"
	}
	return g.log[len(g.log)-1].sha
}

func (g *fakeGit) Run(dir string, args ...string) (string, error) {
	g.calls = append(g.calls, args[0])
	switch args[0] {
	case "status":
		if g.dirty {
			return " M cli.go", nil
		}
	case "log":
		var lines []string
		for _, c := range g.log {
			lines = append(lines, c.sha+"\x1f"+c.subject)
		}
		return strings.Join(lines, "\n"), nil
	case "rev-parse":
		switch {
		case len(args) > 1 && args[1] == "--verify":
			return fakeMergeSHA, nil
		case args[1] == "HEAD":
			return g.head(), nil
		case g.unpushed:
			return "older", nil
		}
		return g.head(), nil
	case "merge-base":
		return "base0", nil
	}
	return "", nil
}

type startRig struct {
	t       *testing.T
	env     identity.Env
	home    string
	tracker *fakeTracker
	factory *fakeFactory
	git     *fakeGit
	fdb     *sql.DB
}

func enriched(key string) tsr.Task {
	return tsr.Task{ID: "id-" + key, Key: key, Title: "Title " + key, ProjectID: "p", Size: "S", Complexity: 2,
		Description: "## Goal\nx\n\n## Acceptance criteria\n\n- [ ] it works\n\n## Notes\ny", E2ETests: "none: no UI"}
}

func newStartRig(t *testing.T) *startRig {
	env, home := testEnv(t, "")
	fdb := dbtest.Raw(t, factorydb.ResolvePath(home))
	t.Cleanup(func() { fdb.Close() })
	for _, ddl := range []string{
		"CREATE TABLE goals(id TEXT PRIMARY KEY, org TEXT NOT NULL DEFAULT 'claude', project_id TEXT)",
		"CREATE TABLE tasks(id TEXT PRIMARY KEY, goal_id TEXT, branch TEXT, worktree TEXT, status TEXT, pr_url TEXT, updated TEXT)",
		"CREATE TABLE projects(id TEXT PRIMARY KEY, base_branch TEXT, repo_path TEXT)",
		"INSERT INTO projects VALUES('p1', 'main', '/repo')",
	} {
		if _, err := fdb.Exec(ddl); err != nil {
			t.Fatal(err)
		}
	}
	r := &startRig{t: t, env: env, home: home, fdb: fdb, git: &fakeGit{},
		factory: &fakeFactory{t: t, db: fdb, org: defaultOrg},
		tracker: &fakeTracker{tasks: map[string]tsr.Task{}, children: map[string][]string{}}}
	story := enriched("ST-1")
	r.tracker.tasks["ST-1"] = story
	for _, k := range []string{"C-1", "C-2", "C-3"} {
		r.tracker.tasks[k] = enriched(k)
		r.tracker.children["ST-1"] = append(r.tracker.children["ST-1"], k)
	}
	old := newDeps
	t.Cleanup(func() { newDeps = old })
	newDeps = func(identity.Env) (*Deps, error) {
		return &Deps{Tracker: func() (Tracker, error) { return r.tracker, nil }, Factory: r.factory, Git: r.git,
			SrcDir: repoRoot(t)}, nil
	}
	return r
}

func (r *startRig) as(agent string) identity.Env {
	e := r.env
	vars := map[string]string{"FACTORY_HOME": r.home, "HOME": r.home, "FACTORY_AGENT": agent}
	e.Getenv = func(k string) string { return vars[k] }
	e.LookupEnv = func(k string) (string, bool) { v, ok := vars[k]; return v, ok && v != "" }
	return e
}

func (r *startRig) runCount() int {
	st, _ := OpenState(StatePath(r.home))
	defer st.Close()
	var n int
	st.QueryRow("SELECT count(*) FROM runs").Scan(&n)
	return n
}

func TestStartCreatesGoalTaskPluginChildrenAndBuilder(t *testing.T) {
	r := newStartRig(t)
	code, out, errs := run(r.env, "start", "--story", "ST-1", "--project", "p1")
	if code != 0 {
		t.Fatalf("start: %d %q %q", code, out, errs)
	}
	want := []string{"goal new", "task add", "spawn coder"}
	if len(r.factory.calls) != 3 {
		t.Fatalf("calls %v", r.factory.calls)
	}
	for i, w := range want {
		if !strings.HasPrefix(r.factory.calls[i], w) {
			t.Fatalf("call %d %q, want %s", i, r.factory.calls[i], w)
		}
	}
	if !strings.Contains(r.factory.calls[0], "--project p1") || !strings.Contains(r.factory.calls[0], "- [ ] it works") {
		t.Fatalf("goal new %q", r.factory.calls[0])
	}
	if !strings.Contains(r.factory.calls[2], "--name coder-t-0001 --prompt -") {
		t.Fatalf("spawn %q", r.factory.calls[2])
	}
	kick := r.factory.stdins[2]
	if placeholderRE.MatchString(kick) || !strings.Contains(kick, "`coder-t-0001`") ||
		!strings.Contains(kick, "branch `factory/t-0001`") || !strings.Contains(kick, "children ST-1") {
		t.Fatalf("kickoff %q", kick)
	}
	skill := filepath.Join(r.home, "roles", "plugins", "goals", "G-001", "story-run", "skills", "story-builder", "SKILL.md")
	if st, err := os.Stat(skill); err != nil || st.Mode().Perm() != 0o644 {
		t.Fatalf("skill: %v %v", st, err)
	}
	if code, out, _ := run(r.env, "status"); code != 0 || out != "G-001 ST-1 huge (chosen) building\n" {
		t.Fatalf("status %q", out)
	}
	st, _ := OpenState(StatePath(r.home))
	defer st.Close()
	rows, _ := st.Query("SELECT child_key, story_key, position, state FROM children ORDER BY position")
	var got []string
	for rows.Next() {
		var k, s, state string
		var p int
		rows.Scan(&k, &s, &p, &state)
		got = append(got, fmt.Sprintf("%s/%s/%d/%s", k, s, p, state))
	}
	rows.Close()
	if strings.Join(got, " ") != "C-1/ST-1/1/todo C-2/ST-1/2/todo C-3/ST-1/3/todo" {
		t.Fatalf("children %v", got)
	}
}

func TestStartRefusesAnUnpreparedChildAndMakesNothing(t *testing.T) {
	r := newStartRig(t)
	c2 := r.tracker.tasks["C-2"]
	c2.Description = "## Goal\nno criteria here"
	r.tracker.tasks["C-2"] = c2
	c3 := r.tracker.tasks["C-3"]
	c3.E2ETests = " "
	r.tracker.tasks["C-3"] = c3
	code, _, errs := run(r.env, "start", "--story", "ST-1")
	if code != exitUsage || !strings.Contains(errs, "C-2: missing acceptance criteria") || !strings.Contains(errs, "C-3: missing tests") {
		t.Fatalf("refusal: %d %q", code, errs)
	}
	if len(r.factory.calls) != 0 || r.runCount() != 0 {
		t.Fatalf("made something: %v, %d runs", r.factory.calls, r.runCount())
	}
	if _, err := os.Stat(filepath.Join(r.home, "roles")); err == nil {
		t.Fatal("plugin folder written")
	}
}

func TestEnrichedRule(t *testing.T) {
	cases := []struct {
		desc, tests string
		miss        string
	}{
		{"## Acceptance criteria\n- [ ] a", "none: nothing to test end to end", ""},
		{"## acceptance criteria:\n1. a", "spec x", ""},
		{"## Acceptance Criteria\n- [x] done", "t", ""},
		{"## Goal\nx", "t", "acceptance criteria"},
		{"## Acceptance criteria\njust prose\n## Next\n- item after", "t", "acceptance criteria"},
		{"## Acceptance criteria\n- a", "", "tests"},
		{"", "t", "description, acceptance criteria"},
	}
	for _, c := range cases {
		got := strings.Join(missingFields(tsr.Task{Description: c.desc, E2ETests: c.tests}), ", ")
		if got != c.miss {
			t.Errorf("%q / %q: missing %q, want %q", c.desc, c.tests, got, c.miss)
		}
	}
}

func TestFillRefusesUnknownOrUnfilledPlaceholders(t *testing.T) {
	if _, err := fill("k", "hi {agent} on {child}", map[string]string{"agent": "a"}); err == nil || !strings.Contains(err.Error(), "{child}") {
		t.Fatalf("unknown: %v", err)
	}
	if _, err := fill("k", "hi {agent}", map[string]string{"agent": ""}); err == nil {
		t.Fatal("empty value accepted")
	}
	if s, err := fill("k", "{a}{b}", map[string]string{"a": "{b}", "b": "x"}); err != nil || s != "{b}x" {
		t.Fatalf("one pass: %q %v", s, err)
	}
}

func TestSpawnFailureLeavesAFailedRunAndBlocksASecondStart(t *testing.T) {
	r := newStartRig(t)
	r.factory.spawnFail = true
	code, _, errs := run(r.env, "start", "--story", "ST-1")
	if code != exitErr || !strings.Contains(errs, "failed at spawn") {
		t.Fatalf("start: %d %q", code, errs)
	}
	if _, out, _ := run(r.env, "status"); out != "G-001 ST-1 huge (chosen) failed\n" {
		t.Fatalf("status %q", out)
	}
	_, out, _ := run(r.env, "incidents", "--json")
	if !strings.Contains(out, `"cause": "spawn-refused"`) || !strings.Contains(out, "no memory") {
		t.Fatalf("incident %s", out)
	}
	n := len(r.factory.calls)
	code, _, errs = run(r.env, "start", "--story", "ST-1")
	if code != exitUsage || !strings.Contains(errs, "already has run G-001 (state failed)") || len(r.factory.calls) != n {
		t.Fatalf("second start: %d %q", code, errs)
	}
}

func TestTickRecordsAChildInReviewOnce(t *testing.T) {
	r := newStartRig(t)
	if code, _, errs := run(r.env, "start", "--story", "ST-1"); code != 0 {
		t.Fatal(errs)
	}
	r.setReview("C-1", true) // the builder records its commits and sets it In Review (HM-35)
	if code, _, errs := run(r.env, "tick"); code != 0 {
		t.Fatal(errs)
	}
	st, _ := OpenState(StatePath(r.home))
	defer st.Close()
	var state, base, head string
	st.QueryRow("SELECT state, base_sha, head_sha FROM children WHERE child_key='C-1'").Scan(&state, &base, &head)
	if state != string(ChildReviewing) || base != "base0" || head != "C-1-1" { // recorded, and its review started (HM-25)
		t.Fatalf("C-1: %s %s %s", state, base, head)
	}
	gitCalls := len(r.git.calls)
	if code, _, errs := run(r.env, "tick"); code != 0 || len(r.git.calls) != gitCalls {
		t.Fatalf("second tick: %d %q, git %v", code, errs, r.git.calls)
	}
	if _, out, _ := run(r.env, "incidents"); out != "no incidents\n" {
		t.Fatalf("incidents %q", out)
	}
}

func TestBuilderEndedWithoutSessionBlocksTheRunOnce(t *testing.T) {
	r := newStartRig(t)
	run(r.env, "start", "--story", "ST-1")
	r.fdb.Exec("UPDATE agents SET status='done', session_id=NULL WHERE name='coder-t-0001'")
	run(r.env, "tick")
	run(r.env, "tick")
	if _, out, _ := run(r.env, "status"); out != "G-001 ST-1 huge (chosen) blocked\n" {
		t.Fatalf("status %q", out)
	}
	mails := 0
	for _, c := range r.factory.calls {
		if strings.HasPrefix(c, "msg boss") {
			mails++
		}
	}
	if mails != 1 {
		t.Fatalf("mails %d: %v", mails, r.factory.calls)
	}
}

func TestBuiltAndBlockedOnlyForTheRunsBuilder(t *testing.T) {
	r := newStartRig(t)
	run(r.env, "start", "--story", "ST-1")
	r.fdb.Exec("INSERT INTO agents(name, role, task_id, status) VALUES('coder-x', 'coder', 'T-0999', 'live')")
	for _, who := range []string{"coder-x", "owner"} {
		if code, _, errs := run(r.as(who), "built"); code != exitRefuse || !strings.Contains(errs, "only a run's builder") {
			t.Fatalf("%s built: %d %q", who, code, errs)
		}
	}
	if code, _, _ := run(r.as("coder-t-0001"), "blocked", "C-9", "--reason", "x"); code != exitErr {
		t.Fatalf("foreign child: %d", code)
	}
	code, out, errs := run(r.as("coder-t-0001"), "blocked", "C-2", "--reason", "the spec contradicts cli.go")
	if code != 0 || !strings.Contains(out, "blocked on C-2") {
		t.Fatalf("blocked: %d %q %q", code, out, errs)
	}
	last := r.factory.calls[len(r.factory.calls)-1]
	if !strings.HasPrefix(last, "msg boss story run G-001 blocked on C-2 - --kind decision --goal G-001") ||
		!strings.Contains(r.factory.stdins[len(r.factory.stdins)-1], "the spec contradicts cli.go") {
		t.Fatalf("mail %q", last)
	}
	_, inc, _ := run(r.env, "incidents", "--json")
	if !strings.Contains(inc, `"cause": "builder-blocked"`) || !strings.Contains(inc, `"child": "C-2"`) {
		t.Fatalf("incident %s", inc)
	}
	if code, out, _ := run(r.as("coder-t-0001"), "built"); code != 0 || out != "run G-001: built\n" {
		t.Fatalf("built: %d %q", code, out)
	}
}

func TestBuilderNameFollowsTheOrgRule(t *testing.T) {
	r := newStartRig(t)
	r.factory.org = "cursor"
	if code, _, errs := run(r.env, "start", "--story", "ST-1"); code != 0 {
		t.Fatal(errs)
	}
	if !strings.Contains(r.factory.calls[2], "--name cursor-coder-t-0001") {
		t.Fatalf("spawn %q", r.factory.calls[2])
	}
}

func TestStartTakesTheOnlyProjectAndRefusesOneWithoutARepository(t *testing.T) {
	r := newStartRig(t)
	if code, _, errs := run(r.env, "start", "--story", "ST-1", "--project", "nope"); code != exitUsage ||
		!strings.Contains(errs, "no factory project nope") || len(r.factory.calls) != 0 {
		t.Fatalf("unknown project: %d %q %v", code, errs, r.factory.calls)
	}
	r.fdb.Exec("INSERT INTO projects VALUES('bare', 'main', NULL)")
	if code, _, errs := run(r.env, "start", "--story", "ST-1", "--project", "bare"); code != exitUsage ||
		!strings.Contains(errs, "has no repository path") || len(r.factory.calls) != 0 {
		t.Fatalf("project without a repository: %d %q", code, errs)
	}
	if code, _, errs := run(r.env, "start", "--story", "ST-1"); code != exitUsage ||
		!strings.Contains(errs, "name the factory project with --project: the factory has 2 (bare, p1)") {
		t.Fatalf("two projects, none named: %d %q", code, errs)
	}
	r.fdb.Exec("DELETE FROM projects WHERE id='bare'")
	if code, _, errs := run(r.env, "start", "--story", "ST-1"); code != 0 || !strings.Contains(r.factory.calls[0], "--project p1") {
		t.Fatalf("the only project: %d %q %v", code, errs, r.factory.calls)
	}
}

func TestACancelledGoalClosesTheRunAndTheStoryCanStartAgain(t *testing.T) {
	r := newStartRig(t)
	if _, err := r.fdb.Exec("ALTER TABLE goals ADD COLUMN status TEXT"); err != nil {
		t.Fatal(err)
	}
	if code, _, errs := run(r.env, "start", "--story", "ST-1"); code != 0 {
		t.Fatalf("start: %d %q", code, errs)
	}
	if code, _, errs := run(r.env, "start", "--story", "ST-1"); code != exitUsage || !strings.Contains(errs, "already has run G-001") {
		t.Fatalf("second start while the run is open: %d %q", code, errs)
	}
	n := len(r.factory.calls)
	r.fdb.Exec("UPDATE goals SET status='cancelled' WHERE id='G-001'")
	for i := 0; i < 2; i++ { // the second tick finds the run closed and does nothing
		if code, _, errs := run(r.env, "tick"); code != 0 {
			t.Fatalf("tick: %d %q", code, errs)
		}
	}
	if _, out, _ := run(r.env, "status"); out != "G-001 ST-1 huge (chosen) cancelled\n" {
		t.Fatalf("status %q", out)
	}
	if len(r.factory.calls) != n {
		t.Fatalf("the tick still acted for a cancelled goal: %v", r.factory.calls[n:])
	}
	_, out, _ := run(r.env, "incidents", "--json")
	if strings.Count(out, `"cause": "goal-cancelled"`) != 1 {
		t.Fatalf("incidents %s", out)
	}
	// the story is free again: the start gets past the "already has run" check and reaches the factory (the fake
	// factory numbers every goal G-001, so recording this second run fails; that is the fake, not the engine)
	if _, _, errs := run(r.env, "start", "--story", "ST-1"); strings.Contains(errs, "already has run") || len(r.factory.calls) == n {
		t.Fatalf("start after the cancel: %q %v", errs, r.factory.calls[n:])
	}
}
