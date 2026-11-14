package workflow

import (
	"database/sql"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"factory/go/internal/factorydb"
	"factory/go/internal/identity"
	"factory/go/internal/tsr"
)

// Mail the engine sends (factory msg <to> ... --kind) and other fixed values.
const (
	mailTo        = "boss"
	mailDecision  = "decision"
	mailRequest   = "request"
	eventBuilt    = "built"
	defaultBranch = "main"
)

// agentEnded is the agent statuses the factory counts as ended (bin/factory_cli.py coder_ci_resume_tick).
var agentEnded = []string{"done", "exited", "lost", "cancelled"}

// Mail and kickoff templates of HM-31, loaded, never reworded.
const (
	childReviewTemplate        = "workflows/prompts/child-review.md"
	childReviewResumedTemplate = "workflows/prompts/child-review-resumed.md"
	builderFindingsTemplate    = "workflows/prompts/builder-findings.md"
	builderResumedTemplate     = "workflows/prompts/builder-resumed.md"
	builderFreshTemplate       = "workflows/prompts/builder-fresh.md"
)

// Placeholders of those templates (the kickoff ones are in start.go).
const (
	phChild            = "child"
	phStory            = "story"
	phRound            = "round"
	phMaxRounds        = "max_rounds"
	phBaseSHA          = "base_sha"
	phHeadSHA          = "head_sha"
	phPreviousFindings = "previous_findings"
	phCommits          = "commits"
	phResumeCount      = "resume_count"
	phMaxResumes       = "max_resumes"
	phChildrenState    = "children_state"
	phPending          = "pending"
	phChildrenDone     = "children_done"
	phChildrenTodo     = "children_todo"
)

// Review results of `factory wf review`.
const (
	reviewPass    = "pass"
	reviewChanges = "changes"
)

// runMain handles the commands that change a run: start and resume (boss), blocked and built (the run's builder),
// review (the child's reviewer).
func runMain(cmd string, rest []string, env identity.Env, stdout, stderr io.Writer) int {
	home := env.Home()
	fail := func(code int, err error) int {
		fmt.Fprintf(stderr, "factory wf %s: %v\n", cmd, err)
		return code
	}
	fs := flag.NewFlagSet("factory wf "+cmd, flag.ContinueOnError)
	fs.SetOutput(stderr)
	var workflow, project, reason, notes, goal *string
	var stories keyList
	var freshBuilder *bool
	var pos []string
	want := 0
	switch cmd {
	case "start":
		fs.Var(&stories, "story", "Taskosaur key of a story to build; repeat it for a batch, in the order of work")
		workflow = fs.String("workflow", "", "simple, medium or huge; default: chosen from size and complexity")
		project = fs.String("project", "", "factory project of the goal")
	case "resume":
		goal = fs.String("goal", "", "the run's goal")
		freshBuilder = fs.Bool("fresh-builder", false, "start a new builder session instead of resuming the old one")
	case "blocked":
		reason = fs.String("reason", "", "one sentence: why the child cannot be built as written")
		want = 1
	case "review":
		notes = fs.String("notes", "", "file with the review notes")
		want = 2
	}
	for len(rest) > 0 && len(pos) < want && !strings.HasPrefix(rest[0], "-") {
		pos, rest = append(pos, rest[0]), rest[1:]
	}
	if err := fs.Parse(rest); err != nil || fs.NArg() > 0 || len(pos) != want || (cmd == "start" && len(stories) == 0) ||
		(goal != nil && *goal == "") || (reason != nil && strings.TrimSpace(*reason) == "") || (notes != nil && *notes == "") ||
		(cmd == "review" && pos[1] != reviewPass && pos[1] != reviewChanges) {
		fmt.Fprintln(stderr, usage)
		return exitUsage
	}
	if workflow != nil && *workflow != "" && !contains(Workflows, *workflow) {
		return fail(exitUsage, fmt.Errorf("--workflow must be one of %v", Workflows))
	}
	var who string
	var code int
	var err error
	if cmd == "start" || cmd == "resume" {
		who, code, err = requireRole(env, home, roleBoss)
	} else {
		who, err = env.Resolve(func() (*factorydb.DB, error) { return factorydb.Open(factorydb.ResolvePath(home)) })
		code = exitRefuse
		var ee *identity.ExitError
		if errors.As(err, &ee) {
			code = ee.Code
		}
	}
	if err != nil {
		return fail(code, err)
	}
	e, closeAll, err := open(env, home)
	if err != nil {
		return fail(exitErr, err)
	}
	defer closeAll()
	if cmd != "built" && cmd != "blocked" {
		if _, err := e.deps(); err != nil {
			return fail(exitErr, err)
		}
	}
	var ue usageError
	switch cmd {
	case "start":
		p, err := e.planStart(stories, *workflow, *project)
		if errors.As(err, &ue) {
			e.Record(Incident{GoalID: noGoal, Kind: KindRejection, Cause: CauseStartRefused, Actor: who,
				Summary: "start refused: " + firstLine(err.Error()), Detail: map[string]any{"stories": []string(stories),
					"reason": err.Error()}})
			return fail(exitUsage, err)
		}
		if err != nil {
			return fail(exitErr, err)
		}
		if _, err := e.start(p, stdout); err != nil {
			return fail(exitErr, err)
		}
		return exitOK
	case "resume":
		err := e.resume(*goal, *freshBuilder, who, stdout)
		if errors.As(err, &ue) {
			return fail(exitUsage, err)
		}
		if err != nil {
			return fail(exitErr, err)
		}
		return exitOK
	case "review":
		r, kid, err := e.reviewerRun(who, pos[0])
		if err != nil {
			return fail(exitRefuse, err)
		}
		text, err := os.ReadFile(*notes)
		if err != nil || strings.TrimSpace(string(text)) == "" {
			return fail(exitUsage, fmt.Errorf("--notes %s: missing or empty", *notes))
		}
		if err := e.review(r, kid, who, pos[1] == reviewPass, string(text), stdout); err != nil {
			return fail(exitErr, err)
		}
		return exitOK
	}
	run, err := e.builderRun(who)
	if err != nil {
		return fail(exitRefuse, err)
	}
	if cmd == "built" {
		if err := e.setRunState(run.GoalID, RunBuilt); err != nil {
			return fail(exitErr, err)
		}
		if err := e.Env.EventAs(e.Factory, who, EventEntity, run.GoalID, eventBuilt, "run built"); err != nil {
			return fail(exitErr, err)
		}
		fmt.Fprintf(stdout, "run %s: built\n", run.GoalID)
		return exitOK
	}
	if err := e.blocked(run, who, pos[0], *reason); err != nil {
		return fail(exitErr, err)
	}
	fmt.Fprintf(stdout, "run %s: blocked on %s; the boss is told\n", run.GoalID, pos[0])
	return exitOK
}

// keyList is a repeatable string flag (--story A --story B).
type keyList []string

func (k *keyList) String() string { return strings.Join(*k, ",") }

func (k *keyList) Set(v string) error {
	if strings.TrimSpace(v) == "" {
		return errors.New("empty key")
	}
	*k = append(*k, strings.TrimSpace(v))
	return nil
}

// noGoal is the goal id of an incident recorded before any goal exists (a refused start).
const noGoal = "-"

func contains(list []string, s string) bool {
	for _, x := range list {
		if x == s {
			return true
		}
	}
	return false
}

// runOfAgent is the run whose factory task the agent who (of role) works on.
func (e *Engine) runOfAgent(who, role string) (Run, error) {
	var task string
	err := e.Factory.QueryRow("SELECT COALESCE(task_id, '') FROM agents WHERE name=? AND role=?", who, role).Scan(&task)
	if err != nil || task == "" {
		return Run{}, fmt.Errorf("no story run has %s as its %s", who, role)
	}
	var r Run
	err = e.State.QueryRow(`SELECT goal_id, story_key, workflow, COALESCE(task_id, ''), state FROM runs WHERE task_id=?`,
		task).Scan(&r.GoalID, &r.StoryKey, &r.Workflow, &r.TaskID, &r.State)
	if err != nil {
		return Run{}, fmt.Errorf("no story run has %s as its %s", who, role)
	}
	return r, nil
}

// builderRun is the run whose builder is who: the coder agent of the run's factory task. Anyone else is refused.
func (e *Engine) builderRun(who string) (Run, error) {
	r, err := e.runOfAgent(who, roleCoder)
	if err != nil {
		return Run{}, fmt.Errorf("%s is not the builder of a story run; only a run's builder may do this", who)
	}
	return r, nil
}

// blocked stops the run on one child: child and run state blocked, an escalation incident, a decision mail to the boss.
func (e *Engine) blocked(r Run, who, child, reason string) error {
	now := e.Env.Now().Format(tsLayout)
	res, err := e.State.Exec("UPDATE children SET state=?, updated=? WHERE goal_id=? AND child_key=?",
		string(ChildBlocked), now, r.GoalID, child)
	if err != nil {
		return err
	}
	if n, _ := res.RowsAffected(); n == 0 {
		return fmt.Errorf("%s is not a child of run %s", child, r.GoalID)
	}
	subject := fmt.Sprintf("story run %s blocked on %s", r.GoalID, child)
	body := fmt.Sprintf("The builder %s cannot build %s as written:\n\n%s\n\nIts comment on %s has the details. "+
		"Decide, tell the builder (factory msg %s ...), then factory wf resume --goal %s.", who, child, reason, child, who, r.GoalID)
	return e.stopRun(r, Incident{ChildKey: child, Kind: KindEscalation, Cause: CauseBuilderBlocked, Actor: who,
		Summary: firstLine(reason), Detail: map[string]any{"reason": reason}}, subject, body)
}

// stopRun blocks the run, mails the boss a decision and records the incident (with the mail's answer or error).
func (e *Engine) stopRun(r Run, inc Incident, subject, body string) error {
	if err := e.setRunState(r.GoalID, RunBlocked); err != nil {
		return err
	}
	mail, mailErr := e.mail(r, mailTo, mailDecision, subject, body)
	inc.GoalID = r.GoalID
	if inc.Detail == nil {
		inc.Detail = map[string]any{}
	}
	inc.Detail["task_id"], inc.Detail["mail"] = r.TaskID, mail
	if mailErr != nil {
		inc.Detail["mail_error"] = mailErr.Error()
	}
	if _, err := e.Record(inc); err != nil {
		return err
	}
	return mailErr
}

// mail sends a message as the owner and returns factory msg's answer line (M#### -> recipient).
func (e *Engine) mail(r Run, to, kind, subject, body string) (string, error) {
	d, err := e.deps()
	if err != nil {
		return "", err
	}
	args := []string{"msg", to, subject, "-", "--kind", kind, "--goal", r.GoalID}
	if r.TaskID != "" {
		args = append(args, "--task", r.TaskID)
	}
	out, err := d.Factory.Run(body, args...)
	return strings.TrimSpace(out), err
}

// template reads one of the run's text files.
func (e *Engine) template(rel string) (string, error) {
	b, err := os.ReadFile(filepath.Join(e.Deps.SrcDir, rel))
	if err != nil {
		return "", fmt.Errorf("template %s: %w", rel, err)
	}
	return string(b), nil
}

type childRow struct {
	key, story, state, base, head string
	rounds                        int
}

func (e *Engine) children(goal string) ([]childRow, error) {
	rows, err := e.State.Query(`SELECT child_key, story_key, state, rounds, COALESCE(base_sha, ''), COALESCE(head_sha, '')
		FROM children WHERE goal_id=? ORDER BY position`, goal)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var kids []childRow
	for rows.Next() {
		var c childRow
		if err := rows.Scan(&c.key, &c.story, &c.state, &c.rounds, &c.base, &c.head); err != nil {
			return nil, err
		}
		kids = append(kids, c)
	}
	return kids, rows.Err()
}

func (e *Engine) setChild(goal string, c childRow) error {
	_, err := e.State.Exec(`UPDATE children SET state=?, rounds=?, base_sha=?, head_sha=?, updated=? WHERE goal_id=? AND child_key=?`,
		c.state, c.rounds, nullable(c.base), nullable(c.head), e.Env.Now().Format(tsLayout), goal, c.key)
	return err
}

func nullable(s string) any {
	if s == "" {
		return nil
	}
	return s
}

// advanceBuilding moves a building (or built) run on by one tick:
//  1. a child the builder set In Review gets its commit range (a fixed child keeps its base, gets a new head);
//  2. one reviewer at a time: the first child waiting for review gets one, a reviewer that ended silently is handled;
//  3. a builder that ended while work is left is resumed (at most MaxBuilderResumes), else the run stops.
func (e *Engine) advanceBuilding(r Run) error {
	d, err := e.deps()
	if err != nil {
		return err
	}
	kids, err := e.children(r.GoalID)
	if err != nil {
		return err
	}
	tr, err := d.Tracker()
	if err != nil {
		return err
	}
	for i := range kids {
		c := &kids[i]
		if c.state != string(ChildTodo) && c.state != string(ChildFixing) {
			continue
		}
		t, err := tr.TaskByKey(c.key)
		if err != nil {
			return err
		}
		if !inReview(t.Status) {
			continue
		}
		// the commits were recorded when the builder set the status (factory wf tsr status … in_review); a child moved
		// another way has none for this round and waits until the builder runs that command
		cs, err := e.commitsOf(r.GoalID, c.key, c.rounds+1)
		if err != nil || len(cs) == 0 {
			continue
		}
		c.state = string(ChildInReview)
		if err := e.setChild(r.GoalID, *c); err != nil {
			return err
		}
	}
	stopped, err := e.advanceReview(r, kids)
	if err != nil || stopped {
		return err
	}
	left := 0
	for _, c := range kids {
		if c.state == string(ChildTodo) || c.state == string(ChildFixing) {
			left++
		}
	}
	if left > 0 {
		return e.checkBuilder(r, kids, left)
	}
	return nil
}

func inReview(s tsr.Status) bool { return s.UserAction != nil && *s.UserAction == tsr.UserActionReview }

// taskCheckout is the factory task's worktree, branch and base branch.
func (e *Engine) taskCheckout(task string) (wt, branch, base string, err error) {
	err = e.Factory.QueryRow(`SELECT COALESCE(t.worktree, ''), COALESCE(t.branch, ''), COALESCE(p.base_branch, '')
		FROM tasks t JOIN goals g ON g.id = t.goal_id LEFT JOIN projects p ON p.id = g.project_id WHERE t.id=?`,
		task).Scan(&wt, &branch, &base)
	if err != nil {
		return "", "", "", fmt.Errorf("task %s: %w", task, err)
	}
	if wt == "" {
		return "", "", "", fmt.Errorf("task %s has no worktree yet", task)
	}
	if branch == "" {
		branch = branchPrefix + strings.ToLower(task)
	}
	if base == "" {
		base = defaultBranch
	}
	return wt, branch, base, nil
}

// agentRow is the newest agents row of a name, or of a task and role when name is "".
type agentRow struct{ name, status, session string }

func (e *Engine) agent(name, task, role string) (agentRow, bool, error) {
	var a agentRow
	q, args := `SELECT name, status, COALESCE(session_id, '') FROM agents WHERE name=?`, []any{name}
	if name == "" {
		q, args = `SELECT name, status, COALESCE(session_id, '') FROM agents WHERE task_id=? AND role=? ORDER BY rowid DESC LIMIT 1`,
			[]any{task, role}
	}
	err := e.Factory.QueryRow(q, args...).Scan(&a.name, &a.status, &a.session)
	if errors.Is(err, sql.ErrNoRows) {
		return a, false, nil
	}
	return a, err == nil, err
}

func ended(status string) bool { return contains(agentEnded, status) }

// countSince counts this run's incidents of one cause (and child, when given) after the owner's last resume.
func (e *Engine) countSince(goal, child string, cause Cause) (int, error) {
	var n int
	err := e.State.QueryRow(`SELECT count(*) FROM incidents WHERE goal_id=?1 AND cause=?2 AND (?3 = '' OR child_key=?3)
		AND id > COALESCE((SELECT max(id) FROM incidents WHERE goal_id=?1 AND cause=?4), 0)`,
		goal, string(cause), child, string(CauseOwnerResumed)).Scan(&n)
	return n, err
}

// counterOpenPRLive is 1 once the builder had the mail to open the pull request while it was running.
const counterOpenPRLive = "open-pr-delivered"

// workInHand reports whether the ended builder had work it was doing (an early end, which counts against
// MaxBuilderResumes) rather than new work that arrived after it ended (a wake-up, not limited; HM-35 finding 6): a
// child still to build, a child to fix whose findings reached the builder while it ran or after a later resume, or the
// pull request after its mail reached the builder.
func (e *Engine) workInHand(r Run, kids []childRow) (bool, error) {
	var lastWake int64
	e.State.QueryRow(`SELECT COALESCE(max(id), 0) FROM incidents WHERE goal_id=? AND cause IN (?, ?)`, r.GoalID,
		string(CauseBuilderResumed), string(CauseBuilderWoken)).Scan(&lastWake)
	open := false
	for _, c := range kids {
		switch c.state {
		case string(ChildTodo):
			return true, nil
		case string(ChildFixing):
			open = true
			var id int64
			var raw string
			if err := e.State.QueryRow(`SELECT id, detail FROM incidents WHERE goal_id=? AND child_key=? AND cause=?
				ORDER BY id DESC LIMIT 1`, r.GoalID, c.key, string(CauseReviewChanges)).Scan(&id, &raw); err != nil {
				continue
			}
			var d struct {
				BuilderLive bool `json:"builder_live"`
			}
			json.Unmarshal([]byte(raw), &d)
			if d.BuilderLive || id < lastWake {
				return true, nil
			}
		}
	}
	if open {
		return false, nil
	}
	delivered, err := e.counter(r.GoalID, counterOpenPRLive, 0, false)
	return delivered > 0, err
}

// checkBuilder resumes a builder that ended while work is left, with its own session and the pending instruction by
// mail. An early end with work in hand is limited to MaxBuilderResumes; a resume that only delivers new work is not.
// With no session id, or after MaxSpawnRetries refusals in a row, the run stops for the boss. The engine never starts
// a builder fresh on its own: a fresh builder would not know the earlier children.
func (e *Engine) checkBuilder(r Run, kids []childRow, left int) error {
	b, found, err := e.agent("", r.TaskID, roleCoder)
	if err != nil || !found || !ended(b.status) {
		return err // not started yet (a queued spawn) or still working
	}
	inWork, err := e.workInHand(r, kids)
	if err != nil {
		return err
	}
	used, err := e.countSince(r.GoalID, "", CauseBuilderResumed)
	if err != nil {
		return err
	}
	why := ""
	switch {
	case inWork && used >= MaxBuilderResumes:
		why = fmt.Sprintf("resumed %d times already (limit %d)", used, MaxBuilderResumes)
	case b.session == "":
		why = "no session id is recorded for it"
	}
	if why == "" {
		ok, err := e.spawnRetried(r, b.name, func() error {
			_, err := e.Deps.Factory.Run("", "spawn", "coder", "--goal", r.GoalID, "--task", r.TaskID, "--name", b.name,
				"--resume", b.session)
			return err
		})
		if err != nil || !ok {
			return err // refused: retried next tick, or the run was stopped after MaxSpawnRetries
		}
	}
	if why != "" {
		subject := fmt.Sprintf("story run %s: the builder ended with %d children left", r.GoalID, left)
		body := fmt.Sprintf("The builder %s of run %s is %s while %d children are not built; it was not resumed: %s. "+
			"Decide, then factory wf resume --goal %s (add --fresh-builder for a new session that is told what is built).",
			b.name, r.GoalID, b.status, left, why, r.GoalID)
		return e.stopRun(r, Incident{Kind: KindEscalation, Cause: CauseBuilderResumeLimit, Actor: ActorEngine,
			Summary: fmt.Sprintf("builder %s ended with %d children left: %s", b.name, left, firstLine(why)),
			Detail: map[string]any{"agent": b.name, "agent_status": b.status, "children_left": left, "why": why,
				"resumes_used": used}}, subject, body)
	}
	count, cause := used, CauseBuilderWoken
	summary := fmt.Sprintf("builder %s (%s) resumed to receive new work; not counted", b.name, b.status)
	if inWork {
		count, cause = used+1, CauseBuilderResumed
		summary = fmt.Sprintf("builder %s ended early (%s); resumed %d of %d", b.name, b.status, count, MaxBuilderResumes)
	}
	text, err := e.builderResumedMail(r, kids, count)
	if err != nil {
		return err
	}
	mail, mailErr := e.mail(r, b.name, mailRequest, fmt.Sprintf("story run %s: resumed, continue", r.GoalID), text)
	detail := map[string]any{"agent": b.name, "agent_status": b.status, "session": b.session, "resume": count,
		"counted": inWork, "mail": mail}
	if mailErr != nil {
		detail["mail_error"] = mailErr.Error()
	}
	if mailErr == nil && left == 0 { // the open-PR instruction reached it with this mail
		e.counter(r.GoalID, counterOpenPRLive, 1, false)
	}
	if _, err := e.Record(Incident{GoalID: r.GoalID, Kind: KindWarning, Cause: cause, Actor: ActorEngine,
		Summary: summary, Detail: detail}); err != nil {
		return err
	}
	return mailErr
}

func (e *Engine) builderResumedMail(r Run, kids []childRow, n int) (string, error) {
	tmpl, err := e.template(builderResumedTemplate)
	if err != nil {
		return "", err
	}
	var lines []string
	pending := ""
	for _, c := range kids {
		lines = append(lines, fmt.Sprintf("- %s (story %s): %s", c.key, c.story, c.state))
		if pending == "" && c.state == string(ChildFixing) {
			pending = fmt.Sprintf("fix the review findings on child %s (factory wf tsr show %s)", c.key, c.key)
		}
	}
	for _, c := range kids {
		if pending == "" && c.state == string(ChildTodo) {
			pending = fmt.Sprintf("child %s is in work", c.key)
		}
	}
	if pending == "" {
		pending = "open the pull request (see the earlier mail)"
	}
	return fill(builderResumedTemplate, tmpl, map[string]string{phResumeCount: strconv.Itoa(n),
		phMaxResumes: strconv.Itoa(MaxBuilderResumes), phGoal: r.GoalID, phTask: r.TaskID,
		phBranch: branchPrefix + strings.ToLower(r.TaskID), phChildrenState: strings.Join(lines, "\n"), phPending: pending})
}
