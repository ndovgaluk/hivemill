package workflow

import (
	"strings"
	"testing"
)

// Tests of the review findings fixed in HM-35.

// lastKickoff is the kickoff of the newest reviewer spawn.
func (r *startRig) lastReviewKickoff(t *testing.T) string {
	t.Helper()
	for i := len(r.factory.calls) - 1; i >= 0; i-- {
		if strings.HasPrefix(r.factory.calls[i], "spawn reviewer") {
			return r.factory.stdins[i]
		}
	}
	t.Fatal("no reviewer spawned")
	return ""
}

func (r *startRig) review(t *testing.T, who, child string, pass bool) {
	t.Helper()
	verdict := reviewChanges
	if pass {
		verdict = reviewPass
	}
	if code, _, errs := run(r.as(who), "review", child, verdict, "--notes", notesFile(t, "notes of "+who)); code != 0 {
		t.Fatalf("%s review %s: %q", who, child, errs)
	}
	r.fdb.Exec("UPDATE agents SET status='done' WHERE name=?", who)
}

// Finding 1, case A: child 1 is set In Review, child 2 is built and pushed before the tick looks.
func TestCaseABuilderAheadOfTheTick(t *testing.T) {
	r := started(t)
	r.setReview("C-1", true)
	r.git.commit("C-2-1", "feat: part 1 (C-2)") // pushed in the same minute, not yet In Review
	r.tick(t)
	k1 := r.lastReviewKickoff(t)
	if !strings.Contains(k1, "C-1-1 feat: part 1 (C-1)") || strings.Contains(k1, "C-2-1") || strings.Contains(k1, "{") {
		t.Fatalf("C-1 kickoff %q", k1)
	}
	r.review(t, "review-c-1-r1", "C-1", true)
	r.setReview("C-2", true) // records C-2-1 and the C-2-2 it adds
	r.tick(t)
	k2 := r.lastReviewKickoff(t)
	if !strings.Contains(k2, "C-2-1 feat: part 1 (C-2)\nC-2-2 feat: part 2 (C-2)") || strings.Contains(k2, "C-1-1 feat") ||
		strings.Contains(k2, "{") {
		t.Fatalf("C-2 kickoff %q", k2)
	}
}

// Finding 1, case B: child 1 is rejected while the builder is on child 3; its fix comes after children 2 and 3.
func TestCaseBAFixAfterLaterChildren(t *testing.T) {
	r := started(t)
	r.setReview("C-1", true)
	r.tick(t)
	r.review(t, "review-c-1-r1", "C-1", false)
	r.setReview("C-1", false)
	r.setReview("C-2", true)
	r.setReview("C-3", true)
	r.tick(t) // the reviewer of C-2 starts
	r.setReview("C-1", true)
	r.review(t, "review-c-2-r1", "C-2", true)
	r.tick(t) // C-1 is first in list order again
	k := r.lastReviewKickoff(t)
	if !strings.Contains(k, "review round 2 of 5") || !strings.Contains(k, "C-1-2 feat: part 2 (C-1)") ||
		strings.Contains(k, "C-1-1 feat") || strings.Contains(k, "C-2-") || strings.Contains(k, "C-3-") || strings.Contains(k, "{") {
		t.Fatalf("round 2 kickoff %q", k)
	}
}

func TestBuilderInReviewRefusalsChangeNothing(t *testing.T) {
	r := started(t)
	try := func(who, key, want string, setup func()) {
		t.Helper()
		if setup != nil {
			setup()
		}
		code, _, errs := run(r.as(who), "tsr", "status", key, "in_review")
		if code == 0 || !strings.Contains(errs, want) {
			t.Fatalf("%s %s: %d %q, want %q", who, key, code, errs, want)
		}
		r.git.dirty, r.git.unpushed = false, false
	}
	try(builder, "C-1", "no commit names C-1", nil)
	r.git.commit("C-1-1", "feat: x (C-1)")
	try(builder, "C-1", "uncommitted changes", func() { r.git.dirty = true })
	try(builder, "C-1", "commit and push first", func() { r.git.unpushed = true })
	try(builder, "C-9", "C-9 is not part of your story run", nil)
	try(builder, "ST-1", "is a story of the run, not a child", nil)
	r.fdb.Exec("INSERT INTO agents(name, role, task_id, status) VALUES('coder-x', 'coder', 'T-0999', 'live')")
	try("coder-x", "C-1", "not part of your story run", nil)
	st, _ := OpenState(StatePath(r.home))
	defer st.Close()
	var n int
	st.QueryRow("SELECT count(*) FROM child_commits").Scan(&n)
	if n != 0 || len(r.tracker.statuses) != 0 {
		t.Fatalf("a refusal changed something: %d commits, statuses %v", n, r.tracker.statuses)
	}
}

// Finding 2: the worktree and the branch are gone after the merge; linking works from the stored commits.
func TestLinkingNeedsNoWorktree(t *testing.T) {
	r := built(t)
	r.tick(t)
	r.merged(t)
	r.fdb.Exec("UPDATE tasks SET worktree=NULL")
	r.fdb.Exec("UPDATE projects SET repo_path=NULL") // no repository either: the merge commit's prefix is linked
	n := len(r.git.calls)
	r.tick(t)
	if r.state(t) != string(RunDone) {
		t.Fatalf("state %s", r.state(t))
	}
	if got := strings.Join(r.tracker.links, " "); got != "id-C-1|c1sha id-C-2|c2sha id-C-2|c2fix id-C-3|c3sha id-ST-1|0abc1234" {
		t.Fatalf("links %s", got)
	}
	if len(r.git.calls) != n {
		t.Fatalf("git ran: %v", r.git.calls[n:])
	}
}

// Finding 4.
func TestTickIsForTheOwnerOnly(t *testing.T) {
	r := started(t)
	if code, _, errs := run(r.as(builder), "tick"); code != exitRefuse || !strings.Contains(errs, "for the owner") {
		t.Fatalf("builder tick: %d %q", code, errs)
	}
}

// Finding 5.
func TestASpawnRefusalIsRetried(t *testing.T) {
	r := started(t)
	r.fdb.Exec("UPDATE agents SET status='done' WHERE name=?", builder)
	r.factory.refuse = 4
	for i := 0; i < 5; i++ {
		r.tick(t)
	}
	if _, out, _ := run(r.env, "status"); !strings.HasPrefix(out, "G-001 ST-1 huge (chosen) building") {
		t.Fatalf("status %q", out)
	}
	if _, out, _ := run(r.env, "incidents", "--kind", "escalation"); out != "no incidents\n" {
		t.Fatalf("escalated: %s", out)
	}

	r2 := started(t)
	r2.fdb.Exec("UPDATE agents SET status='done' WHERE name=?", builder)
	r2.factory.refuse = 99
	for i := 0; i < 7; i++ {
		r2.tick(t)
	}
	_, out, _ := run(r2.env, "incidents", "--kind", "escalation")
	if strings.Count(out, "spawn-retry-limit") != 1 || r2.factory.mailsOK["boss"] != 1 {
		t.Fatalf("five refusals: %q, boss mails %d", out, r2.factory.mailsOK["boss"])
	}
}

// Finding 6: waking an ended builder to hand it new work does not use up the limit.
func TestDeliveriesOfNewWorkAreNotLimited(t *testing.T) {
	r := started(t)
	st, _ := OpenState(StatePath(r.home))
	st.Exec("UPDATE children SET state='reviewed' WHERE child_key IN ('C-2', 'C-3')")
	st.Exec("UPDATE children SET state='fixing', rounds=1 WHERE child_key='C-1'")
	st.Close()
	for i := 0; i < 10; i++ {
		r.fdb.Exec("UPDATE agents SET status='done' WHERE name=?", builder)
		st, _ := OpenState(StatePath(r.home)) // findings arrive while the builder is not running
		st.Exec(`INSERT INTO incidents(goal_id, child_key, kind, cause, actor, summary, detail, created)
			VALUES('G-001', 'C-1', 'rejection', 'review-changes', 'rev', 's', '{"builder_live":false}', 'x')`)
		st.Close()
		r.tick(t)
	}
	if _, out, _ := run(r.env, "status"); !strings.HasPrefix(out, "G-001 ST-1 huge (chosen) building") {
		t.Fatalf("status %q", out)
	}
	_, out, _ := run(r.env, "incidents", "--kind", "warning")
	if strings.Count(out, "builder-woken") != 10 || strings.Contains(out, "builder-resumed") {
		t.Fatalf("incidents %s", out)
	}
}

// Finding 7: a failure at each outside step of review() is completed later, each step once.
func TestReviewEffectsHappenOnceAfterAFailure(t *testing.T) {
	for _, point := range []string{"comment", "mark", "mail"} {
		r := started(t)
		r.setReview("C-1", true)
		r.tick(t)
		switch point {
		case "comment":
			r.tracker.failOn = r.tracker.writes + 1
		case "mark":
			r.tracker.failOn = r.tracker.writes + 2
		case "mail":
			r.factory.mailFail = 1
		}
		if code, _, errs := run(r.as("review-c-1-r1"), "review", "C-1", "changes", "--notes", notesFile(t, "1. bad")); code != 0 {
			t.Fatalf("%s: review %q", point, errs)
		}
		if _, out, _ := run(r.as("review-c-1-r1"), "review", "C-1", "changes", "--notes", notesFile(t, "again")); out != "" {
			t.Fatalf("%s: a second result was accepted: %q", point, out)
		}
		r.tick(t)
		r.tick(t)
		if len(r.tracker.comments) != 1 || len(r.tracker.checks) != 1 || r.factory.mailsOK[builder] != 1 {
			t.Fatalf("%s: comments %d, marks %d, builder mails %d", point, len(r.tracker.comments), len(r.tracker.checks),
				r.factory.mailsOK[builder])
		}
	}
}

// Finding 8.
func TestATaskClosedWithoutAMergeIsReportedOnce(t *testing.T) {
	r := built(t)
	r.tick(t) // merging
	r.fdb.Exec("UPDATE tasks SET status='done' WHERE id='T-0001'")
	r.tick(t)
	r.tick(t)
	_, out, _ := run(r.env, "incidents", "--kind", "escalation")
	if strings.Count(out, "closed-without-merge") != 1 || r.factory.mailsOK["boss"] != 1 || r.state(t) != string(RunMerging) {
		t.Fatalf("incidents %q, boss mails %d, state %s", out, r.factory.mailsOK["boss"], r.state(t))
	}
}
