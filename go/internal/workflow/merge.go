package workflow

import (
	"database/sql"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"

	"factory/go/internal/tsr"
)

// The open-PR mail of HM-31 and its placeholders.
const (
	builderOpenPRTemplate = "workflows/prompts/builder-open-pr.md"
	phTitle               = "title"
	phBody                = "body"
	phBase                = "base"
	phChildCount          = "child_count"
	phStoryCount          = "story_count"
)

// The factory's PR body rules (bin/factory_cli.py PR_HEADINGS, ACCEPTANCE_WALK, PR_WORDS_MAX): the five headings in
// order, the acceptance walk inside <details>, at most 300 words outside <details>.
var prHeadings = []string{"## Summary", "## Why", "## Changes", "## Test evidence", "## Risk / rollback"}

const (
	prAcceptanceWalk = "## Acceptance walk"
	prWordsMax       = 300
	mailReport       = "report"
	taskStatusDone   = "done"
	eventMerged      = "merged"
)

var mergedShaRE = regexp.MustCompile(`@([0-9a-f]{7,40})`)

// storyInfo is a story of the run with its Taskosaur record.
type storyInfo struct {
	task tsr.Task
	kids []childRow
}

func (e *Engine) stories(r Run, kids []childRow) ([]storyInfo, error) {
	tr, err := e.Deps.Tracker()
	if err != nil {
		return nil, err
	}
	rows, err := e.State.Query("SELECT story_key FROM run_stories WHERE goal_id=? ORDER BY position", r.GoalID)
	if err != nil {
		return nil, err
	}
	var keys []string
	for rows.Next() {
		var k string
		rows.Scan(&k)
		keys = append(keys, k)
	}
	rows.Close()
	var out []storyInfo
	for _, k := range keys {
		t, err := tr.TaskByKey(k)
		if err != nil {
			return nil, err
		}
		s := storyInfo{task: t}
		for _, c := range kids {
			if c.story == k {
				s.kids = append(s.kids, c)
			}
		}
		out = append(out, s)
	}
	return out, nil
}

// openPR tells the builder, once, to open the one pull request when every child is reviewed. The run is merging.
func (e *Engine) openPR(r Run) error {
	var state string
	if err := e.State.QueryRow("SELECT state FROM runs WHERE goal_id=?", r.GoalID).Scan(&state); err != nil || state != string(RunBuilt) {
		return err // the building step above may have stopped the run
	}
	kids, err := e.children(r.GoalID)
	if err != nil {
		return err
	}
	for _, c := range kids {
		if c.state != string(ChildReviewed) {
			return nil
		}
	}
	b, found, err := e.agent("", r.TaskID, roleCoder)
	if err != nil || !found {
		return fmt.Errorf("no builder to open the pull request of %s: %v", r.GoalID, err)
	}
	ss, err := e.stories(r, kids)
	if err != nil {
		return err
	}
	tr, _ := e.Deps.Tracker()
	titles := map[string]string{}
	for _, c := range kids {
		t, err := tr.TaskByKey(c.key)
		if err != nil {
			return err
		}
		titles[c.key] = t.Title
	}
	base, err := e.baseBranch(r.TaskID)
	if err != nil {
		return err
	}
	tmpl, err := e.template(builderOpenPRTemplate)
	if err != nil {
		return err
	}
	text, err := fill(builderOpenPRTemplate, tmpl, map[string]string{phTitle: prTitle(r.TaskID, ss),
		phBody: prBody(r, ss, titles), phTask: r.TaskID, phBase: base, phChildCount: strconv.Itoa(len(kids)),
		phStoryCount: strconv.Itoa(len(ss))})
	if err != nil {
		return err
	}
	if _, err := e.mail(r, b.name, mailRequest, fmt.Sprintf("story run %s: open the pull request", r.GoalID), text); err != nil {
		return err
	}
	if !ended(b.status) { // it got the instruction while running: a later end is an early end (finding 6)
		if _, err := e.counter(r.GoalID, counterOpenPRLive, 1, false); err != nil {
			return err
		}
	}
	return e.setRunState(r.GoalID, RunMerging)
}

func (e *Engine) baseBranch(task string) (string, error) {
	var base string
	err := e.Factory.QueryRow(`SELECT COALESCE(p.base_branch, '') FROM tasks t JOIN goals g ON g.id = t.goal_id
		LEFT JOIN projects p ON p.id = g.project_id WHERE t.id=?`, task).Scan(&base)
	if base == "" {
		base = defaultBranch
	}
	return base, err
}

func keysOf(ss []storyInfo) []string {
	var k []string
	for _, s := range ss {
		k = append(k, s.task.Key)
	}
	return k
}

// prTitle carries the factory task id first, as every factory PR title does; quotes are dropped because the mail puts
// it inside a shell argument.
func prTitle(task string, ss []storyInfo) string {
	keys := keysOf(ss)
	t := fmt.Sprintf("%s: batch %s..%s (%d stories)", task, keys[0], keys[len(keys)-1], len(keys))
	if len(ss) == 1 {
		t = fmt.Sprintf("%s: %s (%s)", task, ss[0].task.Title, ss[0].task.Key)
	}
	return strings.NewReplacer(`"`, "", "`", "", "$", "").Replace(t)
}

// prBody is a complete pull request body in the repository's template; titles are dropped from the Changes list when
// they would push the text outside <details> over the word limit.
func prBody(r Run, ss []storyInfo, titles map[string]string) string {
	for _, withTitles := range []bool{true, false} {
		b := buildPRBody(r, ss, titles, withTitles)
		if prWordsOutside(b) <= prWordsMax || !withTitles {
			return b
		}
	}
	return ""
}

func buildPRBody(r Run, ss []storyInfo, titles map[string]string, withTitles bool) string {
	keys := strings.Join(keysOf(ss), ", ")
	n := 0
	for _, s := range ss {
		n += len(s.kids)
	}
	noun := "story"
	if len(ss) > 1 {
		noun = "stories"
	}
	var b strings.Builder
	fmt.Fprintf(&b, "## Summary\nStory run of %s: %d children built one after another on this branch, each reviewed by "+
		"agent before this pull request.\n\n", keys, n)
	fmt.Fprintf(&b, "## Why\n%s: builds the task-manager %s %s as one story run (factory wf, goal %s).\n\n", r.TaskID, noun, keys, r.GoalID)
	b.WriteString("## Changes\n")
	for _, s := range ss {
		if withTitles {
			fmt.Fprintf(&b, "- %s: %s (%d children)\n", s.task.Key, s.task.Title, len(s.kids))
		} else {
			fmt.Fprintf(&b, "- %s (%d children)\n", s.task.Key, len(s.kids))
		}
	}
	b.WriteString("\n## Test evidence\nEach child ran its own and the affected tests, by the builder and again by its " +
		"reviewer; the commands and results are in the comments on each child. CI runs once, on this pull request.\n\n")
	b.WriteString("## Risk / rollback\nThe risks are those of each story's children (see the stories). Rollback = revert " +
		"this PR.\n\n")
	b.WriteString("<details><summary>Stories and children</summary>\n\n")
	for _, s := range ss {
		fmt.Fprintf(&b, "- %s: %s\n", s.task.Key, s.task.Title)
		for _, c := range s.kids {
			fmt.Fprintf(&b, "  - %s: %s (commits %s..%s, fix rounds %d)\n", c.key, titles[c.key], short(c.base), short(c.head), c.rounds)
		}
	}
	b.WriteString("</details>\n\n<details><summary>Acceptance walk</summary>\n\n" + prAcceptanceWalk + "\n")
	for i, s := range ss {
		first, last := "", ""
		if len(s.kids) > 0 {
			first, last = s.kids[0].base, s.kids[len(s.kids)-1].head
		}
		fmt.Fprintf(&b, "%d. %s: all %d children reviewed by agent - factory wf status --goal %s -> commits %s..%s\n",
			i+1, s.task.Key, len(s.kids), r.GoalID, short(first), short(last))
	}
	b.WriteString("</details>\n")
	return b.String()
}

var detailsRE = regexp.MustCompile(`(?is)<details\b.*?</details>`)

func prWordsOutside(body string) int {
	return len(strings.Fields(detailsRE.ReplaceAllString(body, "")))
}

// advanceMerging waits for the factory's own gate. The task done with a merged event starts the finish steps. With no
// pull request yet, an ended builder is resumed (HM-25's rule); a run with no agent, no pull request and no change
// for StaleMergingAfter is reported to the boss once.
func (e *Engine) advanceMerging(r Run) error {
	var status, pr, updated string
	if err := e.Factory.QueryRow(`SELECT status, COALESCE(pr_url, ''), updated FROM tasks WHERE id=?`, r.TaskID).
		Scan(&status, &pr, &updated); err != nil {
		return fmt.Errorf("task %s: %w", r.TaskID, err)
	}
	if status == taskStatusDone {
		if _, err := e.mergeSHA(r.TaskID); err == nil {
			if err := e.setRunState(r.GoalID, RunLinking); err != nil {
				return err
			}
			r.State = RunLinking
			return e.finish(r)
		}
		// done without a merged event: closed by hand (finding 8); say so once, and wait
		if n, err := e.countSince(r.GoalID, "", CauseClosedWithoutMerge); err != nil || n > 0 {
			return err
		}
		subject := fmt.Sprintf("story run %s: its task was closed without a merge", r.GoalID)
		body := fmt.Sprintf("Task %s of run %s is done but the factory recorded no merge (pull request: %s). Nothing in "+
			"the task manager was moved to Done. Decide what happened to the work; the run waits.", r.TaskID, r.GoalID, orDash(pr))
		mail, mailErr := e.mail(r, mailTo, mailDecision, subject, body)
		detail := map[string]any{"task_id": r.TaskID, "task_status": status, "pr": pr, "mail": mail}
		if mailErr != nil {
			detail["mail_error"] = mailErr.Error()
		}
		_, err := e.Record(Incident{GoalID: r.GoalID, Kind: KindEscalation, Cause: CauseClosedWithoutMerge,
			Actor: ActorEngine, Summary: fmt.Sprintf("task %s done without a merged event", r.TaskID), Detail: detail})
		return err
	}
	if pr != "" {
		return nil // the factory's review, CI restarts and merge have it
	}
	kids, err := e.children(r.GoalID)
	if err != nil {
		return err
	}
	if b, found, err := e.agent("", r.TaskID, roleCoder); err != nil {
		return err
	} else if found && ended(b.status) {
		if err := e.checkBuilder(r, kids, 0); err != nil {
			return err
		}
	}
	var live int
	e.Factory.QueryRow("SELECT count(*) FROM agents WHERE task_id=? AND status NOT IN (?,?,?,?)", r.TaskID,
		agentEnded[0], agentEnded[1], agentEnded[2], agentEnded[3]).Scan(&live)
	t, err := time.Parse(tsLayout, updated)
	if err != nil || live > 0 || e.Env.Now().Sub(t) < StaleMergingAfter {
		return nil
	}
	if n, err := e.countSince(r.GoalID, "", CauseStaleMerging); err != nil || n > 0 {
		return err
	}
	subject := fmt.Sprintf("story run %s: no pull request and nobody working", r.GoalID)
	body := fmt.Sprintf("Run %s was told to open its pull request, but task %s has no pull request, no agent and no change "+
		"since %s. Look at the builder, then factory wf resume --goal %s if needed.", r.GoalID, r.TaskID, updated, r.GoalID)
	mail, mailErr := e.mail(r, mailTo, mailDecision, subject, body)
	detail := map[string]any{"task_id": r.TaskID, "task_status": status, "task_updated": updated, "mail": mail}
	if mailErr != nil {
		detail["mail_error"] = mailErr.Error()
	}
	_, err = e.Record(Incident{GoalID: r.GoalID, Kind: KindEscalation, Cause: CauseStaleMerging, Actor: ActorEngine,
		Summary: fmt.Sprintf("merging since %s with no pull request and no agent", updated), Detail: detail})
	return err
}

// mergeSHA is the commit named by the task's latest merged event.
func (e *Engine) mergeSHA(task string) (string, error) {
	var detail string
	err := e.Factory.QueryRow(`SELECT COALESCE(detail, '') FROM events WHERE entity='task' AND entity_id=? AND action=?
		ORDER BY rowid DESC LIMIT 1`, task, eventMerged).Scan(&detail)
	if err != nil {
		return "", err
	}
	m := mergedShaRE.FindStringSubmatch(detail)
	if m == nil {
		return "", fmt.Errorf("merged event of %s names no commit: %q", task, detail)
	}
	return m[1], nil
}

// finish runs the steps after the merge, each once: link commits, comment on the stories, children and stories to
// Done, one mail to the boss. A failed step stays the run's state and is tried again next tick.
func (e *Engine) finish(r Run) error {
	for r.State != RunDone {
		next, err := e.finishStep(r)
		if err != nil {
			return e.finishFailed(r, err)
		}
		if err := e.setRunState(r.GoalID, next); err != nil {
			return err
		}
		r.State = next
	}
	if goalIDRE.MatchString(r.GoalID) { // the goal's skills folder is not needed any more
		return os.RemoveAll(filepath.Join(e.Home, "roles", "plugins", "goals", r.GoalID))
	}
	return nil
}

func (e *Engine) finishStep(r Run) (RunState, error) {
	kids, err := e.children(r.GoalID)
	if err != nil {
		return "", err
	}
	ss, err := e.stories(r, kids)
	if err != nil {
		return "", err
	}
	tr, _ := e.Deps.Tracker()
	var pr string
	e.Factory.QueryRow("SELECT COALESCE(pr_url, '') FROM tasks WHERE id=?", r.TaskID).Scan(&pr)
	switch r.State {
	case RunLinking:
		merge, err := e.mergeSHA(r.TaskID)
		if err != nil {
			return "", err
		}
		full := e.fullMergeSHA(r.TaskID, merge)
		for _, s := range ss {
			for _, c := range s.kids {
				t, err := tr.TaskByKey(c.key)
				if err != nil {
					return "", err
				}
				cs, err := e.commitsOf(r.GoalID, c.key, 0) // stored when the builder set it In Review: no git needed
				if err != nil {
					return "", err
				}
				for _, cm := range cs {
					if err := tr.LinkCommit([]string{t.ID}, cm.sha, cm.subject); err != nil {
						return "", err
					}
				}
			}
			if err := tr.LinkCommit([]string{s.task.ID}, full, "merge of "+pr); err != nil {
				return "", err
			}
		}
		return RunReporting, nil
	case RunReporting:
		merge, _ := e.mergeSHA(r.TaskID)
		for _, s := range ss {
			if len(s.kids) > 0 && s.kids[0].state == string(ChildReported) {
				continue // commented before a later story failed
			}
			if err := tr.Comment(s.task.ID, e.report(r, s, pr, merge)); err != nil {
				return "", err
			}
			for _, c := range s.kids {
				c.state = string(ChildReported)
				if err := e.setChild(r.GoalID, c); err != nil {
					return "", err
				}
			}
		}
		return RunClosing, nil
	case RunClosing:
		for _, s := range ss {
			sts, err := tr.Statuses(s.task.ProjectID)
			if err != nil {
				return "", err
			}
			done := firstDone(sts)
			if done == "" {
				return "", fmt.Errorf("the project of %s has no Done status", s.task.Key)
			}
			for _, c := range s.kids {
				t, err := tr.TaskByKey(c.key)
				if err != nil {
					return "", err
				}
				if err := tr.SetStatus(t.ID, done); err != nil {
					return "", err
				}
				c.state = string(ChildDone)
				if err := e.setChild(r.GoalID, c); err != nil {
					return "", err
				}
			}
			if err := tr.SetStatus(s.task.ID, done); err != nil {
				return "", err
			}
		}
		return RunAnnouncing, nil
	case RunAnnouncing:
		keys := strings.Join(keysOf(ss), ", ")
		if _, err := e.mail(r, mailTo, mailReport, fmt.Sprintf("%s merged and Done", keys),
			fmt.Sprintf("%s merged through %s and Done in the task manager, with every child (run %s).", keys, pr, r.GoalID)); err != nil {
			return "", err
		}
		return RunDone, nil
	}
	return "", fmt.Errorf("run %s: no finish step for state %s", r.GoalID, r.State)
}

// finishFailed records the first failure of a step as a warning (once per step) and leaves the step for next tick.
func (e *Engine) finishFailed(r Run, err error) error {
	summary := fmt.Sprintf("finish step %s failed; retried next tick", r.State)
	var n int
	e.State.QueryRow("SELECT count(*) FROM incidents WHERE goal_id=? AND cause=? AND summary=?", r.GoalID,
		string(CauseTaskosaurError), summary).Scan(&n)
	if n > 0 {
		return nil
	}
	detail := map[string]any{"step": string(r.State), "error": err.Error()}
	var te *tsr.Error
	if errors.As(err, &te) {
		detail["http_status"], detail["route"] = te.Status, te.Method+" "+te.Path
	}
	_, rerr := e.Record(Incident{GoalID: r.GoalID, Kind: KindWarning, Cause: CauseTaskosaurError, Actor: ActorEngine,
		Summary: summary, Detail: detail})
	return rerr
}

func firstDone(sts []tsr.Status) string {
	best, pos := "", 0
	for _, s := range sts {
		if s.Category == tsr.CategoryDone && (best == "" || s.Position < pos) {
			best, pos = s.ID, s.Position
		}
	}
	return best
}

type commit struct{ sha, subject string }

// fullMergeSHA is the merge commit's full hash: the event's own when it has 40 characters, else resolved in the
// project's repository (`projects.repo_path`, which outlives the task's worktree), else the prefix as it is.
func (e *Engine) fullMergeSHA(task, merge string) string {
	if len(merge) == 40 {
		return merge
	}
	var repo, base string
	e.Factory.QueryRow(`SELECT COALESCE(p.repo_path, ''), COALESCE(p.base_branch, '') FROM tasks t JOIN goals g ON
		g.id = t.goal_id LEFT JOIN projects p ON p.id = g.project_id WHERE t.id=?`, task).Scan(&repo, &base)
	if repo == "" {
		return merge
	}
	if base == "" {
		base = defaultBranch
	}
	g := e.Deps.Git
	g.Run(repo, "fetch", "-q", "origin", "+refs/heads/"+base+":refs/remotes/origin/"+base) // best effort
	if f, err := g.Run(repo, "rev-parse", "--verify", merge+"^{commit}"); err == nil && len(f) == 40 {
		return f
	}
	return merge
}

// keyIn reports whether a commit subject names key as a whole key (HM-1 is not in HM-12).
func keyIn(subject, key string) bool {
	re := regexp.MustCompile(`(?i)(^|[^A-Za-z0-9-])` + regexp.QuoteMeta(key) + `($|[^0-9])`)
	return re.MatchString(subject)
}

// report is the closing comment on a story.
func (e *Engine) report(r Run, s storyInfo, pr, merge string) string {
	var created string
	e.State.QueryRow("SELECT created FROM runs WHERE goal_id=?", r.GoalID).Scan(&created)
	elapsed := "unknown"
	if t, err := time.Parse(tsLayout, created); err == nil {
		elapsed = e.Env.Now().Sub(t).Round(time.Minute).String()
	}
	var b strings.Builder
	fmt.Fprintf(&b, "Story run %s merged: pull request %s, merge commit %s. Elapsed since the run started: %s.\n\n", r.GoalID, pr, merge, elapsed)
	b.WriteString("Fix rounds per child:\n")
	for _, c := range s.kids {
		fmt.Fprintf(&b, "- %s: %d\n", c.key, c.rounds)
	}
	return b.String()
}

type storyCount struct {
	key         string
	done, total int
}

// storyCounts is, per story in run order, how many of its children passed review (or went further).
func storyCounts(kids []childRow) []storyCount {
	var out []storyCount
	for _, c := range kids {
		if len(out) == 0 || out[len(out)-1].key != c.story {
			out = append(out, storyCount{key: c.story})
		}
		s := &out[len(out)-1]
		s.total++
		if c.state == string(ChildReviewed) || c.state == string(ChildReported) || c.state == string(ChildDone) {
			s.done++
		}
	}
	return out
}

// prURL is the factory task's pull request, for status ("" when unknown).
func prURL(fdb *sql.DB, task string) string {
	var pr string
	if fdb != nil {
		fdb.QueryRow("SELECT COALESCE(pr_url, '') FROM tasks WHERE id=?", task).Scan(&pr)
	}
	return pr
}
