package workflow

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"strconv"
	"strings"
)

const (
	reviewPrefix   = "review-"
	roundInfix     = "-r"
	findingsHeader = "Findings of round %d, to check first:"
)

// reviewerSession is config workflow_reviewer_session, read when a review starts (the owner may switch it mid-run).
func (e *Engine) reviewerSession() string {
	var v string
	if e.Factory.QueryRow("SELECT value FROM config WHERE key=?", cfgReviewerSession).Scan(&v) != nil || v != ReviewerSessionKeep {
		return defaultReviewerSession
	}
	return v
}

// reviewerNames are the names a reviewer of this child and round may have: fresh (one per child and round) and keep
// (one per story run).
func (e *Engine) reviewerNames(r Run, c childRow) (fresh, keep string, err error) {
	if fresh, err = e.agentName(r.GoalID, reviewPrefix+strings.ToLower(c.key)+roundInfix+strconv.Itoa(c.rounds+1)); err != nil {
		return "", "", err
	}
	keep, err = e.agentName(r.GoalID, reviewPrefix+strings.ToLower(r.TaskID))
	return fresh, keep, err
}

// advanceReview keeps one review going per run: it watches the child under review, or starts a reviewer for the first
// child waiting. It reports whether the run was stopped.
func (e *Engine) advanceReview(r Run, kids []childRow) (bool, error) {
	for i := range kids {
		if kids[i].state == string(ChildReviewing) {
			stopped, err := e.checkReviewer(r, &kids[i])
			if err != nil || stopped || kids[i].state == string(ChildReviewing) {
				return stopped, err
			}
			break // its reviewer ended silently: the child waits again, and a new reviewer starts below
		}
	}
	for i := range kids {
		if kids[i].state == string(ChildInReview) {
			return false, e.startReview(r, &kids[i])
		}
	}
	return false, nil
}

// previousFindings is "" in round 1, else each earlier round's notes under its header (kept in the review-changes
// incidents), so a fresh reviewer has what a kept one remembers.
func (e *Engine) previousFindings(goal, child string) (string, error) {
	rows, err := e.State.Query(`SELECT COALESCE(round, 0), detail FROM incidents WHERE goal_id=? AND child_key=? AND cause=?
		ORDER BY id`, goal, child, string(CauseReviewChanges))
	if err != nil {
		return "", err
	}
	defer rows.Close()
	var parts []string
	for rows.Next() {
		var round int
		var raw string
		if err := rows.Scan(&round, &raw); err != nil {
			return "", err
		}
		var d struct {
			Notes string `json:"notes"`
		}
		json.Unmarshal([]byte(raw), &d)
		parts = append(parts, fmt.Sprintf(findingsHeader, round)+"\n\n"+strings.TrimSpace(d.Notes))
	}
	return strings.Join(parts, "\n\n"), rows.Err()
}

// startReview starts (fresh) or resumes (keep) the reviewer of a child that is In Review.
func (e *Engine) startReview(r Run, c *childRow) error {
	fresh, keep, err := e.reviewerNames(r, *c)
	if err != nil {
		return err
	}
	prev, err := e.previousFindings(r.GoalID, c.key)
	if err != nil {
		return err
	}
	round := c.rounds + 1
	shown := round
	if round == 1 {
		shown = 0 // round 1 shows every commit of the child
	}
	commits, err := e.commitsText(r.GoalID, c.key, shown)
	if err != nil {
		return err
	}
	values := map[string]string{phGoal: r.GoalID, phTask: r.TaskID, phChild: c.key, phStory: c.story,
		phRound: strconv.Itoa(round), phMaxRounds: strconv.Itoa(MaxFixRounds), phBaseSHA: c.base, phHeadSHA: c.head,
		phPreviousFindings: prev, phCommits: commits}
	name := fresh
	if e.reviewerSession() == ReviewerSessionKeep {
		kept, found, err := e.agent(keep, "", "")
		if err != nil {
			return err
		}
		switch {
		case !found: // the run's first review: the kept reviewer starts here
			name = keep
		case !ended(kept.status): // still running: the next child arrives as mail
			if err := e.sendKeptReview(r, keep, values); err != nil {
				return err
			}
			return e.markReviewing(r, c)
		case kept.session == "":
			e.recordFallback(r, c, keep, "no session id is recorded for it")
		default:
			if _, err := e.Deps.Factory.Run("", "spawn", roleReviewer, "--goal", r.GoalID, "--task", r.TaskID,
				"--name", keep, "--resume", kept.session); err != nil {
				e.recordFallback(r, c, keep, "the resume was refused: "+err.Error())
				break
			}
			if err := e.sendKeptReview(r, keep, values); err != nil {
				return err
			}
			return e.markReviewing(r, c)
		}
	}
	tmpl, err := e.template(childReviewTemplate)
	if err != nil {
		return err
	}
	values[phAgent] = name
	kick, err := fill(childReviewTemplate, tmpl, values, phPreviousFindings)
	if err != nil {
		return err
	}
	ok, err := e.spawnRetried(r, name, func() error {
		_, err := e.Deps.Factory.Run(kick, "spawn", roleReviewer, "--goal", r.GoalID, "--task", r.TaskID,
			"--name", name, "--prompt", "-")
		return err
	})
	if err != nil || !ok {
		return err
	}
	return e.markReviewing(r, c)
}

// spawnRetried runs one spawn. A refusal is retried on the next ticks; only the MaxSpawnRetries-th refusal in a row for
// the same agent name stops the run for the boss (HM-35 finding 5). ok reports a successful spawn.
func (e *Engine) spawnRetried(r Run, name string, spawn func() error) (ok bool, err error) {
	key := "spawn-refused:" + name
	serr := spawn()
	if serr == nil {
		_, err = e.counter(r.GoalID, key, 0, true)
		return true, err
	}
	n, err := e.counter(r.GoalID, key, 1, false)
	if err != nil || n < MaxSpawnRetries {
		return false, err
	}
	e.counter(r.GoalID, key, 0, true)
	detail := map[string]any{"agent": name, "refusals": n, "error": serr.Error()}
	var ce *CmdError
	if errors.As(serr, &ce) {
		detail["exit_code"], detail["stderr"] = ce.ExitCode(), ce.Stderr
	}
	subject := fmt.Sprintf("story run %s: %s could not be started", r.GoalID, name)
	body := fmt.Sprintf("factory spawn refused %s %d times in a row; the last answer: %s. The run is stopped. Fix the "+
		"cause, then factory wf resume --goal %s.", name, n, firstLine(serr.Error()), r.GoalID)
	return false, e.stopRun(r, Incident{Kind: KindEscalation, Cause: CauseSpawnRetryLimit, Actor: ActorEngine,
		Summary: fmt.Sprintf("%s refused %d times in a row", name, n), Detail: detail}, subject, body)
}

func (e *Engine) sendKeptReview(r Run, name string, values map[string]string) error {
	tmpl, err := e.template(childReviewResumedTemplate)
	if err != nil {
		return err
	}
	text, err := fill(childReviewResumedTemplate, tmpl, values, phPreviousFindings)
	if err != nil {
		return err
	}
	_, err = e.mail(r, name, mailRequest, fmt.Sprintf("review %s, round %s", values[phChild], values[phRound]), text)
	return err
}

// recordFallback notes that keep mode could not resume and this review runs fresh.
func (e *Engine) recordFallback(r Run, c *childRow, name, why string) {
	e.Record(Incident{GoalID: r.GoalID, ChildKey: c.key, Kind: KindWarning, Cause: CauseReviewerResumeFallback,
		Actor: ActorEngine, Round: c.rounds + 1, Summary: fmt.Sprintf("kept reviewer %s not resumed (%s); this review runs fresh", name, firstLine(why)),
		Detail: map[string]any{"agent": name, "why": why}})
}

func (e *Engine) markReviewing(r Run, c *childRow) error {
	c.state = string(ChildReviewing)
	return e.setChild(r.GoalID, *c)
}

// checkReviewer handles a reviewer that ended without `factory wf review`: the child waits for a new reviewer once;
// the second such end stops the run.
func (e *Engine) checkReviewer(r Run, c *childRow) (bool, error) {
	fresh, keep, err := e.reviewerNames(r, *c)
	if err != nil {
		return false, err
	}
	var rev agentRow
	for _, n := range []string{fresh, keep} {
		a, found, err := e.agent(n, "", "")
		if err != nil {
			return false, err
		}
		if found && !ended(a.status) {
			return false, nil // still reviewing
		}
		if found && rev.name == "" {
			rev = a
		}
	}
	if rev.name == "" {
		return false, nil // not started yet (a queued spawn)
	}
	inc := Incident{GoalID: r.GoalID, ChildKey: c.key, Kind: KindWarning, Cause: CauseReviewerEndedSilently,
		Actor: rev.name, Round: c.rounds + 1, BaseSHA: c.base, HeadSHA: c.head,
		Summary: fmt.Sprintf("reviewer %s ended (%s) without factory wf review", rev.name, rev.status),
		Detail:  map[string]any{"agent": rev.name, "agent_status": rev.status}}
	n, err := e.countSince(r.GoalID, c.key, CauseReviewerEndedSilently)
	if err != nil {
		return false, err
	}
	if n+1 >= MaxSilentReviewerEnds {
		inc.Kind = KindEscalation
		c.state = string(ChildInReview)
		if err := e.setChild(r.GoalID, *c); err != nil {
			return false, err
		}
		subject := fmt.Sprintf("story run %s: no review result for %s", r.GoalID, c.key)
		body := fmt.Sprintf("Two reviewers of %s ended without a result (the last: %s, %s). The run is stopped. "+
			"Look at their panes or logs, then factory wf resume --goal %s.", c.key, rev.name, rev.status, r.GoalID)
		return true, e.stopRun(r, inc, subject, body)
	}
	if _, err := e.Record(inc); err != nil {
		return false, err
	}
	c.state = string(ChildInReview) // the next tick starts a new reviewer
	return false, e.setChild(r.GoalID, *c)
}

// reviewerRun checks that who is the reviewer started for child's current review, and returns the run and child.
func (e *Engine) reviewerRun(who, child string) (Run, childRow, error) {
	refuse := fmt.Errorf("%s is not the reviewer of %s's current review round", who, child)
	r, err := e.runOfAgent(who, roleReviewer)
	if err != nil {
		return Run{}, childRow{}, refuse
	}
	kids, err := e.children(r.GoalID)
	if err != nil {
		return Run{}, childRow{}, err
	}
	for _, c := range kids {
		if c.key != child {
			continue
		}
		fresh, keep, err := e.reviewerNames(r, c)
		if err != nil {
			return Run{}, childRow{}, err
		}
		if c.state != string(ChildReviewing) || (who != fresh && who != keep) {
			return Run{}, childRow{}, refuse
		}
		return r, c, nil
	}
	return Run{}, childRow{}, refuse
}

// review records one reviewer's result: a comment with the notes and the "reviewed by agent" mark in Taskosaur, then
// reviewed, or fixing with mail to the builder, or after MaxFixRounds stuck with the run stopped.
func (e *Engine) review(r Run, c childRow, who string, pass bool, notes string, w io.Writer) error {
	round := c.rounds + 1
	verdict := "pass"
	if !pass {
		verdict = "changes requested"
	}
	header := fmt.Sprintf("Review of %s, round %d of %d: %s (reviewer %s, commits %s..%s)", c.key, round, MaxFixRounds,
		verdict, who, short(c.base), short(c.head))
	// The engine's own state first, then the outside effects through the pending queue, each done once (finding 7).
	queue := func() error {
		if err := e.addPending(r.GoalID, c.key, pendingComment, pendingPayload{Key: c.key,
			Text: header + "\n\n" + strings.TrimSpace(notes)}); err != nil {
			return err
		}
		return e.addPending(r.GoalID, c.key, pendingMark, pendingPayload{Key: c.key, Agent: who, Ref: c.head, Passed: pass})
	}
	if pass {
		c.state = string(ChildReviewed)
		if err := e.setChild(r.GoalID, c); err != nil {
			return err
		}
		if err := queue(); err != nil {
			return err
		}
		fmt.Fprintf(w, "%s: reviewed\n", c.key)
		return e.runPending(r)
	}
	b, found, err := e.agent("", r.TaskID, roleCoder)
	if err != nil {
		return err
	}
	c.rounds = round
	c.state = string(ChildFixing)
	if round >= MaxFixRounds {
		c.state = string(ChildStuck)
	}
	if err := e.setChild(r.GoalID, c); err != nil {
		return err
	}
	if _, err := e.Record(Incident{GoalID: r.GoalID, ChildKey: c.key, Kind: KindRejection, Cause: CauseReviewChanges,
		Actor: who, Round: round, BaseSHA: c.base, HeadSHA: c.head, Summary: header,
		Detail: map[string]any{"notes": notes, "reviewer": who, "task_id": r.TaskID,
			"builder_live": found && !ended(b.status)}}); err != nil {
		return err
	}
	if err := queue(); err != nil {
		return err
	}
	if round >= MaxFixRounds {
		if err := e.runPending(r); err != nil {
			return err
		}
		all, err := e.previousFindings(r.GoalID, c.key)
		if err != nil {
			return err
		}
		subject := fmt.Sprintf("story run %s: %s did not converge in %d rounds", r.GoalID, c.key, MaxFixRounds)
		body := fmt.Sprintf("Child %s got changes requested %d times. The run is stopped; nothing more is built or "+
			"reviewed until factory wf resume --goal %s (which resets its rounds). The findings of every round "+
			"(also comments on %s):\n\n%s", c.key, round, r.GoalID, c.key, all)
		fmt.Fprintf(w, "%s: changes requested, round limit reached; the run is stopped\n", c.key)
		return e.stopRun(r, Incident{ChildKey: c.key, Kind: KindEscalation, Cause: CauseRoundLimit, Actor: ActorEngine,
			Round: round, Summary: fmt.Sprintf("%s: %d rounds of changes", c.key, round)}, subject, body)
	}
	to := b.name
	if !found {
		if to, err = e.builderName(r.GoalID, r.TaskID); err != nil {
			return err
		}
	}
	tmpl, err := e.template(builderFindingsTemplate)
	if err != nil {
		return err
	}
	text, err := fill(builderFindingsTemplate, tmpl, map[string]string{phChild: c.key, phRound: strconv.Itoa(round),
		phMaxRounds: strconv.Itoa(MaxFixRounds)})
	if err != nil {
		return err
	}
	if err := e.addPending(r.GoalID, c.key, pendingMail, pendingPayload{To: to, Kind: mailRequest, Text: text,
		Subject: fmt.Sprintf("review of %s: changes requested (round %d of %d)", c.key, round, MaxFixRounds)}); err != nil {
		return err
	}
	fmt.Fprintf(w, "%s: changes requested (round %d of %d); the builder is told\n", c.key, round, MaxFixRounds)
	return e.runPending(r)
}

func short(sha string) string {
	if len(sha) > 12 {
		return sha[:12]
	}
	return sha
}

// resume lets a stopped run go on (boss or owner): stuck children get their rounds back, blocked children wait to be
// built again, and the counters of early ends start over. --fresh-builder starts a new builder session told what is
// built; otherwise an ended builder is resumed by the next tick.
func (e *Engine) resume(goal string, freshBuilder bool, who string, w io.Writer) error {
	var r Run
	err := e.State.QueryRow(`SELECT goal_id, story_key, workflow, COALESCE(task_id, ''), state FROM runs WHERE goal_id=?`,
		goal).Scan(&r.GoalID, &r.StoryKey, &r.Workflow, &r.TaskID, &r.State)
	if err != nil {
		return usageError{fmt.Sprintf("no run %s", goal)}
	}
	if r.State != RunBlocked {
		return usageError{fmt.Sprintf("run %s is %s, not blocked; nothing to resume", goal, r.State)}
	}
	kids, err := e.children(goal)
	if err != nil {
		return err
	}
	for _, c := range kids {
		switch c.state {
		case string(ChildStuck):
			c.state, c.rounds = string(ChildFixing), 0
		case string(ChildBlocked):
			c.state = string(ChildTodo)
		default:
			continue
		}
		if err := e.setChild(goal, c); err != nil {
			return err
		}
	}
	if _, err := e.Record(Incident{GoalID: goal, Kind: KindWarning, Cause: CauseOwnerResumed, Actor: who,
		Summary: fmt.Sprintf("run resumed by %s (fresh builder: %v)", who, freshBuilder),
		Detail:  map[string]any{"fresh_builder": freshBuilder}}); err != nil {
		return err
	}
	if freshBuilder {
		if err := e.startFreshBuilder(r, kids); err != nil {
			return err
		}
	}
	if err := e.setRunState(goal, RunBuilding); err != nil {
		return err
	}
	fmt.Fprintf(w, "run %s: building again\n", goal)
	return nil
}

// startFreshBuilder is the one path that starts a builder without --resume: the owner's decision.
func (e *Engine) startFreshBuilder(r Run, kids []childRow) error {
	name, err := e.builderName(r.GoalID, r.TaskID)
	if err != nil {
		return err
	}
	if b, found, err := e.agent("", r.TaskID, roleCoder); err != nil {
		return err
	} else if found && !ended(b.status) {
		return errors.New("the builder " + b.name + " is still running; stop it first (factory stop " + b.name + ")")
	}
	stories, err := e.State.Query("SELECT story_key FROM run_stories WHERE goal_id=? ORDER BY position", r.GoalID)
	if err != nil {
		return err
	}
	var keys []string
	for stories.Next() {
		var k string
		stories.Scan(&k)
		keys = append(keys, k)
	}
	stories.Close()
	var done, todo []string
	for _, c := range kids {
		if c.head != "" && (c.state != string(ChildTodo)) {
			done = append(done, fmt.Sprintf("- %s (story %s): %s..%s, %s", c.key, c.story, c.base, c.head, c.state))
		} else {
			todo = append(todo, c.key)
		}
	}
	if len(done) == 0 {
		done = []string{"- none"}
	}
	tmpl, err := e.template(builderFreshTemplate)
	if err != nil {
		return err
	}
	kick, err := fill(builderFreshTemplate, tmpl, map[string]string{phAgent: name, phGoal: r.GoalID, phTask: r.TaskID,
		phBranch: branchPrefix + strings.ToLower(r.TaskID), phStories: strings.Join(keys, ", "),
		phChildrenDone: strings.Join(done, "\n"), phChildrenTodo: strings.Join(todo, ", ")}, phChildrenTodo)
	if err != nil {
		return err
	}
	_, err = e.Deps.Factory.Run(kick, "spawn", roleCoder, "--goal", r.GoalID, "--task", r.TaskID, "--name", name, "--prompt", "-")
	return err
}
