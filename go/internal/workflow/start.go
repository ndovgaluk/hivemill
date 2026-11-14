package workflow

import (
	"database/sql"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"factory/go/internal/tsr"
)

// The "enriched" rule (owner decision of 2026-11-13, refined on HM-24 2026-11-14): a child has a description, an
// "Acceptance criteria" section with at least one list item inside it, and a tests field ("none: <why>" counts).
const (
	acceptanceHeading = "## acceptance criteria"
	missDescription   = "description"
	missAcceptance    = "acceptance criteria"
	missTests         = "tests"
)

var (
	listItemRE    = regexp.MustCompile(`^\s*(-|\d+\.)\s+\S`)
	placeholderRE = regexp.MustCompile(`\{([a-z_]+)\}`)
)

// Template files of the story run (HM-31); loaded, never reworded.
const (
	kickoffTemplate  = "workflows/prompts/builder-kickoff.md"
	goalPluginSource = "workflows/goal-plugin"
)

// Kickoff placeholders.
const (
	phAgent      = "agent"
	phGoal       = "goal"
	phTask       = "task"
	phBranch     = "branch"
	phStories    = "stories"
	phFirstStory = "first_story"
)

// Fixed parts of what start creates.
const (
	defaultOrg       = "claude" // scout/orgs.py DEFAULT_ORG
	cfgOrgPrefix     = "org_prefix_default"
	builderPrefix    = "builder-"
	branchPrefix     = "factory/"
	roleCoderTask    = "coder"
	taskSpecTemplate = "Story run of %s. The work is defined in the task manager (factory wf tsr show and children) " +
		"and in the skill story-run:story-builder of this goal; build the children in order, one commit per child, " +
		"no pull request until the engine's mail."
	taskAcceptanceTemplate = "every child of %s is In Review in Taskosaur with its commits on this branch"
)

// acceptanceSection returns the text of the description's "## Acceptance criteria" section and whether it holds a
// list item.
func acceptanceSection(desc string) (string, bool) {
	lines := strings.Split(desc, "\n")
	for i, l := range lines {
		if strings.TrimSuffix(strings.ToLower(strings.TrimSpace(l)), ":") != acceptanceHeading {
			continue
		}
		var body []string
		item := false
		for _, m := range lines[i+1:] {
			if strings.HasPrefix(strings.TrimSpace(m), "## ") {
				break
			}
			body = append(body, m)
			item = item || listItemRE.MatchString(m)
		}
		return strings.TrimSpace(strings.Join(body, "\n")), item
	}
	return "", false
}

// missingFields lists what keeps a task from being enriched, in the rule's words.
func missingFields(t tsr.Task) []string {
	var miss []string
	if strings.TrimSpace(t.Description) == "" {
		miss = append(miss, missDescription)
	}
	if _, ok := acceptanceSection(t.Description); !ok {
		miss = append(miss, missAcceptance)
	}
	if e := strings.TrimSpace(t.E2ETests); e == "" {
		miss = append(miss, missTests)
	}
	return miss
}

// fill replaces every {name} of tmpl from values in one pass. An unknown or unfilled placeholder is an error: a
// kickoff with a literal {name} in it must never reach an agent. maybeEmpty names the placeholders that may be "".
func fill(name, tmpl string, values map[string]string, maybeEmpty ...string) (string, error) {
	var bad []string
	out := placeholderRE.ReplaceAllStringFunc(tmpl, func(m string) string {
		k := m[1 : len(m)-1]
		v, ok := values[k]
		if !ok || (v == "" && !contains(maybeEmpty, k)) {
			bad = append(bad, m)
			return m
		}
		return v
	})
	if len(bad) > 0 {
		return "", fmt.Errorf("%s: unknown or unfilled placeholder(s) %s", name, strings.Join(bad, " "))
	}
	return out, nil
}

// copyPlugin copies the goal plugin template into dst (which must not exist): directories 0755, files 0644, no
// symlinks and no executables.
func copyPlugin(src, dst string) error {
	if _, err := os.Lstat(dst); err == nil {
		return fmt.Errorf("%s exists already", dst)
	}
	return filepath.WalkDir(src, func(p string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		rel, _ := filepath.Rel(src, p)
		to := filepath.Join(dst, rel)
		switch {
		case d.IsDir():
			return os.MkdirAll(to, 0o755)
		case d.Type().IsRegular():
			in, err := os.Open(p)
			if err != nil {
				return err
			}
			defer in.Close()
			out, err := os.OpenFile(to, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o644)
			if err != nil {
				return err
			}
			if _, err := io.Copy(out, in); err != nil {
				out.Close()
				return err
			}
			return out.Close()
		default:
			return fmt.Errorf("%s: only folders and regular files may be in the goal plugin", p)
		}
	})
}

// startPlan is everything start needs, gathered before anything is created.
type startPlan struct {
	stories  []tsr.Task
	children []planChild
	kickoff  string // template text
	workflow string
	chosen   bool // the workflow came from Choose, not --workflow
	project  string
}

type planChild struct {
	story string
	task  tsr.Task
}

// usageError ends a command with exit 2 (bad input, refused before anything was made).
type usageError struct{ msg string }

func (u usageError) Error() string { return u.msg }

// planStart reads the stories and their children and checks them and the templates. It creates nothing.
func (e *Engine) planStart(keys []string, workflow, project string) (*startPlan, error) {
	seen := map[string]bool{}
	for _, k := range keys {
		if seen[strings.ToUpper(k)] {
			return nil, usageError{fmt.Sprintf("story %s is listed twice", k)}
		}
		seen[strings.ToUpper(k)] = true
		var goal, state string
		err := e.State.QueryRow(`SELECT r.goal_id, r.state FROM run_stories s JOIN runs r ON r.goal_id = s.goal_id
			WHERE s.story_key = ? AND r.state != ? ORDER BY r.created DESC LIMIT 1`, k, string(RunDone)).Scan(&goal, &state)
		if err == nil { // a failed run counts as unfinished: its goal is still open for the owner
			return nil, usageError{fmt.Sprintf("story %s already has run %s (state %s); see factory wf status --goal %s "+
				"and factory wf incidents --goal %s", k, goal, state, goal, goal)}
		}
		if !errors.Is(err, sql.ErrNoRows) {
			return nil, err
		}
	}
	tr, err := e.Deps.Tracker()
	if err != nil {
		return nil, err
	}
	p := &startPlan{workflow: workflow, project: project}
	var refused []string
	var rated []planStory
	for _, k := range keys {
		story, err := tr.TaskByKey(k)
		if err != nil {
			return nil, err
		}
		kids, err := tr.Children(story)
		if err != nil {
			return nil, err
		}
		// Taskosaur's list rows carry no description and no tests field: read each child in full (first real run, HM-39)
		for i := range kids {
			if kids[i], err = tr.TaskByKey(kids[i].Key); err != nil {
				return nil, err
			}
		}
		if len(p.stories) > 0 && story.ProjectID != p.stories[0].ProjectID {
			return nil, usageError{fmt.Sprintf("story %s is in another Taskosaur project than %s; a batch takes one project",
				k, p.stories[0].Key)}
		}
		rated = append(rated, planStory{key: story.Key, size: story.Size, complexity: story.Complexity, hasChildren: len(kids) > 0})
		if len(kids) == 0 {
			kids = []tsr.Task{story} // a task without children is a story with one child: itself
		} else if len(keys) > 1 { // a batch item must be prepared itself too (owner decision of 2026-11-14, HM-33)
			if miss := missingFields(story); len(miss) > 0 {
				refused = append(refused, fmt.Sprintf("%s: missing %s", story.Key, strings.Join(miss, ", ")))
			}
		}
		p.stories = append(p.stories, story)
		for _, c := range kids {
			p.children = append(p.children, planChild{story: story.Key, task: c})
			if miss := missingFields(c); len(miss) > 0 {
				refused = append(refused, fmt.Sprintf("%s: missing %s", c.Key, strings.Join(miss, ", ")))
			}
		}
	}
	if len(refused) > 0 {
		return nil, usageError{"not prepared for a story run (each child needs a description, a \"## Acceptance " +
			"criteria\" section with list items, and its tests field; a project in Simple tasks mode cannot pass):\n  " +
			strings.Join(refused, "\n  ")}
	}
	if p.workflow == "" {
		if p.workflow, err = chooseFor(rated); err != nil {
			return nil, err
		}
		p.chosen = true
	}
	raw, err := os.ReadFile(filepath.Join(e.Deps.SrcDir, kickoffTemplate))
	if err != nil {
		return nil, fmt.Errorf("kickoff template: %w", err)
	}
	p.kickoff = string(raw)
	probe := map[string]string{phAgent: "x", phGoal: "x", phTask: "x", phBranch: "x", phStories: "x", phFirstStory: "x"}
	if _, err := fill(kickoffTemplate, p.kickoff, probe); err != nil {
		return nil, err
	}
	if st, err := os.Stat(filepath.Join(e.Deps.SrcDir, goalPluginSource)); err != nil || !st.IsDir() {
		return nil, fmt.Errorf("goal plugin template %s is missing", goalPluginSource)
	}
	return p, nil
}

// lastLine is the last non-empty line of a command's output (factory task add may print a warning first).
func lastLine(s string) string {
	lines := strings.Split(strings.TrimSpace(s), "\n")
	return strings.TrimSpace(lines[len(lines)-1])
}

var (
	goalIDRE = regexp.MustCompile(`^G-\d+$`)
	taskIDRE = regexp.MustCompile(`^T-\d+$`)
)

// start runs the plan. Before the goal exists nothing is made; after it, every failure leaves the run in state
// failed with an incident naming the step, and the goal stays for the owner to close.
func (e *Engine) start(p *startPlan, w io.Writer) (string, error) {
	first := p.stories[0]
	keys := make([]string, len(p.stories))
	for i, s := range p.stories {
		keys[i] = s.Key
	}
	success, _ := acceptanceSection(first.Description)
	if success == "" {
		success = fmt.Sprintf(taskAcceptanceTemplate, first.Key)
	}
	args := []string{"goal", "new", "--title", fmt.Sprintf("%s (%s)", first.Title, strings.Join(keys, ", ")),
		"--intent", "-", "--success", success}
	if p.project != "" {
		args = append(args, "--project", p.project)
	}
	out, err := e.Deps.Factory.Run(first.Description, args...)
	if err != nil {
		return "", err
	}
	goal := lastLine(out)
	if !goalIDRE.MatchString(goal) {
		return "", fmt.Errorf("factory goal new printed %q, not a goal id", goal)
	}
	now := e.Env.Now().Format(tsLayout)
	if err := e.insertRun(goal, keys, p, now); err != nil { // finding 9: the goal exists, the run does not
		e.Record(Incident{GoalID: goal, Kind: KindFailure, Cause: CauseStartFailed, Actor: ActorEngine,
			Summary: "start stopped at record run: " + firstLine(err.Error()),
			Detail:  map[string]any{"step": "record run", "error": err.Error(), "stories": keys}})
		return goal, fmt.Errorf("goal %s was created but its run could not be recorded (%v); close the goal "+
			"(factory goal status %s cancelled) before starting again", goal, err, goal)
	}
	origin := eventWorkflowGiven
	if p.chosen {
		origin = eventWorkflowChosen
	}
	if err := e.Env.EventAs(e.Factory, ActorEngine, EventEntity, goal, origin, p.workflow); err != nil {
		return goal, err
	}
	fail := func(step string, cause Cause, err error) (string, error) {
		detail := map[string]any{"step": step, "error": err.Error(), "stories": keys}
		var ce *CmdError
		if errors.As(err, &ce) {
			detail["command"], detail["exit_code"], detail["stderr"] = ce.Cmd, ce.ExitCode(), ce.Stderr
		}
		e.setRunState(goal, RunFailed)
		e.Record(Incident{GoalID: goal, Kind: KindFailure, Cause: cause, Actor: ActorEngine,
			Summary: "start stopped at " + step + ": " + firstLine(err.Error()), Detail: detail})
		return goal, fmt.Errorf("run %s failed at %s: %w", goal, step, err)
	}
	out, err = e.Deps.Factory.Run("", "task", "add", "--goal", goal, "--role", roleCoderTask,
		"--title", fmt.Sprintf("Build %s", strings.Join(keys, ", ")),
		"--spec", fmt.Sprintf(taskSpecTemplate, strings.Join(keys, ", ")),
		"--acceptance", fmt.Sprintf(taskAcceptanceTemplate, strings.Join(keys, ", ")))
	task := lastLine(out)
	if err == nil && !taskIDRE.MatchString(task) {
		err = fmt.Errorf("factory task add printed %q, not a task id", task)
	}
	if err != nil {
		return fail("task add", CauseStartFailed, err)
	}
	if _, err := e.State.Exec("UPDATE runs SET task_id=?, updated=? WHERE goal_id=?", task, now, goal); err != nil {
		return fail("record task", CauseStartFailed, err)
	}
	agent, err := e.builderName(goal, task)
	if err != nil {
		return fail("builder name", CauseStartFailed, err)
	}
	if err := copyPlugin(filepath.Join(e.Deps.SrcDir, goalPluginSource),
		filepath.Join(e.Home, "roles", "plugins", "goals", goal)); err != nil {
		return fail("goal plugin", CauseStartFailed, err)
	}
	kick, err := fill(kickoffTemplate, p.kickoff, map[string]string{phAgent: agent, phGoal: goal, phTask: task,
		phBranch: branchPrefix + strings.ToLower(task), phStories: strings.Join(keys, ", "), phFirstStory: keys[0]})
	if err != nil {
		return fail("kickoff", CauseStartFailed, err)
	}
	if _, err := e.Deps.Factory.Run(kick, "spawn", "coder", "--goal", goal, "--task", task, "--name", agent,
		"--prompt", "-"); err != nil {
		return fail("spawn", CauseSpawnRefused, err)
	}
	if err := e.setRunState(goal, RunBuilding); err != nil {
		return goal, err
	}
	fmt.Fprintf(w, "run %s: task %s, builder %s, %d children of %s\n", goal, task, agent, len(p.children),
		strings.Join(keys, ", "))
	return goal, nil
}

func (e *Engine) insertRun(goal string, keys []string, p *startPlan, now string) error {
	tx, err := e.State.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()
	if _, err := tx.Exec(`INSERT INTO runs(goal_id, story_key, workflow, state, created, updated) VALUES(?,?,?,?,?,?)`,
		goal, keys[0], p.workflow, string(RunStarting), now, now); err != nil {
		return err
	}
	for i, k := range keys {
		if _, err := tx.Exec(`INSERT INTO run_stories VALUES(?,?,?)`, goal, k, i+1); err != nil {
			return err
		}
	}
	for i, c := range p.children {
		if _, err := tx.Exec(`INSERT INTO children(goal_id, story_key, child_key, position, state, updated)
			VALUES(?,?,?,?,?,?)`, goal, c.story, c.task.Key, i+1, string(ChildTodo), now); err != nil {
			return err
		}
	}
	return tx.Commit()
}

func (e *Engine) setRunState(goal string, s RunState) error {
	_, err := e.State.Exec("UPDATE runs SET state=?, updated=? WHERE goal_id=?", string(s), e.Env.Now().Format(tsLayout), goal)
	return err
}

// builderName is the name of the run's builder.
func (e *Engine) builderName(goal, task string) (string, error) {
	return e.agentName(goal, builderPrefix+strings.ToLower(task))
}

// agentName is spawn's naming rule (bin/factory_cli.py oname): <org>-<base>, except in the default org while config
// org_prefix_default is not 1.
func (e *Engine) agentName(goal, base string) (string, error) {
	var org string
	if err := e.Factory.QueryRow("SELECT org FROM goals WHERE id=?", goal).Scan(&org); err != nil {
		return "", err
	}
	var prefixDefault string
	if err := e.Factory.QueryRow("SELECT value FROM config WHERE key=?", cfgOrgPrefix).Scan(&prefixDefault); err != nil &&
		!errors.Is(err, sql.ErrNoRows) {
		return "", err
	}
	if org == defaultOrg && strings.TrimSpace(prefixDefault) != "1" {
		return base, nil
	}
	return org + "-" + base, nil
}
