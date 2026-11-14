package workflow

import (
	"bytes"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"factory/go/internal/factorydb"
	"factory/go/internal/factorydb/dbtest"
	"factory/go/internal/identity"
)

var fixedNow = time.Date(2026, 11, 14, 12, 0, 0, 0, time.FixedZone("CET", 3600))

// testEnv is a home with a factory.db, and an Env whose caller is agent (empty: the owner).
func testEnv(t *testing.T, agent string) (identity.Env, string) {
	t.Helper()
	home := t.TempDir()
	dbtest.New(t, home, factorydb.SchemaVersion)
	vars := map[string]string{"FACTORY_HOME": home, "HOME": home}
	if agent != "" {
		vars["FACTORY_AGENT"] = agent
	}
	look := func(k string) (string, bool) { v, ok := vars[k]; return v, ok }
	return identity.Env{Getenv: func(k string) string { return vars[k] }, LookupEnv: look, Uid: os.Getuid(),
		Now: func() time.Time { return fixedNow }, Stderr: &bytes.Buffer{}}, home
}

func run(env identity.Env, args ...string) (int, string, string) {
	var out, errb bytes.Buffer
	code := Main(args, env, &out, &errb)
	return code, out.String(), errb.String()
}

func addRun(t *testing.T, home, goal, created string) {
	t.Helper()
	st, err := OpenState(StatePath(home))
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	if _, err := st.Exec(`INSERT INTO runs VALUES(?, 'DVDG-1', 'huge', NULL, ?, ?, ?)`, goal, string(RunNew), created, created); err != nil {
		t.Fatal(err)
	}
}

func TestStateCreateReopenAndVersion(t *testing.T) {
	home := t.TempDir()
	path := StatePath(home)
	st, err := OpenState(path)
	if err != nil {
		t.Fatal(err)
	}
	var v int
	st.QueryRow("PRAGMA user_version").Scan(&v)
	if v != UserVersion {
		t.Fatalf("user_version %d", v)
	}
	// the final first-version shape: run_stories exists and children carries story_key
	if _, err := st.Exec(`INSERT INTO run_stories VALUES('G-001', 'DVDG-1', 1)`); err != nil {
		t.Fatal(err)
	}
	if _, err := st.Exec(`INSERT INTO children(goal_id, story_key, child_key, position, state, updated)
		VALUES('G-001', 'DVDG-1', 'HM-1', 1, ?, 'now')`, string(ChildTodo)); err != nil {
		t.Fatal(err)
	}
	st.Close()
	if fi, _ := os.Stat(path); fi.Mode().Perm() != 0o600 {
		t.Fatalf("mode %v", fi.Mode().Perm())
	}
	st, err = OpenState(path) // reopened unchanged
	if err != nil {
		t.Fatal(err)
	}
	var n int
	st.QueryRow("SELECT count(*) FROM children WHERE story_key='DVDG-1'").Scan(&n)
	if n != 1 {
		t.Fatalf("children rows %d", n)
	}
	st.Exec("PRAGMA user_version = 7")
	st.Close()
	if _, err := OpenState(path); !errors.Is(err, ErrStateVersion) {
		t.Fatalf("version 7: want ErrStateVersion, got %v", err)
	}
	// an unversioned file that holds someone else's tables is refused, never initialised over
	other := filepath.Join(t.TempDir(), "workflow.db")
	d := dbtest.Raw(t, other)
	if _, err := d.Exec("CREATE TABLE x(a)"); err != nil {
		t.Fatal(err)
	}
	d.Close()
	if _, err := OpenState(other); !errors.Is(err, ErrStateVersion) {
		t.Fatalf("foreign file: want ErrStateVersion, got %v", err)
	}
}

func TestStatusFreshHomeAndFactoryDBUntouched(t *testing.T) {
	env, home := testEnv(t, "")
	fpath := factorydb.ResolvePath(home)
	before, _ := os.ReadFile(fpath)
	if code, out, errs := run(env, "status"); code != 0 || out != "no runs\n" {
		t.Fatalf("status: %d %q %q", code, out, errs)
	}
	if code, _, errs := run(env, "tick"); code != 0 {
		t.Fatalf("tick: %d %q", code, errs)
	}
	after, _ := os.ReadFile(fpath)
	if !bytes.Equal(before, after) {
		t.Fatal("factory.db changed")
	}
	addRun(t, home, "G-002", "2026-11-14T10:00:00+01:00")
	if code, out, _ := run(env, "status", "--goal", "G-002"); code != 0 || out != "G-002 DVDG-1 huge new\n" {
		t.Fatalf("status --goal: %d %q", code, out)
	}
}

func TestSecondTickExitsAtOnceWhileTheLockIsHeld(t *testing.T) {
	env, home := testEnv(t, "")
	addRun(t, home, "G-001", "2026-11-14T10:00:00+01:00")
	calls := 0
	defer func(old func(*Engine, Run) error) { advance = old }(advance)
	advance = func(*Engine, Run) error { calls++; return nil }
	unlock, held, err := lock(filepath.Join(home, "run", "workflow.lock"))
	if err != nil || held {
		t.Fatalf("first lock: %v %v", held, err)
	}
	if code, _, errs := run(env, "tick"); code != 0 || calls != 0 {
		t.Fatalf("locked tick: code %d calls %d %q", code, calls, errs)
	}
	unlock()
	if code, _, errs := run(env, "tick"); code != 0 || calls != 1 {
		t.Fatalf("free tick: code %d calls %d %q", code, calls, errs)
	}
}

func TestRecordWritesTheIncidentAndOneBareEvent(t *testing.T) {
	env, home := testEnv(t, "")
	e, closeAll, err := open(env, home)
	if err != nil {
		t.Fatal(err)
	}
	defer closeAll()
	id, err := e.Record(Incident{GoalID: "G-003", ChildKey: "HM-9", Kind: KindRejection, Cause: "review-changes",
		Actor: "reviewer-1", Round: 2, HeadSHA: "abc", Summary: "two findings", Detail: map[string]any{"findings": "secret text"}})
	if err != nil {
		t.Fatal(err)
	}
	rows, _ := e.Factory.Query("SELECT actor, entity, entity_id, action, detail FROM events")
	defer rows.Close()
	var got []string
	for rows.Next() {
		var a, en, eid, act, det string
		rows.Scan(&a, &en, &eid, &act, &det)
		got = append(got, strings.Join([]string{a, en, eid, act, det}, "|"))
	}
	want := "reviewer-1|workflow|G-003|rejection|cause=review-changes incident=" + itoa(id)
	if len(got) != 1 || got[0] != want {
		t.Fatalf("events %q, want [%q]", got, want)
	}
	var child, round, base any
	e.State.QueryRow("SELECT child_key, round, base_sha FROM incidents WHERE id=?", id).Scan(&child, &round, &base)
	if child != "HM-9" || round != int64(2) || base != nil {
		t.Fatalf("row: %v %v %v", child, round, base)
	}
}

func itoa(n int64) string { b, _ := json.Marshal(n); return string(b) }

func TestFailingAdvanceIsRecordedAndOthersStillRun(t *testing.T) {
	env, home := testEnv(t, "")
	addRun(t, home, "G-001", "2026-11-14T10:00:00+01:00")
	addRun(t, home, "G-002", "2026-11-14T10:01:00+01:00")
	addRun(t, home, "G-003", "2026-11-14T10:02:00+01:00")
	var seen []string
	defer func(old func(*Engine, Run) error) { advance = old }(advance)
	advance = func(_ *Engine, r Run) error {
		seen = append(seen, r.GoalID)
		switch r.GoalID {
		case "G-001":
			return errors.New("boom\nsecond line")
		case "G-002":
			panic("kaputt")
		}
		return nil
	}
	if code, _, errs := run(env, "tick"); code != 0 {
		t.Fatalf("tick: %d %q", code, errs)
	}
	if strings.Join(seen, ",") != "G-001,G-002,G-003" {
		t.Fatalf("advanced %v", seen)
	}
	code, out, errs := run(env, "incidents", "--json")
	if code != 0 {
		t.Fatalf("incidents: %d %q", code, errs)
	}
	var inc []struct {
		Goal, Kind, Cause, Summary string
		Detail                     map[string]any
	}
	if err := json.Unmarshal([]byte(out), &inc); err != nil {
		t.Fatal(err)
	}
	if len(inc) != 2 || inc[0].Goal != "G-002" || inc[1].Goal != "G-001" {
		t.Fatalf("incidents %+v", inc)
	}
	if inc[1].Kind != string(KindFailure) || inc[1].Cause != string(CauseEngineError) ||
		inc[1].Detail["error"] != "boom\nsecond line" || inc[1].Detail["run_state"] != string(RunNew) ||
		inc[1].Summary != "advance failed: boom" || inc[0].Detail["error"] != "panic: kaputt" {
		t.Fatalf("incident content %+v", inc)
	}
}

func TestIncidentsJSONKeepsDetailAndOnlyBossOrOwner(t *testing.T) {
	env, home := testEnv(t, "")
	e, closeAll, err := open(env, home)
	if err != nil {
		t.Fatal(err)
	}
	detail := map[string]any{"cmd": "go test", "exit": float64(1), "output": "FAIL x\n\"quoted\"", "nested": map[string]any{"a": []any{"b"}}}
	if _, err := e.Record(Incident{GoalID: "G-1", Kind: KindWarning, Cause: CauseEngineError, Actor: ActorEngine,
		Summary: "s", Detail: detail}); err != nil {
		t.Fatal(err)
	}
	e.Factory.Exec("INSERT INTO agents(name, role, status) VALUES('boss', 'boss', 'live'), ('coder-1', 'coder', 'live')")
	closeAll()

	code, out, _ := run(env, "incidents", "--json", "--kind", "warning")
	var inc []struct{ Detail map[string]any }
	json.Unmarshal([]byte(out), &inc)
	if code != 0 || len(inc) != 1 || mustJSON(inc[0].Detail) != mustJSON(detail) {
		t.Fatalf("owner: %d %q", code, out)
	}
	if code, out, _ := run(env, "incidents", "--kind", "rejection"); code != 0 || out != "no incidents\n" {
		t.Fatalf("filter: %d %q", code, out)
	}
	if code, _, _ := run(env, "incidents", "--kind", "nope"); code != 2 {
		t.Fatalf("bad kind: %d", code)
	}
	boss, bhome := env, home
	boss.Getenv = func(k string) string {
		return map[string]string{"FACTORY_HOME": bhome, "HOME": bhome, "FACTORY_AGENT": "boss"}[k]
	}
	boss.LookupEnv = func(k string) (string, bool) { v := boss.Getenv(k); return v, v != "" }
	if code, _, errs := run(boss, "incidents"); code != 0 {
		t.Fatalf("boss: %d %q", code, errs)
	}
	coder := boss
	coder.Getenv = func(k string) string {
		return map[string]string{"FACTORY_HOME": bhome, "HOME": bhome, "FACTORY_AGENT": "coder-1"}[k]
	}
	coder.LookupEnv = func(k string) (string, bool) { v := coder.Getenv(k); return v, v != "" }
	if code, _, errs := run(coder, "incidents"); code != 3 || !strings.Contains(errs, "allowed: boss") {
		t.Fatalf("coder: %d %q", code, errs)
	}
}

func mustJSON(v any) string { b, _ := json.Marshal(v); return string(b) }

func TestUsageErrors(t *testing.T) {
	env, _ := testEnv(t, "")
	for _, args := range [][]string{{}, {"nope"}, {"status", "extra"}, {"status", "--json"}} {
		if code, _, _ := run(env, args...); code != 2 {
			t.Errorf("%v: want 2, got %d", args, code)
		}
	}
	if code, out, _ := run(env, "version"); code != 0 || !strings.HasPrefix(out, Bin+" ") {
		t.Fatalf("version: %d %q", code, out)
	}
}
