package workflow

import (
	"reflect"
	"sort"
	"strings"
	"testing"
)

// batchRig is a start rig with a second prepared story ST-2 (children D-1, D-2) in the same project.
func batchRig(t *testing.T) *startRig {
	r := newStartRig(t)
	r.tracker.tasks["ST-2"] = enriched("ST-2")
	for _, k := range []string{"D-1", "D-2"} {
		r.tracker.tasks[k] = enriched(k)
		r.tracker.children["ST-2"] = append(r.tracker.children["ST-2"], k)
	}
	return r
}

func (r *startRig) childRows(t *testing.T) string {
	st, _ := OpenState(StatePath(r.home))
	defer st.Close()
	kids, _ := (&Engine{State: st}).children("G-001")
	var s []string
	for _, c := range kids {
		s = append(s, c.story+"/"+c.key)
	}
	return strings.Join(s, " ")
}

func TestBatchStartMakesOneRunWithChildrenInStoryOrder(t *testing.T) {
	r := batchRig(t)
	code, out, errs := run(r.env, "start", "--story", "ST-2", "--story", "ST-1")
	if code != 0 {
		t.Fatalf("start: %d %q", code, errs)
	}
	if len(r.callsLike("goal new")) != 1 || len(r.callsLike("task add")) != 1 || len(r.callsLike("spawn coder")) != 1 {
		t.Fatalf("calls %v", r.factory.calls)
	}
	if got := r.childRows(t); got != "ST-2/D-1 ST-2/D-2 ST-1/C-1 ST-1/C-2 ST-1/C-3" {
		t.Fatalf("children %s", got)
	}
	if !strings.Contains(r.factory.calls[0], "(ST-2, ST-1)") || !strings.Contains(r.factory.stdins[2], "in this order: ST-2, ST-1.") ||
		!strings.Contains(out, "5 children of ST-2, ST-1") {
		t.Fatalf("goal %q kickoff %q out %q", r.factory.calls[0], r.factory.stdins[2], out)
	}
	if _, st, _ := run(r.env, "status"); !strings.Contains(st, "  story ST-2: 0 of 2 children reviewed\n  story ST-1: 0 of 3") {
		t.Fatalf("status %q", st)
	}
}

func TestBatchRefusalsCreateNothingAndAreRecorded(t *testing.T) {
	r := batchRig(t)
	st2 := r.tracker.tasks["ST-2"]
	st2.E2ETests = ""
	r.tracker.tasks["ST-2"] = st2
	code, _, errs := run(r.env, "start", "--story", "ST-1", "--story", "ST-2")
	if code != exitUsage || !strings.Contains(errs, "ST-2: missing tests") || len(r.factory.calls) != 0 || r.runCount() != 0 {
		t.Fatalf("unprepared item: %d %q %v", code, errs, r.factory.calls)
	}
	if code, _, errs := run(r.env, "start", "--story", "ST-1", "--story", "st-1"); code != exitUsage || !strings.Contains(errs, "listed twice") {
		t.Fatalf("twice: %d %q", code, errs)
	}
	r.tracker.tasks["ST-2"] = enriched("ST-2")
	other := r.tracker.tasks["ST-2"]
	other.ProjectID = "other"
	r.tracker.tasks["ST-2"] = other
	if code, _, errs := run(r.env, "start", "--story", "ST-1", "--story", "ST-2"); code != exitUsage || !strings.Contains(errs, "another Taskosaur project") {
		t.Fatalf("project: %d %q", code, errs)
	}
	_, inc, _ := run(r.env, "incidents", "--json")
	if strings.Count(inc, `"cause": "start-refused"`) != 3 || !strings.Contains(inc, `"goal": "-"`) {
		t.Fatalf("incidents %s", inc)
	}
	r.tracker.tasks["ST-2"] = enriched("ST-2")
	if code, _, errs := run(r.env, "start", "--story", "ST-1"); code != 0 {
		t.Fatal(errs)
	}
	n := len(r.factory.calls)
	if code, _, errs := run(r.env, "start", "--story", "ST-2", "--story", "ST-1"); code != exitUsage ||
		!strings.Contains(errs, "story ST-1 already has run G-001 (state building)") || len(r.factory.calls) != n {
		t.Fatalf("in a run: %d %q", code, errs)
	}
}

func TestBatchOpensOnePRAfterTheLastChildAndClosesEveryStory(t *testing.T) {
	r := batchRig(t)
	if code, _, errs := run(r.env, "start", "--story", "ST-1", "--story", "ST-2"); code != 0 {
		t.Fatal(errs)
	}
	st, _ := OpenState(StatePath(r.home))
	st.Exec("UPDATE children SET state='reviewed', base_sha='base0', head_sha='head1'")
	st.Exec("UPDATE children SET state='reviewing' WHERE child_key='D-2'")
	st.Exec("UPDATE runs SET state='built'")
	st.Close()
	seedCommits(r)
	r.fdb.Exec("INSERT INTO agents(name, role, task_id, status) VALUES('review-d-2-r1', 'reviewer', 'T-0001', 'live')")
	r.tick(t)
	if len(r.callsLike("msg coder-t-0001")) != 0 {
		t.Fatal("PR mail while D-2 is in review")
	}
	run(r.as("review-d-2-r1"), "review", "D-2", "pass", "--notes", notesFile(t, "ok"))
	r.tick(t)
	if m := r.callsLike("msg coder-t-0001"); len(m) != 1 || !strings.Contains(r.factory.stdins[len(r.factory.stdins)-1], "Title: `T-0001: batch ST-1..ST-2 (2 stories)`") {
		t.Fatalf("PR mail %v", m)
	}
	r.tick(t)
	if len(r.callsLike("msg coder-t-0001")) != 1 {
		t.Fatal("second PR mail")
	}
	r.merged(t)
	// the second story's closing comment fails once: after the links and the first story's comment
	r.tracker.failOn = r.tracker.writes + batchLinkWrites + 2
	run(r.env, "tick")
	if _, inc, _ := run(r.env, "incidents", "--json"); !strings.Contains(inc, "finish step reporting failed") {
		t.Fatalf("no failure injected: %s", inc)
	}
	run(r.env, "tick")
	if r.state(t) != string(RunDone) {
		t.Fatalf("state %s", r.state(t))
	}
	var commented []string
	for _, c := range r.tracker.comments {
		if strings.HasPrefix(c, "id-ST-") {
			commented = append(commented, c[:len("id-ST-1")])
		}
	}
	if strings.Join(commented, " ") != "id-ST-1 id-ST-2" {
		t.Fatalf("story comments %v", commented)
	}
	var done []string
	for _, s := range r.tracker.statuses {
		done = append(done, strings.TrimSuffix(s, "|s-done"))
	}
	if strings.Join(done, " ") != "id-C-1 id-C-2 id-C-3 id-ST-1 id-D-1 id-D-2 id-ST-2" {
		t.Fatalf("Done %v", done)
	}
	if boss := r.callsLike("msg boss"); len(boss) != 1 || !strings.Contains(boss[0], "ST-1, ST-2 merged and Done") {
		t.Fatalf("boss %v", boss)
	}
}

// batchLinkWrites is how many LinkCommit writes the linking step makes for the batch fixture: the fake git log names
// C-1, C-2 twice and C-3 (no D child), and each of the two stories gets the merge commit.
const batchLinkWrites = 4 + 2

func TestTheEngineCannotEditATasksText(t *testing.T) {
	// the only Taskosaur writes the engine can make are status, comment, the agent mark and commit links
	var got []string
	tt := reflect.TypeOf((*Tracker)(nil)).Elem()
	for i := 0; i < tt.NumMethod(); i++ {
		got = append(got, tt.Method(i).Name)
	}
	sort.Strings(got)
	want := []string{"AgentCheck", "Children", "Comment", "LinkCommit", "SetStatus", "Statuses", "TaskByKey"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("Tracker methods %v, want %v", got, want)
	}
}
