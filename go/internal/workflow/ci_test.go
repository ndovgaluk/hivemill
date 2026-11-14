package workflow

import (
	"database/sql"
	"path/filepath"
	"strings"
	"testing"
)

// storedCI is runs.ci of the rig's one run.
func storedCI(t *testing.T, r *startRig) string {
	t.Helper()
	st, err := OpenState(StatePath(r.home))
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	var s string
	if err := st.QueryRow("SELECT ci FROM runs").Scan(&s); err != nil {
		t.Fatal(err)
	}
	return s
}

func TestStartStoresTheCIModeOfTheFlagAndShowsIt(t *testing.T) {
	r := newStartRig(t)
	r.fdb.Exec("INSERT INTO config VALUES(?, ?)", cfgCI, CIGithub) // the flag wins over the config
	if code, out, errs := run(r.env, "start", "--story", "ST-1", "--ci", CILocal); code != 0 {
		t.Fatalf("start: %d %q %q", code, out, errs)
	}
	if got := storedCI(t, r); got != CILocal {
		t.Fatalf("stored %q", got)
	}
	if _, out, _ := run(r.env, "status"); !strings.HasSuffix(out, " building ci="+CILocal+"\n") {
		t.Fatalf("status %q", out)
	}
	var n int
	r.fdb.QueryRow("SELECT count(*) FROM events WHERE entity_id='G-001' AND action=? AND detail=?", eventCIMode, CILocal).Scan(&n)
	if n != 1 {
		t.Fatalf("%d %s events", n, eventCIMode)
	}
}

func TestStartTakesTheConfigDefaultAndTheRunKeepsIt(t *testing.T) {
	r := newStartRig(t)
	r.fdb.Exec("INSERT INTO config VALUES(?, ?)", cfgCI, CILocal)
	if code, out, errs := run(r.env, "start", "--story", "ST-1"); code != 0 {
		t.Fatalf("start: %d %q %q", code, out, errs)
	}
	r.fdb.Exec("UPDATE config SET value=? WHERE key=?", CIGithub, cfgCI) // the owner changes the default mid-run
	if got := storedCI(t, r); got != CILocal {
		t.Fatalf("stored %q after the config changed", got)
	}
}

func TestWithoutFlagOrConfigTheRunIsGithub(t *testing.T) {
	for _, cfg := range []string{"", "bogus"} { // a missing or unknown config value never skips GitHub's checks
		r := newStartRig(t)
		if cfg != "" {
			r.fdb.Exec("INSERT INTO config VALUES(?, ?)", cfgCI, cfg)
		}
		if code, out, errs := run(r.env, "start", "--story", "ST-1"); code != 0 {
			t.Fatalf("config %q start: %d %q %q", cfg, code, out, errs)
		}
		if got := storedCI(t, r); got != CIGithub {
			t.Fatalf("config %q stored %q", cfg, got)
		}
	}
}

func TestAnUnknownCIFlagIsAUsageErrorAndStartsNothing(t *testing.T) {
	r := newStartRig(t)
	code, _, errs := run(r.env, "start", "--story", "ST-1", "--ci", "circleci")
	if code != exitUsage || !strings.Contains(errs, "--ci must be one of") {
		t.Fatalf("code %d %q", code, errs)
	}
	if len(r.factory.calls) != 0 {
		t.Fatalf("factory called: %v", r.factory.calls)
	}
}

func TestAVersion1StateIsMigratedAndItsRunsAreGithub(t *testing.T) {
	path := filepath.Join(t.TempDir(), "db", "workflow.db")
	if _, err := OpenState(path); err != nil { // make the directory and a current file, then rebuild it as version 1
		t.Fatal(err)
	}
	d, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatal(err)
	}
	for _, q := range []string{"DROP TABLE runs",
		`CREATE TABLE runs(goal_id TEXT PRIMARY KEY, story_key TEXT NOT NULL, workflow TEXT NOT NULL, task_id TEXT,
		  state TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL)`,
		"INSERT INTO runs VALUES('G-1', 'ST-1', 'huge', 'T-1', 'building', 'x', 'x')",
		"PRAGMA user_version = 1"} {
		if _, err := d.Exec(q); err != nil {
			t.Fatalf("%s: %v", q, err)
		}
	}
	d.Close()
	st, err := OpenState(path)
	if err != nil {
		t.Fatalf("open v1: %v", err)
	}
	defer st.Close()
	var v int
	var ci string
	st.QueryRow("PRAGMA user_version").Scan(&v)
	st.QueryRow("SELECT ci FROM runs WHERE goal_id='G-1'").Scan(&ci)
	if v != UserVersion || ci != CIGithub {
		t.Fatalf("version %d ci %q", v, ci)
	}
}

func TestALocalRunStopsForTheOwnerInsteadOfOpeningAPullRequest(t *testing.T) {
	r := built(t)
	st, _ := OpenState(StatePath(r.home))
	st.Exec("UPDATE runs SET ci=?", CILocal)
	st.Close()
	r.tick(t)
	r.tick(t) // a second tick must not stop it, mail or record again
	if len(r.callsLike("msg coder-t-0001")) != 0 {
		t.Fatalf("builder asked for a pull request: %v", r.factory.calls)
	}
	if r.state(t) != string(RunBlocked) || len(r.callsLike("msg boss")) != 1 {
		t.Fatalf("state %s, boss mails %v", r.state(t), r.callsLike("msg boss"))
	}
	st, _ = OpenState(StatePath(r.home))
	defer st.Close()
	var n int
	st.QueryRow("SELECT count(*) FROM incidents WHERE cause=? AND kind=?", string(CauseCILocalNotBuilt), string(KindEscalation)).Scan(&n)
	if n != 1 {
		t.Fatalf("%d escalations", n)
	}
}
