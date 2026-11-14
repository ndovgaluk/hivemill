package workflow

import (
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"

	"factory/go/internal/identity"
	"factory/go/internal/tsr"
)

const tsrUsage = "usage: factory wf tsr {show KEY | children KEY | comment KEY --file PATH | status KEY in_progress|in_review" +
	" | attachments KEY | attachment ID --out PATH}"

// Target statuses of `tsr status`.
const (
	statusInProgress = "in_progress"
	statusInReview   = "in_review"
)

// Who may call which `tsr` command (owner decision of 2026-11-14, DVDG-565 question 3). Marks, Done and commit links
// have no command: only the engine sets them.
var (
	tsrReaders    = []string{roleCoder, roleReviewer, roleQA, roleStaffEngineer, roleBoss}
	tsrCommenters = []string{roleCoder, roleReviewer, roleQA, roleStaffEngineer}
	tsrMovers     = []string{roleCoder}
)

// tsrConfigDir holds tsr-url and tsr-token.
func tsrConfigDir(env identity.Env) string {
	return filepath.Join(env.UserHome(), ".config", "factory")
}

func tsrMain(args []string, env identity.Env, stdout, stderr io.Writer) int {
	fail := func(code int, err error) int {
		fmt.Fprintf(stderr, "factory wf tsr: %v\n", err)
		return code
	}
	usage := func() int { fmt.Fprintln(stderr, tsrUsage); return exitUsage }
	if len(args) < 2 {
		return usage()
	}
	cmd, arg, rest := args[0], args[1], args[2:]
	allowed := tsrReaders
	switch cmd {
	case "comment":
		allowed = tsrCommenters
	case "status":
		allowed = tsrMovers
	case "show", "children", "attachments", "attachment":
	default:
		return usage()
	}
	fs := flag.NewFlagSet("factory wf tsr "+cmd, flag.ContinueOnError)
	fs.SetOutput(stderr)
	var file, out *string
	switch cmd {
	case "comment":
		file = fs.String("file", "", "markdown file with the comment")
	case "attachment":
		out = fs.String("out", "", "where to save the file (inside the current directory or the scratch directory)")
	}
	var pos []string
	if cmd == "status" && len(rest) > 0 {
		pos, rest = rest[:1], rest[1:]
	}
	if err := fs.Parse(rest); err != nil || fs.NArg() > 0 || (cmd == "status" && len(pos) != 1) ||
		(file != nil && *file == "") || (out != nil && *out == "") {
		return usage()
	}
	who, code, err := requireRole(env, env.Home(), allowed...)
	if err != nil {
		return fail(code, err)
	}
	// Scope (HM-35 finding 3): the token reaches every task, so any caller but the owner and the boss is held to the
	// stories and children of its own run; status is only for the run's builder.
	var e *Engine
	var run Run
	var inRun map[string]bool
	if who != roleOwner {
		eng, closeAll, err := open(env, env.Home())
		if err != nil {
			return fail(exitErr, err)
		}
		defer closeAll()
		e = eng
		role := e.roleOf(who)
		if role != roleBoss || cmd == "status" {
			if cmd == "status" {
				role = roleCoder
			}
			if run, err = e.runOfAgent(who, role); err != nil {
				return fail(exitRefuse, fmt.Errorf("%s is not part of your story run (you have none)", arg))
			}
			if inRun, err = e.runKeys(run.GoalID); err != nil {
				return fail(exitErr, err)
			}
			if cmd != "attachment" && !inRun[strings.ToUpper(arg)] {
				return fail(exitRefuse, fmt.Errorf("%s is not part of your story run", arg))
			}
		}
	} else if cmd == "status" {
		return fail(exitRefuse, errors.New("tsr status is for the builder of a story run"))
	}
	var markdown string
	if file != nil {
		b, err := os.ReadFile(*file)
		if err != nil {
			return fail(exitUsage, err)
		}
		if strings.TrimSpace(string(b)) == "" {
			return fail(exitUsage, fmt.Errorf("%s is empty", *file))
		}
		markdown = fmt.Sprintf("factory agent %s:\n\n%s", who, b)
	}
	var target string
	if out != nil {
		if target, err = outPath(*out); err != nil {
			return fail(exitUsage, err)
		}
	}
	if cmd == "status" {
		if err := e.builderStatus(run, arg, pos[0], stdout); err != nil {
			var nr errNotReady
			var ue usageErr
			switch {
			case errors.As(err, &nr), errors.As(err, &ue):
				return fail(exitUsage, err)
			}
			return fail(exitErr, err)
		}
		return exitOK
	}
	c, err := tsr.Load(tsrConfigDir(env))
	if err != nil {
		return fail(exitErr, err)
	}
	if cmd == "attachment" {
		if inRun != nil {
			ok, err := attachmentInRun(c, arg, inRun)
			if err != nil {
				return fail(exitErr, err)
			}
			if !ok {
				return fail(exitRefuse, fmt.Errorf("attachment %s is not part of your story run", arg))
			}
		}
		if err := saveAttachment(c, arg, target); err != nil {
			return fail(exitErr, err)
		}
		fmt.Fprintln(stdout, target)
		return exitOK
	}
	t, err := c.TaskByKey(arg)
	if err != nil {
		return fail(exitErr, err)
	}
	switch cmd {
	case "show":
		err = printTask(c, t, stdout)
	case "children":
		var kids []tsr.Task
		if kids, err = c.Children(t); err == nil {
			for _, k := range kids {
				fmt.Fprintf(stdout, "%s\t%s\t%s\n", k.Key, k.Status.Name, k.Title)
			}
		}
	case "attachments":
		err = printAttachments(c, t, stdout)
	case "comment":
		if err = c.Comment(t.ID, markdown); err == nil {
			fmt.Fprintf(stdout, "commented on %s\n", t.Key)
		}
	}
	if err != nil {
		var ue usageErr
		if errors.As(err, &ue) {
			return fail(exitUsage, err)
		}
		return fail(exitErr, err)
	}
	return exitOK
}

type usageErr struct{ msg string }

func (u usageErr) Error() string { return u.msg }

func printTask(c *tsr.Client, t tsr.Task, w io.Writer) error {
	fmt.Fprintf(w, "%s %s\n", t.Key, t.Title)
	fmt.Fprintf(w, "type %s · status %s · size %s · complexity %d\n", t.Type, t.Status.Name, orDash(t.Size), t.Complexity)
	fmt.Fprintf(w, "\n## Description (with the acceptance criteria)\n\n%s\n", orDash(t.Description))
	fmt.Fprintf(w, "\n## E2E tests\n\n%s\n", orDash(t.E2ETests))
	atts, err := c.Attachments(t.ID)
	if err != nil {
		return err
	}
	if len(atts) > 0 {
		fmt.Fprintf(w, "\n## Attachments (factory wf tsr attachment ID --out PATH)\n\n")
		writeAttachments(atts, w)
	}
	return nil
}

func printAttachments(c *tsr.Client, t tsr.Task, w io.Writer) error {
	atts, err := c.Attachments(t.ID)
	if err == nil {
		writeAttachments(atts, w)
	}
	return err
}

func writeAttachments(atts []tsr.Attachment, w io.Writer) {
	for _, a := range atts {
		fmt.Fprintf(w, "%s\t%d\t%s\t%s\n", a.ID, a.FileSize, a.MimeType, a.FileName)
	}
}

func orDash(s string) string {
	if strings.TrimSpace(s) == "" {
		return "-"
	}
	return s
}

// roleOf is the factory role of an agent ("unknown" when it has no row).
func (e *Engine) roleOf(who string) string {
	r := identity.Unknown
	e.Factory.QueryRow("SELECT role FROM agents WHERE name=?", who).Scan(&r)
	return r
}

// runKeys is every story and child key of a run, upper-cased.
func (e *Engine) runKeys(goal string) (map[string]bool, error) {
	rows, err := e.State.Query(`SELECT story_key FROM run_stories WHERE goal_id=?1 UNION
		SELECT child_key FROM children WHERE goal_id=?1`, goal)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	keys := map[string]bool{}
	for rows.Next() {
		var k string
		if err := rows.Scan(&k); err != nil {
			return nil, err
		}
		keys[strings.ToUpper(k)] = true
	}
	return keys, rows.Err()
}

// attachmentInRun reports whether an attachment belongs to a story or child of the run.
func attachmentInRun(c *tsr.Client, id string, keys map[string]bool) (bool, error) {
	a, err := c.AttachmentByID(id)
	if err != nil {
		return false, err
	}
	for k := range keys {
		t, err := c.TaskByKey(k)
		if err != nil {
			return false, err
		}
		if t.ID == a.TaskID {
			return true, nil
		}
	}
	return false, nil
}

// builderStatus is `tsr status` for the run's builder: in_review first records the child's commits (the worktree must
// be clean and pushed, a commit must name the child), then moves the task (HM-35 finding 1).
func (e *Engine) builderStatus(r Run, key, kind string, w io.Writer) error {
	if kind != statusInProgress && kind != statusInReview {
		return usageErr{fmt.Sprintf("status must be %s or %s, not %q", statusInProgress, statusInReview, kind)}
	}
	kids, err := e.children(r.GoalID)
	if err != nil {
		return err
	}
	var child *childRow
	for i := range kids {
		if strings.EqualFold(kids[i].key, key) {
			child = &kids[i]
		}
	}
	if child == nil {
		return usageErr{fmt.Sprintf("%s is a story of the run, not a child; set its children", key)}
	}
	d, err := e.deps()
	if err != nil {
		return err
	}
	if kind == statusInReview {
		if err := e.recordInReview(r, *child); err != nil {
			return err
		}
	}
	tr, err := d.Tracker()
	if err != nil {
		return err
	}
	t, err := tr.TaskByKey(child.key)
	if err != nil {
		return err
	}
	return moveTask(tr, t, kind, w)
}

// statusSetter is the part of the client moveTask needs.
type statusSetter interface {
	Statuses(projectID string) ([]tsr.Status, error)
	SetStatus(taskID, statusID string) error
}

// moveTask sets the first status (by position) of the wanted kind: in_progress is the first IN_PROGRESS status with
// no user action, in_review the first status whose user action is REVIEW.
func moveTask(c statusSetter, t tsr.Task, kind string, w io.Writer) error {
	if kind != statusInProgress && kind != statusInReview {
		return usageErr{fmt.Sprintf("status must be %s or %s, not %q", statusInProgress, statusInReview, kind)}
	}
	sts, err := c.Statuses(t.ProjectID)
	if err != nil {
		return err
	}
	var best *tsr.Status
	for i := range sts {
		s := &sts[i]
		review := s.UserAction != nil && *s.UserAction == tsr.UserActionReview
		ok := (kind == statusInReview && review) || (kind == statusInProgress && s.Category == tsr.CategoryInProgress && s.UserAction == nil)
		if ok && (best == nil || s.Position < best.Position) {
			best = s
		}
	}
	if best == nil {
		return fmt.Errorf("the project of %s has no %s status", t.Key, kind)
	}
	if err := c.SetStatus(t.ID, best.ID); err != nil {
		return err
	}
	fmt.Fprintf(w, "%s -> %s\n", t.Key, best.Name)
	return nil
}

// outPath accepts a path inside the current directory tree or the caller's scratch directory
// (<tmp>/claude-<uid>), after resolving symlinks of its parent; the file itself must not exist yet.
func outPath(p string) (string, error) {
	abs, err := filepath.Abs(p)
	if err != nil {
		return "", err
	}
	dir, err := filepath.EvalSymlinks(filepath.Dir(abs))
	if err != nil {
		return "", fmt.Errorf("--out: folder of %s: %v", p, err)
	}
	target := filepath.Join(dir, filepath.Base(abs))
	var roots []string
	if wd, err := os.Getwd(); err == nil {
		roots = append(roots, wd)
	}
	roots = append(roots, filepath.Join(os.TempDir(), fmt.Sprintf("claude-%d", os.Getuid())))
	inside := false
	for _, r := range roots {
		if rr, err := filepath.EvalSymlinks(r); err == nil {
			r = rr
		}
		if rel, err := filepath.Rel(r, target); err == nil && rel != "." && !strings.HasPrefix(rel, "..") {
			inside = true
		}
	}
	if !inside {
		return "", fmt.Errorf("--out %s: must be inside the current directory or %s", p, roots[len(roots)-1])
	}
	if _, err := os.Lstat(target); err == nil {
		return "", fmt.Errorf("--out %s: exists; not overwritten", p)
	}
	return target, nil
}

// saveAttachment downloads into a temp file next to target (mode 0600) and links it into place only when complete,
// so a failed or oversized download leaves nothing behind and an existing file is never replaced.
func saveAttachment(c *tsr.Client, id, target string) error {
	tmp, err := os.CreateTemp(filepath.Dir(target), ".tsr-download-*")
	if err != nil {
		return err
	}
	defer os.Remove(tmp.Name())
	_, derr := c.Download(id, tmp)
	if cerr := tmp.Close(); derr == nil {
		derr = cerr
	}
	if derr != nil {
		return derr
	}
	if err := os.Link(tmp.Name(), target); err != nil {
		return fmt.Errorf("--out %s: %v", target, err)
	}
	return nil
}
