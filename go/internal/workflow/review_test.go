package workflow

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"factory/go/internal/tsr"
)

// started is a rig with a running story run (children C-1..C-3, builder builder-t-0001).
func started(t *testing.T) *startRig {
	t.Helper()
	r := newStartRig(t)
	if code, _, errs := run(r.env, "start", "--story", "ST-1"); code != 0 {
		t.Fatal(errs)
	}
	return r
}

// setReview with on: the builder commits one more change naming key (sha "<key>-<n>"), pushes, and runs
// `factory wf tsr status KEY in_review`, which records the commit and moves the task. Without on: Taskosaur moved the
// task back to In Progress (what a FAILED review mark does).
func (r *startRig) setReview(key string, on bool) {
	if !on {
		t := r.tracker.tasks[key]
		t.Status = tsr.Status{Name: "In Progress", Category: tsr.CategoryInProgress}
		r.tracker.tasks[key] = t
		return
	}
	n := 1
	for _, c := range r.git.log {
		if keyIn(c.subject, key) {
			n++
		}
	}
	r.git.commit(fmt.Sprintf("%s-%d", key, n), fmt.Sprintf("feat: part %d (%s)", n, key))
	if code, _, errs := run(r.as(builder), "tsr", "status", key, "in_review"); code != 0 {
		r.t.Fatalf("builder in_review %s: %d %q", key, code, errs)
	}
}

// builder is the run's builder in the rig.
const builder = "builder-t-0001"

func (r *startRig) tick(t *testing.T) {
	t.Helper()
	if code, _, errs := run(r.env, "tick"); code != 0 {
		t.Fatalf("tick: %q", errs)
	}
	if _, out, _ := run(r.env, "incidents", "--kind", "failure"); out != "no incidents\n" {
		t.Fatalf("engine failure: %s", out)
	}
}

func (r *startRig) callsLike(prefix string) []string {
	var out []string
	for _, c := range r.factory.calls {
		if strings.HasPrefix(c, prefix) {
			out = append(out, c)
		}
	}
	return out
}

func (r *startRig) child(t *testing.T, key string) childRow {
	t.Helper()
	st, _ := OpenState(StatePath(r.home))
	defer st.Close()
	kids, _ := (&Engine{State: st}).children("G-001")
	for _, c := range kids {
		if c.key == key {
			return c
		}
	}
	t.Fatalf("no child %s", key)
	return childRow{}
}

func notesFile(t *testing.T, text string) string {
	p := filepath.Join(t.TempDir(), "notes.md")
	os.WriteFile(p, []byte(text), 0o600)
	return p
}

func TestOneReviewerStartsForTheFirstChildInReview(t *testing.T) {
	r := started(t)
	r.setReview("C-1", true)
	r.tick(t)
	spawns := r.callsLike("spawn reviewer")
	if len(spawns) != 1 || !strings.Contains(spawns[0], "--name review-c-1-r1 --prompt -") {
		t.Fatalf("spawns %v", spawns)
	}
	kick := r.factory.stdins[len(r.factory.stdins)-1]
	if placeholderRE.MatchString(kick) || !strings.Contains(kick, "C-1-1 feat: part 1 (C-1)") ||
		!strings.Contains(kick, "`C-1-1`") || !strings.Contains(kick, "`base0`") || !strings.Contains(kick, "round 1 of 5") {
		t.Fatalf("kickoff %q", kick)
	}
	if c := r.child(t, "C-1"); c.state != string(ChildReviewing) {
		t.Fatalf("C-1 %+v", c)
	}
	r.tick(t)
	if len(r.callsLike("spawn reviewer")) != 1 || len(r.callsLike("spawn coder")) != 1 {
		t.Fatalf("second tick started an agent: %v", r.factory.calls)
	}
	if _, out, _ := run(r.env, "status", "--goal", "G-001"); !strings.Contains(out, "  C-1 reviewing rounds=0\n  C-2 todo rounds=0") {
		t.Fatalf("status %q", out)
	}
}

func TestReviewPassSetsTheMark(t *testing.T) {
	r := started(t)
	r.setReview("C-1", true)
	r.tick(t)
	code, out, errs := run(r.as("review-c-1-r1"), "review", "C-1", "pass", "--notes", notesFile(t, "AC1 met: test x passes"))
	if code != 0 || out != "C-1: reviewed\n" {
		t.Fatalf("pass: %d %q %q", code, out, errs)
	}
	if len(r.tracker.checks) != 1 || r.tracker.checks[0] != "id-C-1|REVIEW|PASSED|review-c-1-r1|C-1-1" {
		t.Fatalf("checks %v", r.tracker.checks)
	}
	if !strings.Contains(r.tracker.comments[0], "round 1 of 5: pass") || !strings.Contains(r.tracker.comments[0], "AC1 met") {
		t.Fatalf("comment %q", r.tracker.comments[0])
	}
	if c := r.child(t, "C-1"); c.state != string(ChildReviewed) {
		t.Fatalf("C-1 %+v", c)
	}
	// twice for the same round: refused, nothing changes
	if code, _, _ := run(r.as("review-c-1-r1"), "review", "C-1", "changes", "--notes", notesFile(t, "x")); code != exitRefuse || len(r.tracker.checks) != 1 {
		t.Fatalf("second result: %d %v", code, r.tracker.checks)
	}
}

func TestChangesGoToTheBuilderAndANewRoundStarts(t *testing.T) {
	r := started(t)
	r.setReview("C-1", true)
	r.tick(t)
	code, _, errs := run(r.as("review-c-1-r1"), "review", "C-1", "changes", "--notes", notesFile(t, "1. cli.go:10 misses the error"))
	if code != 0 {
		t.Fatal(errs)
	}
	if r.tracker.checks[0] != "id-C-1|REVIEW|FAILED|review-c-1-r1|C-1-1" {
		t.Fatalf("checks %v", r.tracker.checks)
	}
	mails := r.callsLike("msg builder-t-0001")
	if len(mails) != 1 || !strings.Contains(mails[0], "--kind request") ||
		!strings.Contains(r.factory.stdins[len(r.factory.stdins)-1], "Review of `C-1`: changes requested (round 1 of 5)") {
		t.Fatalf("mail %v", mails)
	}
	if c := r.child(t, "C-1"); c.state != string(ChildFixing) || c.rounds != 1 {
		t.Fatalf("C-1 %+v", c)
	}
	r.setReview("C-1", false) // Taskosaur moved it back
	r.tick(t)
	if len(r.callsLike("spawn reviewer")) != 1 {
		t.Fatal("reviewer started while fixing")
	}
	r.setReview("C-1", true)
	r.tick(t)
	c := r.child(t, "C-1")
	if c.base != "base0" || c.head != "C-1-2" || c.state != string(ChildReviewing) {
		t.Fatalf("C-1 after fix %+v", c)
	}
	spawns := r.callsLike("spawn reviewer")
	kick := r.factory.stdins[len(r.factory.stdins)-1]
	if len(spawns) != 2 || !strings.Contains(spawns[1], "--name review-c-1-r2") ||
		!strings.Contains(kick, "Findings of round 1, to check first:\n\n1. cli.go:10 misses the error") ||
		!strings.Contains(kick, "C-1-2 feat: part 2 (C-1)") || strings.Contains(kick, "C-1-1 feat") {
		t.Fatalf("round 2: %v %q", spawns, kick)
	}
}

func TestTheFifthChangesStopsTheRunUntilResume(t *testing.T) {
	r := started(t)
	for round := 1; round <= MaxFixRounds; round++ {
		r.setReview("C-1", true)
		r.tick(t)
		name := "review-c-1-r" + string(rune('0'+round))
		if code, _, errs := run(r.as(name), "review", "C-1", "changes", "--notes", notesFile(t, "finding "+name)); code != 0 {
			t.Fatalf("round %d: %q", round, errs)
		}
		r.fdb.Exec("UPDATE agents SET status='done' WHERE name=?", name)
	}
	if _, out, _ := run(r.env, "status"); out != "G-001 ST-1 huge (chosen) blocked\n" {
		t.Fatalf("status %q", out)
	}
	boss := r.callsLike("msg boss")
	body := r.factory.stdins[len(r.factory.stdins)-1]
	if len(boss) != 1 || !strings.Contains(body, "finding review-c-1-r1") || !strings.Contains(body, "finding review-c-1-r5") {
		t.Fatalf("boss mail %v %q", boss, body)
	}
	if len(r.callsLike("msg builder-t-0001")) != 4 {
		t.Fatalf("builder mails %v", r.callsLike("msg builder-t-0001"))
	}
	n := len(r.factory.calls)
	r.setReview("C-1", true)
	r.tick(t)
	if len(r.factory.calls) != n {
		t.Fatalf("a blocked run started something: %v", r.factory.calls[n:])
	}
	if code, out, errs := run(r.env, "resume", "--goal", "G-001"); code != 0 || out != "run G-001: building again\n" {
		t.Fatalf("resume: %d %q %q", code, out, errs)
	}
	if c := r.child(t, "C-1"); c.state != string(ChildFixing) || c.rounds != 0 {
		t.Fatalf("C-1 after resume %+v", c)
	}
}

func TestReviewIsRefusedForTheWrongAgentOrChild(t *testing.T) {
	r := started(t)
	r.setReview("C-1", true)
	r.tick(t)
	f := notesFile(t, "x")
	for _, c := range []struct{ who, child string }{{"builder-t-0001", "C-1"}, {"review-c-1-r1", "C-2"}, {"owner", "C-1"}} {
		if code, _, errs := run(r.as(c.who), "review", c.child, "pass", "--notes", f); code != exitRefuse {
			t.Fatalf("%s on %s: %d %q", c.who, c.child, code, errs)
		}
	}
	if len(r.tracker.checks)+len(r.tracker.comments) != 0 || r.child(t, "C-1").state != string(ChildReviewing) {
		t.Fatal("a refused review changed something")
	}
}

func TestASilentReviewerIsRetriedOnceThenTheRunStops(t *testing.T) {
	r := started(t)
	r.setReview("C-1", true)
	r.tick(t)
	r.fdb.Exec("UPDATE agents SET status='lost' WHERE name='review-c-1-r1'")
	r.tick(t) // back to in_review and a new reviewer in the same tick
	if len(r.callsLike("spawn reviewer")) != 2 || r.child(t, "C-1").state != string(ChildReviewing) {
		t.Fatalf("retry: %v", r.factory.calls)
	}
	r.fdb.Exec("UPDATE agents SET status='exited' WHERE name='review-c-1-r1'")
	r.tick(t)
	if _, out, _ := run(r.env, "status"); out != "G-001 ST-1 huge (chosen) blocked\n" || len(r.callsLike("msg boss")) != 1 {
		t.Fatalf("status %q, boss %v", out, r.callsLike("msg boss"))
	}
}

func TestKeepModeResumesOneReviewerAndMailsTheNextChild(t *testing.T) {
	r := started(t)
	r.fdb.Exec("INSERT INTO config VALUES('workflow_reviewer_session', 'keep')")
	r.setReview("C-1", true)
	r.tick(t)
	if s := r.callsLike("spawn reviewer"); len(s) != 1 || !strings.Contains(s[0], "--name review-t-0001 --prompt -") {
		t.Fatalf("first review %v", s)
	}
	run(r.as("review-t-0001"), "review", "C-1", "pass", "--notes", notesFile(t, "ok"))
	r.fdb.Exec("UPDATE agents SET status='done' WHERE name='review-t-0001'")
	r.setReview("C-2", true)
	r.tick(t)
	s := r.callsLike("spawn reviewer")
	if len(s) != 2 || s[1] != "spawn reviewer --goal G-001 --task T-0001 --name review-t-0001 --resume sess-review-t-0001" {
		t.Fatalf("resume %v", s)
	}
	mails := r.callsLike("msg review-t-0001")
	if len(mails) != 1 || !strings.Contains(r.factory.stdins[len(r.factory.stdins)-1], "Child: `C-2`") {
		t.Fatalf("mail %v", mails)
	}
	if code, _, errs := run(r.as("review-t-0001"), "review", "C-2", "pass", "--notes", notesFile(t, "ok")); code != 0 {
		t.Fatalf("kept reviewer result: %q", errs)
	}
}

func TestKeepModeWithoutSessionFallsBackToFresh(t *testing.T) {
	r := started(t)
	r.fdb.Exec("INSERT INTO config VALUES('workflow_reviewer_session', 'keep')")
	r.fdb.Exec("INSERT INTO agents(name, role, task_id, status) VALUES('review-t-0001', 'reviewer', 'T-0001', 'done')")
	r.setReview("C-1", true)
	r.tick(t)
	if s := r.callsLike("spawn reviewer"); len(s) != 1 || !strings.Contains(s[0], "--name review-c-1-r1 --prompt -") {
		t.Fatalf("fallback %v", s)
	}
	_, out, _ := run(r.env, "incidents", "--kind", "warning")
	if !strings.Contains(out, "reviewer-resume-fallback") {
		t.Fatalf("incidents %q", out)
	}
}

func TestAnEndedBuilderIsResumedThreeTimesThenTheRunStops(t *testing.T) {
	r := started(t)
	for i := 1; i <= MaxBuilderResumes; i++ {
		r.fdb.Exec("UPDATE agents SET status='done' WHERE name='builder-t-0001'")
		r.tick(t)
		s := r.callsLike("spawn coder")
		if len(s) != i+1 || s[i] != "spawn coder --goal G-001 --task T-0001 --name builder-t-0001 --resume sess-builder-t-0001" {
			t.Fatalf("resume %d: %v", i, s)
		}
		body := r.factory.stdins[len(r.factory.stdins)-1]
		if !strings.Contains(body, "resume "+string(rune('0'+i))+" of 3") || !strings.Contains(body, "child C-1 is in work") {
			t.Fatalf("resume mail %q", body)
		}
		if _, out, _ := run(r.env, "status"); out != "G-001 ST-1 huge (chosen) building\n" {
			t.Fatalf("status %q", out)
		}
	}
	r.fdb.Exec("UPDATE agents SET status='done' WHERE name='builder-t-0001'")
	r.tick(t)
	if _, out, _ := run(r.env, "status"); out != "G-001 ST-1 huge (chosen) blocked\n" {
		t.Fatalf("status %q", out)
	}
	if _, out, _ := run(r.env, "incidents", "--kind", "escalation"); !strings.Contains(out, "builder-resume-limit") {
		t.Fatalf("incidents %q", out)
	}
	// only the owner's --fresh-builder starts a builder without --resume
	if code, _, errs := run(r.env, "resume", "--goal", "G-001", "--fresh-builder"); code != 0 {
		t.Fatal(errs)
	}
	s := r.callsLike("spawn coder")
	last := s[len(s)-1]
	kick := r.factory.stdins[len(r.factory.stdins)-1]
	if strings.Contains(last, "--resume") || !strings.Contains(last, "--prompt -") || !strings.Contains(kick, "Still to do, in order: C-1, C-2, C-3") {
		t.Fatalf("fresh builder %q %q", last, kick)
	}
	for _, c := range s[:len(s)-1] {
		if !strings.Contains(c, "--resume") && c != r.factory.calls[2] {
			t.Fatalf("a builder started without --resume: %q", c)
		}
	}
}
