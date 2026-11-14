package workflow

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"factory/go/internal/factorydb"
	"factory/go/internal/factorydb/dbtest"
	"factory/go/internal/identity"
	"factory/go/internal/tsr"
)

const tsrTestToken = "tsr_pat_WF-test-secret"

// tsrRig is a home with agents of every role, config files pointing at a stub Taskosaur, and the requests it got.
type tsrRig struct {
	home  string
	mu    sync.Mutex
	calls []string // "METHOD path body"
	big   bool     // the download answers MaxAttachmentBytes+1 bytes
}

func newTsrRig(t *testing.T) *tsrRig {
	t.Helper()
	r := &tsrRig{home: t.TempDir()}
	dbtest.New(t, r.home, factorydb.SchemaVersion)
	d := dbtest.Raw(t, factorydb.ResolvePath(r.home))
	// coder-1 builds run G-1 (factory task T-1, story ST-9 with the one child HM-1); reviewer-1 and qa-1 work on it too
	for _, a := range [][3]string{{"coder-1", roleCoder, "T-1"}, {"reviewer-1", roleReviewer, "T-1"}, {"qa-1", roleQA, "T-1"},
		{"boss", roleBoss, ""}, {"pm-1", "pm", ""}} {
		if _, err := d.Exec("INSERT INTO agents(name, role, task_id, status) VALUES(?, ?, NULLIF(?, ''), 'live')", a[0], a[1], a[2]); err != nil {
			t.Fatal(err)
		}
	}
	d.Close()
	st, err := OpenState(StatePath(r.home))
	if err != nil {
		t.Fatal(err)
	}
	for _, q := range []string{
		"INSERT INTO runs VALUES('G-1', 'ST-9', 'simple', 'T-1', 'building', 'x', 'x')",
		"INSERT INTO run_stories VALUES('G-1', 'ST-9', 1)",
		"INSERT INTO children(goal_id, story_key, child_key, position, state, updated) VALUES('G-1', 'ST-9', 'HM-1', 1, 'todo', 'x')",
	} {
		if _, err := st.Exec(q); err != nil {
			t.Fatal(err)
		}
	}
	st.Close()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, q *http.Request) {
		raw, _ := io.ReadAll(q.Body)
		r.mu.Lock()
		r.calls = append(r.calls, strings.TrimSpace(q.Method+" "+q.URL.Path+" "+string(raw)))
		r.mu.Unlock()
		if q.Header.Get("Authorization") != "Bearer "+tsrTestToken {
			w.WriteHeader(401)
			return
		}
		switch q.URL.Path {
		case "/api/tasks/key/HM-1":
			io.WriteString(w, `{"id":"t-1","slug":"HM-1","title":"Do it","type":"TASK","size":"S","complexity":2,
				"description":"## Acceptance criteria\n- [ ] works","e2eTests":"none","projectId":"p-1",
				"status":{"id":"s0","name":"To Do","category":"TODO"},"project":{"workspace":{"organization":{"id":"o-1"}}}}`)
		case "/api/tasks":
			io.WriteString(w, `{"data":[{"id":"c1","slug":"HM-2","title":"Child","status":{"name":"In Review"}}],"totalPages":1}`)
		case "/api/task-statuses/project":
			io.WriteString(w, `[{"id":"s-todo","name":"To Do","category":"TODO","position":1},
				{"id":"s-prog","name":"In Progress","category":"IN_PROGRESS","position":2},
				{"id":"s-rev","name":"In Review","category":"IN_PROGRESS","position":3,"userAction":"REVIEW"},
				{"id":"s-done","name":"Done","category":"DONE","position":4}]`)
		case "/api/task-attachments/task/t-1":
			io.WriteString(w, `[{"id":"a-1","fileName":"../../evil.png","fileSize":5,"mimeType":"image/png"}]`)
		case "/api/task-attachments/a-1":
			io.WriteString(w, `{"id":"a-1","taskId":"t-1","fileName":"../../evil.png"}`)
		case "/api/task-attachments/a-9": // belongs to a task outside the run
			io.WriteString(w, `{"id":"a-9","taskId":"t-other","fileName":"x.png"}`)
		case "/api/task-attachments/a-1/download":
			if r.big {
				w.Write(bytes.Repeat([]byte{'x'}, tsr.MaxAttachmentBytes+1))
				return
			}
			io.WriteString(w, "PNG!!")
		default:
			if strings.HasPrefix(q.URL.Path, "/api/task-attachments/task/") {
				io.WriteString(w, `[]`)
				return
			}
			io.WriteString(w, `{}`)
		}
	}))
	t.Cleanup(srv.Close)
	cfg := filepath.Join(r.home, ".config", "factory")
	os.MkdirAll(cfg, 0o700)
	os.WriteFile(filepath.Join(cfg, tsr.URLFile), []byte(srv.URL+"/api\n"), 0o600)
	os.WriteFile(filepath.Join(cfg, tsr.TokenFile), []byte(tsrTestToken+"\n"), 0o600)
	return r
}

func (r *tsrRig) env(agent string) identity.Env {
	vars := map[string]string{"FACTORY_HOME": r.home, "HOME": r.home}
	if agent != "" {
		vars["FACTORY_AGENT"] = agent
	}
	return identity.Env{Getenv: func(k string) string { return vars[k] },
		LookupEnv: func(k string) (string, bool) { v, ok := vars[k]; return v, ok },
		Uid:       os.Getuid(), Now: func() time.Time { return fixedNow }, Stderr: &bytes.Buffer{}}
}

func (r *tsrRig) run(t *testing.T, agent string, args ...string) (int, string, string) {
	t.Helper()
	code, out, errs := run(r.env(agent), append([]string{"tsr"}, args...)...)
	if strings.Contains(out+errs, tsrTestToken) {
		t.Fatalf("token leaked in output of %v", args)
	}
	return code, out, errs
}

func (r *tsrRig) writes() []string {
	var w []string
	for _, c := range r.calls {
		if !strings.HasPrefix(c, "GET ") {
			w = append(w, c)
		}
	}
	return w
}

// The in_review path of status (commits recorded first) is tested with the start rig in hm35_test.go.
func TestTsrStatusIsForTheRunsBuilderOnly(t *testing.T) {
	r := newTsrRig(t)
	cases := []struct{ who, key, want string }{
		{"reviewer-1", "HM-1", "allowed: coder"},
		{"coder-1", "HM-77", "HM-77 is not part of your story run"},
		{"", "HM-1", "tsr status is for the builder of a story run"}, // the owner
	}
	for _, c := range cases {
		code, _, errs := r.run(t, c.who, "status", c.key, "in_review")
		if code != exitRefuse || !strings.Contains(errs, c.want) {
			t.Fatalf("%q on %s: %d %q", c.who, c.key, code, errs)
		}
	}
	if len(r.calls) != 0 {
		t.Fatalf("a refused status reached Taskosaur: %v", r.calls)
	}
}

func TestTsrIsScopedToTheCallersRun(t *testing.T) {
	r := newTsrRig(t)
	f := filepath.Join(t.TempDir(), "c.md")
	os.WriteFile(f, []byte("note"), 0o600)
	for _, c := range [][]string{
		{"reviewer-1", "show", "HM-77"}, {"coder-1", "children", "HM-77"}, {"qa-1", "attachments", "HM-77"},
		{"coder-1", "comment", "HM-77", "--file", f}, {"pm-1", "show", "HM-1"},
	} {
		if code, _, errs := r.run(t, c[0], c[1:]...); code != exitRefuse {
			t.Fatalf("%v: %d %q", c, code, errs)
		}
	}
	wd, _ := os.Getwd()
	os.Chdir(t.TempDir())
	defer os.Chdir(wd)
	if code, _, errs := r.run(t, "coder-1", "attachment", "a-9", "--out", "x.png"); code != exitRefuse ||
		!strings.Contains(errs, "attachment a-9 is not part of your story run") {
		t.Fatalf("foreign attachment: %d %q", code, errs)
	}
	if len(r.writes()) != 0 {
		t.Fatalf("writes %v", r.writes())
	}
	for _, who := range []string{"boss", ""} { // the boss and the owner are not limited
		if code, _, errs := r.run(t, who, "show", "HM-77"); code != 0 {
			t.Fatalf("%q show HM-77: %d %q", who, code, errs)
		}
	}
	if code, _, errs := r.run(t, "reviewer-1", "show", "ST-9"); code != 0 { // the run's story is in scope
		t.Fatalf("story: %d %q", code, errs)
	}
}

func TestTsrShowChildrenAndComment(t *testing.T) {
	r := newTsrRig(t)
	code, out, errs := r.run(t, "qa-1", "show", "HM-1")
	if code != 0 || !strings.Contains(out, "HM-1 Do it") || !strings.Contains(out, "- [ ] works") ||
		!strings.Contains(out, "## E2E tests\n\nnone") || !strings.Contains(out, "a-1\t5\timage/png\t../../evil.png") {
		t.Fatalf("show: %d %q %q", code, out, errs)
	}
	if code, out, _ := r.run(t, "boss", "children", "HM-1"); code != 0 || out != "HM-2\tIn Review\tChild\n" {
		t.Fatalf("children: %d %q", code, out)
	}
	if code, _, _ := r.run(t, "pm-1", "show", "HM-1"); code != exitRefuse {
		t.Fatalf("pm show: %d", code)
	}
	if code, _, _ := r.run(t, "boss", "comment", "HM-1", "--file", "x"); code != exitRefuse {
		t.Fatalf("boss comment: %d", code)
	}
	f := filepath.Join(t.TempDir(), "c.md")
	os.WriteFile(f, []byte("found **two** issues\n"), 0o600)
	if code, _, errs := r.run(t, "reviewer-1", "comment", "HM-1", "--file", f); code != 0 {
		t.Fatalf("comment: %d %q", code, errs)
	}
	w := r.writes()
	var body map[string]string
	json.Unmarshal([]byte(strings.TrimPrefix(w[0], "POST /api/task-comments ")), &body)
	if len(w) != 1 || body["taskId"] != "t-1" || body["content"] != "factory agent reviewer-1:\n\nfound **two** issues\n" {
		t.Fatalf("comment write %v", w)
	}
}

func TestTsrAttachmentPathRules(t *testing.T) {
	r := newTsrRig(t)
	wd, _ := os.Getwd()
	work := t.TempDir()
	os.Chdir(work)
	defer os.Chdir(wd)

	if code, out, _ := r.run(t, "coder-1", "attachments", "HM-1"); code != 0 || out != "a-1\t5\timage/png\t../../evil.png\n" {
		t.Fatalf("attachments: %d %q", code, out)
	}
	code, out, errs := r.run(t, "coder-1", "attachment", "a-1", "--out", "shot.png")
	target := filepath.Join(work, "shot.png")
	if real, err := filepath.EvalSymlinks(work); err == nil {
		target = filepath.Join(real, "shot.png")
	}
	if code != 0 || strings.TrimSpace(out) != target {
		t.Fatalf("save: %d %q %q", code, out, errs)
	}
	if b, _ := os.ReadFile(target); string(b) != "PNG!!" {
		t.Fatalf("content %q", b)
	}
	if st, _ := os.Stat(target); st.Mode().Perm() != 0o600 {
		t.Fatalf("mode %v", st.Mode().Perm())
	}
	if _, err := os.Stat(filepath.Join(filepath.Dir(filepath.Dir(work)), "evil.png")); err == nil {
		t.Fatal("server file name used as a path")
	}
	if code, _, errs := r.run(t, "coder-1", "attachment", "a-1", "--out", "shot.png"); code != exitUsage || !strings.Contains(errs, "not overwritten") {
		t.Fatalf("overwrite: %d %q", code, errs)
	}
	outside := filepath.Join(t.TempDir(), "x.png")
	if code, _, errs := r.run(t, "coder-1", "attachment", "a-1", "--out", outside); code != exitUsage || !strings.Contains(errs, "must be inside") {
		t.Fatalf("outside: %d %q", code, errs)
	}
	if code, _, _ := r.run(t, "coder-1", "attachment", "a-1", "--out", "../escape.png"); code != exitUsage {
		t.Fatalf("dotdot: %d", code)
	}
	r.big = true
	if code, _, errs := r.run(t, "coder-1", "attachment", "a-1", "--out", "big.png"); code != exitErr || !strings.Contains(errs, "larger than") {
		t.Fatalf("big: %d %q", code, errs)
	}
	left, _ := os.ReadDir(work)
	if len(left) != 1 {
		t.Fatalf("partial files left: %v", names(left))
	}
}

func names(es []os.DirEntry) string {
	var n []string
	for _, e := range es {
		n = append(n, e.Name())
	}
	return fmt.Sprint(n)
}

func TestTsrRefusesAnUnsafeTokenFile(t *testing.T) {
	r := newTsrRig(t)
	os.Chmod(filepath.Join(r.home, ".config", "factory", tsr.TokenFile), 0o644)
	code, _, errs := r.run(t, "coder-1", "show", "HM-1")
	if code != exitErr || !strings.Contains(errs, tsr.TokenFile) || !strings.Contains(errs, "mode 0600") || len(r.calls) != 0 {
		t.Fatalf("0644: %d %q", code, errs)
	}
}
