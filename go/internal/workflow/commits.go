package workflow

import (
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	"factory/go/internal/tsr"
)

// A child's commits are recorded when the builder says the child is In Review (`factory wf tsr status CHILD in_review`
// in its worktree), not when the tick notices it: by then the builder may have pushed the next child (HM-35 finding 1).

// errNotReady is a refusal of the builder's in_review: nothing was stored or moved.
type errNotReady struct{ msg string }

func (e errNotReady) Error() string { return e.msg }

// storedCommit is one row of child_commits.
type storedCommit struct {
	sha, subject string
	round        int
}

// recordInReview checks the builder's worktree and stores the child's new commits for its current round. It is safe to
// run again after a failure later on (moving the task): commits already stored for this round count.
func (e *Engine) recordInReview(r Run, child childRow) error {
	wt, branch, base, err := e.taskCheckout(r.TaskID)
	if err != nil {
		return err
	}
	g := e.Deps.Git
	if dirty, err := g.Run(wt, "status", "--porcelain", "--untracked-files=no"); err != nil {
		return err
	} else if strings.TrimSpace(dirty) != "" {
		return errNotReady{"the worktree has uncommitted changes: commit and push first"}
	}
	if _, err := g.Run(wt, "fetch", "-q", "origin", "+refs/heads/"+branch+":refs/remotes/origin/"+branch,
		"+refs/heads/"+base+":refs/remotes/origin/"+base); err != nil {
		return err
	}
	head, err := g.Run(wt, "rev-parse", "HEAD")
	if err != nil {
		return err
	}
	if remote, err := g.Run(wt, "rev-parse", "refs/remotes/origin/"+branch); err != nil || remote != head {
		return errNotReady{fmt.Sprintf("HEAD is not origin/%s: commit and push first", branch)}
	}
	start, err := g.Run(wt, "merge-base", "refs/remotes/origin/"+base, "HEAD")
	if err != nil {
		return err
	}
	out, err := g.Run(wt, "log", "--reverse", "--format=%H%x1f%s", start+"..HEAD")
	if err != nil {
		return err
	}
	round := child.rounds + 1
	known, err := e.commitsOf(r.GoalID, child.key, 0)
	if err != nil {
		return err
	}
	seen := map[string]bool{}
	for _, c := range known {
		seen[c.sha] = true
	}
	var fresh []commit
	for _, l := range strings.Split(out, "\n") {
		p := strings.SplitN(l, "\x1f", 2)
		if len(p) == 2 && keyIn(p[1], child.key) && !seen[p[0]] {
			fresh = append(fresh, commit{sha: p[0], subject: p[1]})
		}
	}
	thisRound, err := e.commitsOf(r.GoalID, child.key, round)
	if err != nil {
		return err
	}
	if len(fresh) == 0 && len(thisRound) == 0 {
		return errNotReady{fmt.Sprintf("no commit names %s: put the key in each of its commit subjects", child.key)}
	}
	from := child.base // read before the transaction: workflow.db has one connection, which the transaction holds
	if from == "" {
		from = e.previousHead(r.GoalID, child.key, start)
	}
	tx, err := e.State.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()
	var pos int
	tx.QueryRow("SELECT COALESCE(max(position), 0) FROM child_commits WHERE goal_id=?", r.GoalID).Scan(&pos)
	for _, c := range fresh {
		pos++
		if _, err := tx.Exec("INSERT INTO child_commits VALUES(?,?,?,?,?,?)", r.GoalID, child.key, c.sha, c.subject,
			round, pos); err != nil {
			return err
		}
	}
	if _, err := tx.Exec("UPDATE children SET base_sha=?, head_sha=?, updated=? WHERE goal_id=? AND child_key=?",
		from, head, e.Env.Now().Format(tsLayout), r.GoalID, child.key); err != nil {
		return err
	}
	return tx.Commit()
}

// previousHead is the head of the child before this one in run order, or start for the first.
func (e *Engine) previousHead(goal, child, start string) string {
	var head string
	err := e.State.QueryRow(`SELECT COALESCE(head_sha, '') FROM children WHERE goal_id=?1 AND position <
		(SELECT position FROM children WHERE goal_id=?1 AND child_key=?2) ORDER BY position DESC LIMIT 1`, goal, child).Scan(&head)
	if err != nil || head == "" {
		return start
	}
	return head
}

// commitsOf lists a child's stored commits in order; round 0 means all rounds.
func (e *Engine) commitsOf(goal, child string, round int) ([]storedCommit, error) {
	rows, err := e.State.Query(`SELECT sha, subject, round FROM child_commits WHERE goal_id=? AND child_key=?
		AND (?3 = 0 OR round = ?3) ORDER BY position`, goal, child, round)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []storedCommit
	for rows.Next() {
		var c storedCommit
		if err := rows.Scan(&c.sha, &c.subject, &c.round); err != nil {
			return nil, err
		}
		out = append(out, c)
	}
	return out, rows.Err()
}

// commitsText is the {commits} of the reviewer texts: one line per commit, "<full hash> <subject>", oldest first;
// round 1 shows all of the child's commits, later rounds only that round's.
func (e *Engine) commitsText(goal, child string, round int) (string, error) {
	cs, err := e.commitsOf(goal, child, round)
	if err != nil {
		return "", err
	}
	var lines []string
	for _, c := range cs {
		lines = append(lines, c.sha+" "+c.subject)
	}
	return strings.Join(lines, "\n"), nil
}

// counter reads and changes a per-run counter (spawn refusals, ...); add 0 reads, reset sets 0.
func (e *Engine) counter(goal, name string, add int, reset bool) (int, error) {
	if reset {
		_, err := e.State.Exec("DELETE FROM counters WHERE goal_id=? AND name=?", goal, name)
		return 0, err
	}
	if add != 0 {
		if _, err := e.State.Exec(`INSERT INTO counters VALUES(?,?,?) ON CONFLICT(goal_id, name) DO UPDATE SET
			value = value + excluded.value`, goal, name, add); err != nil {
			return 0, err
		}
	}
	var v int
	err := e.State.QueryRow("SELECT value FROM counters WHERE goal_id=? AND name=?", goal, name).Scan(&v)
	if errors.Is(err, sql.ErrNoRows) {
		return 0, nil
	}
	return v, err
}

// Pending outside effects of a review result, done after the engine's own state is saved (HM-35 finding 7).
const (
	pendingComment = "comment"
	pendingMark    = "mark"
	pendingMail    = "mail"
)

type pendingPayload struct {
	Key, Text, Agent, Ref, To, Subject, Kind string
	Passed                                   bool
}

func (e *Engine) addPending(goal, child, action string, p pendingPayload) error {
	b, _ := json.Marshal(p)
	_, err := e.State.Exec("INSERT INTO pending(goal_id, child_key, action, payload, created) VALUES(?,?,?,?,?)",
		goal, child, action, string(b), e.Env.Now().Format(tsLayout))
	return err
}

// runPending does a run's queued comments, marks and mails in order, each once: a done item is deleted, the first
// failure stops the queue until the next call (one warning per item).
func (e *Engine) runPending(r Run) error {
	rows, err := e.State.Query("SELECT id, COALESCE(child_key, ''), action, payload FROM pending WHERE goal_id=? ORDER BY id", r.GoalID)
	if err != nil {
		return err
	}
	type item struct {
		id            int64
		child, action string
		p             pendingPayload
	}
	var items []item
	for rows.Next() {
		var it item
		var raw string
		if err := rows.Scan(&it.id, &it.child, &it.action, &raw); err != nil {
			rows.Close()
			return err
		}
		json.Unmarshal([]byte(raw), &it.p)
		items = append(items, it)
	}
	rows.Close()
	for _, it := range items {
		if err := e.doPending(r, it.action, it.p); err != nil {
			summary := fmt.Sprintf("queued %s for %s failed; retried next tick", it.action, it.child)
			var n int
			e.State.QueryRow("SELECT count(*) FROM incidents WHERE goal_id=? AND cause=? AND summary=?", r.GoalID,
				string(CausePendingFailed), summary).Scan(&n)
			if n == 0 {
				detail := map[string]any{"action": it.action, "error": err.Error(), "pending_id": it.id}
				var te *tsr.Error
				if errors.As(err, &te) {
					detail["http_status"], detail["route"] = te.Status, te.Method+" "+te.Path
				}
				e.Record(Incident{GoalID: r.GoalID, ChildKey: it.child, Kind: KindWarning, Cause: CausePendingFailed,
					Actor: ActorEngine, Summary: summary, Detail: detail})
			}
			return nil
		}
		if _, err := e.State.Exec("DELETE FROM pending WHERE id=?", it.id); err != nil {
			return err
		}
	}
	return nil
}

func (e *Engine) doPending(r Run, action string, p pendingPayload) error {
	if action == pendingMail {
		_, err := e.mail(r, p.To, p.Kind, p.Subject, p.Text)
		return err
	}
	tr, err := e.Deps.Tracker()
	if err != nil {
		return err
	}
	t, err := tr.TaskByKey(p.Key)
	if err != nil {
		return err
	}
	if action == pendingComment {
		return tr.Comment(t.ID, p.Text)
	}
	result := tsr.ResultFailed
	if p.Passed {
		result = tsr.ResultPassed
	}
	return tr.AgentCheck(t.ID, tsr.CheckReview, &result, p.Agent, p.Ref)
}
