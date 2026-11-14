package tsr

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
)

const testToken = "tsr_pat_SECRET-test-token-value"

type call struct {
	Method, Path, Query, Auth string
	Body                      map[string]any
}

// stub records every request and answers from the handler.
type stub struct {
	mu    sync.Mutex
	calls []call
	srv   *httptest.Server
}

func newStub(t *testing.T, h func(w http.ResponseWriter, r *http.Request)) (*stub, *Client) {
	s := &stub{}
	s.srv = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		raw, _ := io.ReadAll(r.Body)
		c := call{Method: r.Method, Path: r.URL.Path, Query: r.URL.RawQuery, Auth: r.Header.Get("Authorization")}
		if len(raw) > 0 {
			json.Unmarshal(raw, &c.Body)
		}
		s.mu.Lock()
		s.calls = append(s.calls, c)
		s.mu.Unlock()
		h(w, r)
	}))
	t.Cleanup(s.srv.Close)
	c := New(s.srv.URL+"/api/", testToken)
	c.pause = 0
	return s, c
}

func ok(body string) func(http.ResponseWriter, *http.Request) {
	return func(w http.ResponseWriter, _ *http.Request) { io.WriteString(w, body) }
}

func TestMethodsSendTheExactRequests(t *testing.T) {
	task := `{"id":"t-1","slug":"HM-1","title":"T","type":"TASK","size":"M","complexity":3,"description":"d",
		"e2eTests":"e","projectId":"p-1","parentTaskId":null,"status":{"id":"s","name":"To Do","category":"TODO"},
		"project":{"workspace":{"organization":{"id":"o-1"}}}}`
	s, c := newStub(t, func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/api/tasks/key/HM-1":
			io.WriteString(w, task)
		case r.URL.Path == "/api/tasks" && r.Method == http.MethodGet:
			if r.URL.Query().Get("page") == "1" {
				io.WriteString(w, `{"data":[{"id":"c1","slug":"HM-2"}],"totalPages":2}`)
			} else {
				io.WriteString(w, `{"data":[{"id":"c2","slug":"HM-3"}],"totalPages":2}`)
			}
		case r.URL.Path == "/api/task-statuses/project":
			io.WriteString(w, `[{"id":"s1","name":"In Review","category":"IN_PROGRESS","position":3,"userAction":"REVIEW"}]`)
		case r.URL.Path == "/api/task-attachments/task/t-1":
			io.WriteString(w, `[{"id":"a1","fileName":"x.png","fileSize":3,"mimeType":"image/png"}]`)
		default:
			io.WriteString(w, `{}`)
		}
	})
	tk, err := c.TaskByKey("HM-1")
	if err != nil || tk.ID != "t-1" || tk.OrganizationID() != "o-1" || tk.Complexity != 3 || tk.E2ETests != "e" {
		t.Fatalf("TaskByKey: %+v %v", tk, err)
	}
	kids, err := c.Children(tk)
	if err != nil || len(kids) != 2 || kids[1].Key != "HM-3" {
		t.Fatalf("Children: %+v %v", kids, err)
	}
	sts, err := c.Statuses("p-1")
	if err != nil || len(sts) != 1 || *sts[0].UserAction != UserActionReview {
		t.Fatalf("Statuses: %+v %v", sts, err)
	}
	atts, err := c.Attachments("t-1")
	if err != nil || atts[0].FileName != "x.png" || atts[0].FileSize != 3 {
		t.Fatalf("Attachments: %+v %v", atts, err)
	}
	passed := ResultPassed
	for _, err := range []error{c.SetStatus("t-1", "s1"), c.Comment("t-1", "**hi**"),
		c.AgentCheck("t-1", CheckReview, &passed, "reviewer-1", "abc123"), c.AgentCheck("t-1", CheckQA, nil, "", ""),
		c.LinkCommit([]string{"t-1", "t-2"}, "abcdef1", "subj")} {
		if err != nil {
			t.Fatal(err)
		}
	}
	want := []struct {
		method, path, query string
		body                map[string]any
	}{
		{"GET", "/api/tasks/key/HM-1", "", nil},
		{"GET", "/api/tasks", "includeDone=true&limit=100&organizationId=o-1&page=1&parentTaskId=t-1&sortBy=listRank&sortOrder=asc", nil},
		{"GET", "/api/tasks", "includeDone=true&limit=100&organizationId=o-1&page=2&parentTaskId=t-1&sortBy=listRank&sortOrder=asc", nil},
		{"GET", "/api/task-statuses/project", "projectId=p-1", nil},
		{"GET", "/api/task-attachments/task/t-1", "", nil},
		{"PATCH", "/api/tasks/t-1/status", "", map[string]any{"statusId": "s1"}},
		{"POST", "/api/task-comments", "", map[string]any{"taskId": "t-1", "content": "**hi**"}},
		{"PATCH", "/api/tasks/t-1/agent-check", "", map[string]any{"kind": "REVIEW", "result": "PASSED", "agentName": "reviewer-1", "ref": "abc123"}},
		{"PATCH", "/api/tasks/t-1/agent-check", "", map[string]any{"kind": "QA", "result": nil}},
		{"POST", "/api/task-commits", "", map[string]any{"taskId": "t-1", "sha": "abcdef1", "message": "subj"}},
		{"POST", "/api/task-commits", "", map[string]any{"taskId": "t-2", "sha": "abcdef1", "message": "subj"}},
	}
	if len(s.calls) != len(want) {
		t.Fatalf("calls: %+v", s.calls)
	}
	for i, w := range want {
		g := s.calls[i]
		gb, _ := json.Marshal(g.Body)
		wb, _ := json.Marshal(w.body)
		if g.Method != w.method || g.Path != w.path || g.Query != w.query || string(gb) != string(wb) ||
			g.Auth != "Bearer "+testToken {
			t.Errorf("call %d: got %s %s ?%s %s auth-ok=%v; want %s %s ?%s %s", i, g.Method, g.Path, g.Query, gb,
				g.Auth == "Bearer "+testToken, w.method, w.path, w.query, wb)
		}
	}
}

func TestErrorsRetriesAndRedirects(t *testing.T) {
	s, c := newStub(t, func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/api/tasks/key/BAD":
			w.WriteHeader(400)
			io.WriteString(w, `{"message":["statusId must be a UUID","x"],"error":"Bad Request","statusCode":400}`)
		case "/api/tasks/key/GONE":
			w.WriteHeader(404)
			io.WriteString(w, `{"message":"Task GONE not found","statusCode":404}`)
		case "/api/tasks/key/DOWN":
			w.WriteHeader(503)
		case "/api/tasks/key/MOVED":
			http.Redirect(w, r, "/elsewhere", http.StatusFound)
		}
	})
	_, err := c.TaskByKey("BAD")
	var te *Error
	if !errors.As(err, &te) || te.Status != 400 || te.Message != "statusId must be a UUID; x" {
		t.Fatalf("400: %v", err)
	}
	if _, err = c.TaskByKey("GONE"); !errors.As(err, &te) || te.Status != 404 || !strings.Contains(err.Error(), "Task GONE not found") {
		t.Fatalf("404: %v", err)
	}
	n := len(s.calls)
	if _, err = c.TaskByKey("DOWN"); !errors.As(err, &te) || te.Status != 503 || len(s.calls)-n != MaxTries {
		t.Fatalf("503: %v after %d tries", err, len(s.calls)-n)
	}
	n = len(s.calls)
	if _, err = c.TaskByKey("MOVED"); !errors.As(err, &te) || te.Status != 302 || len(s.calls)-n != 1 {
		t.Fatalf("redirect: %v, %d calls", err, len(s.calls)-n)
	}
	for _, p := range s.calls {
		if p.Path == "/elsewhere" {
			t.Fatal("redirect followed")
		}
	}
	// a 4xx is not retried
	n = len(s.calls)
	c.TaskByKey("BAD")
	if len(s.calls)-n != 1 {
		t.Fatalf("4xx retried: %d", len(s.calls)-n)
	}
	// a network error is named without the token
	l, err := net.Listen("tcp", "127.0.0.1:0") // a port that was just closed refuses at once
	if err != nil {
		t.Fatal(err)
	}
	l.Close()
	c2 := New("http://"+l.Addr().String()+"/api", testToken)
	c2.pause = 0
	_, err = c2.TaskByKey("X")
	if !errors.As(err, &te) || te.Status != 0 || !strings.Contains(err.Error(), "refused") || strings.Contains(err.Error(), testToken) {
		t.Fatalf("network: %v", err)
	}
}

func TestDownloadLimit(t *testing.T) {
	_, c := newStub(t, func(w http.ResponseWriter, r *http.Request) {
		size := 10
		if strings.Contains(r.URL.Path, "big") {
			size = MaxAttachmentBytes + 1
		}
		w.Write(bytes.Repeat([]byte{'x'}, size))
	})
	var b bytes.Buffer
	if n, err := c.Download("small", &b); err != nil || n != 10 || b.Len() != 10 {
		t.Fatalf("small: %d %v", n, err)
	}
	if _, err := c.Download("big", io.Discard); !errors.Is(err, ErrTooLarge) {
		t.Fatalf("big: %v", err)
	}
}

func writeCfg(t *testing.T, dir, name, content string, mode os.FileMode) {
	t.Helper()
	p := filepath.Join(dir, name)
	os.Remove(p)
	if err := os.WriteFile(p, []byte(content), mode); err != nil {
		t.Fatal(err)
	}
	os.Chmod(p, mode)
}

func TestLoadRefusesUnsafeFilesWithoutShowingThem(t *testing.T) {
	dir := t.TempDir()
	writeCfg(t, dir, URLFile, "http://127.0.0.1:9/api\n", 0o600)
	writeCfg(t, dir, TokenFile, testToken+"\n", 0o600)
	if c, err := Load(dir); err != nil || c.token != testToken || c.base != "http://127.0.0.1:9/api" {
		t.Fatalf("good files: %v", err)
	}
	cases := map[string]func(){
		"mode 0644": func() { writeCfg(t, dir, TokenFile, testToken, 0o644) },
		"empty":     func() { writeCfg(t, dir, TokenFile, "", 0o600) },
		"symlink": func() {
			real := filepath.Join(dir, "real")
			writeCfg(t, dir, "real", testToken, 0o600)
			os.Remove(filepath.Join(dir, TokenFile))
			if err := os.Symlink(real, filepath.Join(dir, TokenFile)); err != nil {
				t.Fatal(err)
			}
		},
		"missing": func() { os.Remove(filepath.Join(dir, TokenFile)) },
	}
	for name, setup := range cases {
		setup()
		_, err := Load(dir)
		if err == nil || !strings.Contains(err.Error(), filepath.Join(dir, TokenFile)) ||
			!strings.Contains(err.Error(), "mode 0600") || strings.Contains(err.Error(), testToken) {
			t.Errorf("%s: %v", name, err)
		}
	}
	writeCfg(t, dir, TokenFile, testToken, 0o600)
	writeCfg(t, dir, URLFile, "ftp://x", 0o600)
	if _, err := Load(dir); err == nil || !strings.Contains(err.Error(), URLFile) {
		t.Errorf("bad url: %v", err)
	}
}
