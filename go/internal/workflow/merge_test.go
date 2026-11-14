package workflow

import (
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"

	"factory/go/internal/tsr"
)

// built is a run whose three children are all reviewed and whose builder has run `factory wf built`.
func built(t *testing.T) *startRig {
	t.Helper()
	r := started(t)
	st, _ := OpenState(StatePath(r.home))
	st.Exec("UPDATE children SET state='reviewed', base_sha='base0', head_sha='head1'")
	st.Exec("UPDATE runs SET state='built'")
	st.Close()
	seedCommits(r)
	return r
}

// seedCommits stores what the builder's in_review calls would have recorded for C-1..C-3 (C-2 had a fix round).
func seedCommits(r *startRig) {
	st, _ := OpenState(StatePath(r.home))
	defer st.Close()
	rows := []struct {
		child, sha, subject string
		round               int
	}{{"C-1", "c1sha", "feat: one (C-1)", 1}, {"C-2", "c2sha", "feat: two (C-2)", 1},
		{"C-3", "c3sha", "feat: three (C-3)", 1}, {"C-2", "c2fix", "fix: review of C-2", 2}}
	for i, c := range rows {
		st.Exec("INSERT INTO child_commits VALUES('G-001', ?, ?, ?, ?, ?)", c.child, c.sha, c.subject, c.round, i+1)
	}
}

func (r *startRig) merged(t *testing.T) {
	r.fdb.Exec("UPDATE tasks SET status='done', pr_url='https://example.com/pr/7' WHERE id='T-0001'")
	r.fdb.Exec("INSERT INTO events(ts, actor, entity, entity_id, action, detail) VALUES('x', 'tick', 'task', 'T-0001', 'merged', '@0abc1234 by=mech: green')")
}

func (r *startRig) state(t *testing.T) string {
	st, _ := OpenState(StatePath(r.home))
	defer st.Close()
	var s string
	st.QueryRow("SELECT state FROM runs").Scan(&s)
	return s
}

// bodyProblems applies the checks of bin/factory_cli.py pr_body_problems to a body.
func bodyProblems(body string) []string {
	var p []string
	outside := detailsRE.ReplaceAllString(regexp.MustCompile(`(?s)<!--.*?-->`).ReplaceAllString(body, ""), "")
	lines := strings.Split(outside, "\n")
	last := -1
	for _, h := range prHeadings {
		i := -1
		for j, l := range lines {
			if strings.TrimRight(l, " ") == h {
				i = j
				break
			}
		}
		if i < 0 || i < last {
			p = append(p, "heading "+h)
		}
		last = i
	}
	walk := false
	for _, blk := range detailsRE.FindAllString(body, -1) {
		ls := strings.Split(blk, "\n")
		for i, l := range ls {
			if strings.TrimRight(l, " ") == prAcceptanceWalk && i+1 < len(ls) && strings.TrimSpace(ls[i+1]) != "" &&
				!strings.HasPrefix(strings.TrimSpace(ls[i+1]), "</") {
				walk = true
			}
		}
	}
	if !walk {
		p = append(p, "acceptance walk")
	}
	if n := len(strings.Fields(outside)); n > prWordsMax {
		p = append(p, "words")
	}
	return p
}

func TestPRBodyFollowsTheFactoryRules(t *testing.T) {
	long := strings.Repeat("very long story title words ", 12)
	mk := func(n int) []storyInfo {
		var ss []storyInfo
		for i := 0; i < n; i++ {
			k := "ST-" + string(rune('1'+i))
			ss = append(ss, storyInfo{task: tsr.Task{Key: k, Title: long},
				kids: []childRow{{key: k + "a", base: "aaaa", head: "bbbb"}, {key: k + "b", base: "bbbb", head: "cccc", rounds: 2}}})
		}
		return ss
	}
	for _, n := range []int{1, 3} {
		body := prBody(Run{GoalID: "G-001", TaskID: "T-0001"}, mk(n), map[string]string{})
		if p := bodyProblems(body); len(p) > 0 {
			t.Fatalf("%d stories: %v\n%s", n, p, body)
		}
		if !strings.Contains(body, "1. ST-1: all 2 children reviewed by agent") {
			t.Fatalf("walk: %s", body)
		}
	}
	if got := prTitle("T-0001", mk(1)[:1]); strings.ContainsAny(got, "\"`$") || !strings.HasPrefix(got, "T-0001: ") {
		t.Fatalf("title %q", got)
	}
}

func TestBuiltRunAsksForThePROnceWhenEveryChildIsReviewed(t *testing.T) {
	r := built(t)
	st, _ := OpenState(StatePath(r.home))
	st.Exec("UPDATE children SET state='fixing' WHERE child_key='C-2'")
	st.Close()
	r.tick(t)
	if len(r.callsLike("msg builder-t-0001")) != 0 || r.state(t) != string(RunBuilt) {
		t.Fatalf("sent with a child fixing: %v", r.factory.calls)
	}
	st, _ = OpenState(StatePath(r.home))
	st.Exec("UPDATE children SET state='reviewed' WHERE child_key='C-2'")
	st.Close()
	r.tick(t)
	mails := r.callsLike("msg builder-t-0001")
	text := r.factory.stdins[len(r.factory.stdins)-1]
	if len(mails) != 1 || r.state(t) != string(RunMerging) || placeholderRE.MatchString(text) ||
		!strings.Contains(text, "factory task update T-0001 --status in_review") || !strings.Contains(text, "git merge origin/main") {
		t.Fatalf("open-PR mail %v %q", mails, text)
	}
	if p := bodyProblems(text[strings.Index(text, "## Summary") : strings.LastIndex(text, "</details>")+len("</details>")]); len(p) > 0 {
		t.Fatalf("body in the mail: %v", p)
	}
	r.tick(t)
	if len(r.callsLike("msg builder-t-0001")) != 1 {
		t.Fatal("second mail")
	}
}

func TestMergedRunLinksCommentsClosesAndTellsTheBoss(t *testing.T) {
	r := built(t)
	r.tick(t) // merging
	r.tick(t) // the gate has not merged: nothing
	if len(r.tracker.links)+len(r.tracker.statuses)+len(r.tracker.comments) != 0 {
		t.Fatal("finished before the merge")
	}
	r.merged(t)
	r.tick(t)
	if r.state(t) != string(RunDone) {
		t.Fatalf("state %s", r.state(t))
	}
	want := "id-C-1|c1sha id-C-2|c2sha id-C-2|c2fix id-C-3|c3sha id-ST-1|" + fakeMergeSHA + ""
	if got := strings.Join(r.tracker.links, " "); got != want {
		t.Fatalf("links %s\nwant  %s", got, want)
	}
	if len(r.tracker.comments) != 1 || !strings.HasPrefix(r.tracker.comments[0], "id-ST-1|Story run G-001 merged: pull request https://example.com/pr/7") ||
		!strings.Contains(r.tracker.comments[0], "- C-2: 0") {
		t.Fatalf("comment %v", r.tracker.comments)
	}
	if got := strings.Join(r.tracker.statuses, " "); got != "id-C-1|s-done id-C-2|s-done id-C-3|s-done id-ST-1|s-done" {
		t.Fatalf("statuses %s", got)
	}
	boss := r.callsLike("msg boss")
	if len(boss) != 1 || !strings.Contains(boss[0], "ST-1 merged and Done") || !strings.Contains(boss[0], "--kind report") {
		t.Fatalf("boss %v", boss)
	}
	if _, err := os.Stat(filepath.Join(r.home, "roles", "plugins", "goals", "G-001")); !os.IsNotExist(err) {
		t.Fatalf("goal plugin folder still there: %v", err)
	}
	n := len(r.factory.calls) + len(r.tracker.links) + len(r.tracker.comments) + len(r.tracker.statuses)
	r.tick(t)
	if len(r.factory.calls)+len(r.tracker.links)+len(r.tracker.comments)+len(r.tracker.statuses) != n {
		t.Fatal("a tick after done changed something")
	}
	for _, c := range r.factory.calls {
		if strings.HasPrefix(c, "verdict") || strings.HasPrefix(c, "pr ") || strings.HasPrefix(c, "judge") {
			t.Fatalf("the engine called %q", c)
		}
	}
}

func TestAFailedFinishStepResumesWithoutRepeating(t *testing.T) {
	for _, failOn := range []int{3, 7} { // 3: inside the links; 7: the first move to Done, after the comment (writes 6)
		r := built(t)
		r.tick(t)
		r.merged(t)
		r.tracker.failOn = failOn
		if code, _, errs := run(r.env, "tick"); code != 0 {
			t.Fatal(errs)
		}
		if failOn == 7 && (r.state(t) != string(RunClosing) || len(r.tracker.comments) != 1) {
			t.Fatalf("fail on 7: state %s comments %d", r.state(t), len(r.tracker.comments))
		}
		if failOn == 3 && (r.state(t) != string(RunLinking) || len(r.tracker.comments) != 0) {
			t.Fatalf("fail on 3: state %s", r.state(t))
		}
		_, inc, _ := run(r.env, "incidents", "--json")
		if strings.Count(inc, `"cause": "taskosaur-error"`) != 1 || !strings.Contains(inc, `"http_status": 500`) {
			t.Fatalf("incidents %s", inc)
		}
		run(r.env, "tick")
		run(r.env, "tick")
		if r.state(t) != string(RunDone) || len(r.tracker.comments) != 1 || len(r.callsLike("msg boss")) != 1 {
			t.Fatalf("fail on %d: state %s, comments %d, boss %v", failOn, r.state(t), len(r.tracker.comments), r.callsLike("msg boss"))
		}
	}
}

func TestAStaleMergingRunIsReportedOnce(t *testing.T) {
	r := built(t)
	r.tick(t)
	r.fdb.Exec("DELETE FROM agents")
	r.fdb.Exec("UPDATE tasks SET updated='2026-11-14T09:00:00+01:00'") // three hours before fixedNow
	r.tick(t)
	r.tick(t)
	if boss := r.callsLike("msg boss"); len(boss) != 1 || !strings.Contains(boss[0], "no pull request and nobody working") {
		t.Fatalf("boss %v", boss)
	}
}

func TestTheEngineNeverCallsGh(t *testing.T) {
	files, _ := filepath.Glob("*.go")
	for _, f := range files {
		if strings.HasSuffix(f, "_test.go") {
			continue
		}
		src, _ := os.ReadFile(f)
		if regexp.MustCompile(`exec\.Command\("gh"|"verdict"`).Match(src) {
			t.Fatalf("%s calls gh or writes a verdict", f)
		}
	}
}

func TestKeyMatchingIsWholeKey(t *testing.T) {
	for s, want := range map[string]bool{"feat: x (C-1)": true, "C-1: x": true, "chore: C-10 y": false, "fix c-1 typo": true, "XC-1": false} {
		if keyIn(s, "C-1") != want {
			t.Errorf("%q: want %v", s, want)
		}
	}
}
