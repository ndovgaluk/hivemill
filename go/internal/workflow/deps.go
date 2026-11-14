package workflow

import (
	"bytes"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"

	"factory/go/internal/identity"
	"factory/go/internal/tsr"
)

// Tracker is the part of the Taskosaur client the engine's steps use (tsr.Client implements it; tests stub it).
type Tracker interface {
	TaskByKey(key string) (tsr.Task, error)
	Children(task tsr.Task) ([]tsr.Task, error)
	Comment(taskID, markdown string) error
	AgentCheck(taskID string, kind tsr.CheckKind, result *tsr.CheckResult, agentName, ref string) error
	Statuses(projectID string) ([]tsr.Status, error)
	SetStatus(taskID, statusID string) error
	LinkCommit(taskIDs []string, sha, message string) error
}

// Factory runs the factory CLI (bin/factory) as the owner; stdin may be "".
type Factory interface {
	Run(stdin string, args ...string) (string, error)
}

// Git runs git in a directory.
type Git interface {
	Run(dir string, args ...string) (string, error)
}

// Tests starts a command (the affected tests of a branch, HM-54) detached in dir and returns at once; the command's
// output goes to logPath and, when it ends, its exit code to rcPath. The engine's tick holds a lock and never waits for it.
type Tests interface {
	Start(dir, logPath, rcPath string, argv []string) error
}

// Deps are the outside systems of the engine's steps, injected so tests run the whole path with stubs.
type Deps struct {
	Tracker func() (Tracker, error) // lazy: a home with no runs never needs the token files
	Factory Factory
	Git     Git
	Tests   Tests
	SrcDir  string // the checkout holding workflows/ (the templates)
}

// envInvocation is set by systemd for a unit's processes: the tick's engine runs in a transient unit.
const envInvocation = "INVOCATION_ID"

// detachedScript runs "$@", writes its output to $LOG and then its exit code to $RC (through a temporary name, so a
// reader never sees half a file).
const detachedScript = `"$@" > "$LOG" 2>&1; echo $? > "$RC.tmp" && mv "$RC.tmp" "$RC"`

type cliTests struct{ home string }

func (t cliTests) Start(dir, logPath, rcPath string, argv []string) error {
	env := append(ownerEnv(t.home), "LOG="+logPath, "RC="+rcPath)
	args := append([]string{"-c", detachedScript, "affected"}, argv...)
	if os.Getenv(envInvocation) != "" {
		// a child would be killed with the tick's unit (KillMode=control-group): give it its own transient unit, as
		// tick_gate does for gate runners; a unit gets the manager's environment, so pass what the tests need
		unit := []string{"--user", "--collect", "--quiet", "--working-directory=" + dir}
		for _, kv := range env {
			k := kv[:strings.IndexByte(kv+"=", '=')]
			if k == "PATH" || k == "HOME" || k == "FACTORY_HOME" || k == "LOG" || k == "RC" {
				unit = append(unit, "--setenv="+kv)
			}
		}
		return exec.Command("systemd-run", append(append(unit, "--", "bash"), args...)...).Run()
	}
	cmd := exec.Command("bash", args...)
	cmd.Dir, cmd.Env = dir, env
	cmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true} // its own session: it outlives this process
	if err := cmd.Start(); err != nil {
		return err
	}
	return cmd.Process.Release()
}

// EnvFactoryCLI names bin/factory; the Python seams (cmd_wf, tick_workflow) set it.
const EnvFactoryCLI = "FACTORY_CLI"

// newDeps builds the real dependencies; tests replace it.
var newDeps = func(env identity.Env) (*Deps, error) {
	bin := env.Getenv(EnvFactoryCLI)
	if bin == "" {
		return nil, fmt.Errorf("%s is not set: run the engine through `factory wf`", EnvFactoryCLI)
	}
	var cached Tracker
	return &Deps{
		Tracker: func() (Tracker, error) {
			if cached == nil {
				c, err := tsr.Load(tsrConfigDir(env))
				if err != nil {
					return nil, err
				}
				cached = c
			}
			return cached, nil
		},
		Factory: cliFactory{bin: bin, home: env.Home()},
		Git:     cliGit{home: env.Home()},
		Tests:   cliTests{home: env.Home()},
		SrcDir:  filepath.Dir(filepath.Dir(bin)),
	}, nil
}

// ownerEnv is this process's environment without any agent identity, so the factory CLI sees the owner. The engine
// checks its own caller (boss, owner, or the run's builder) before it acts; its factory steps then run with the
// owner's rights, as the tick does.
func ownerEnv(home string) []string {
	var out []string
	for _, kv := range os.Environ() {
		k := kv[:strings.IndexByte(kv+"=", '=')]
		switch k {
		case "FACTORY_AGENT", "FACTORY_ROLE", "CLAUDECODE", "HERDR_PANE_ID", "FACTORY_HOME":
			continue
		}
		if strings.HasPrefix(k, "GIT_") {
			continue
		}
		out = append(out, kv)
	}
	return append(out, "FACTORY_HOME="+home)
}

type cliFactory struct{ bin, home string }

func (f cliFactory) Run(stdin string, args ...string) (string, error) {
	cmd := exec.Command(f.bin, args...)
	cmd.Env = ownerEnv(f.home)
	cmd.Stdin = strings.NewReader(stdin)
	var out, errb bytes.Buffer
	cmd.Stdout, cmd.Stderr = &out, &errb
	if err := cmd.Run(); err != nil {
		return out.String(), &CmdError{Cmd: "factory " + args[0], Err: err, Stderr: errb.String()}
	}
	return out.String(), nil
}

type cliGit struct{ home string }

func (g cliGit) Run(dir string, args ...string) (string, error) {
	cmd := exec.Command("git", append([]string{"-C", dir}, args...)...)
	cmd.Env = ownerEnv(g.home)
	var out, errb bytes.Buffer
	cmd.Stdout, cmd.Stderr = &out, &errb
	if err := cmd.Run(); err != nil {
		return out.String(), &CmdError{Cmd: "git " + args[0], Err: err, Stderr: errb.String()}
	}
	return strings.TrimSpace(out.String()), nil
}

// CmdError is a failed factory or git call, with what an incident needs.
type CmdError struct {
	Cmd    string
	Err    error
	Stderr string
}

func (e *CmdError) Error() string {
	last := strings.TrimSpace(e.Stderr)
	if i := strings.LastIndexByte(last, '\n'); i >= 0 {
		last = last[i+1:]
	}
	return fmt.Sprintf("%s: %v: %s", e.Cmd, e.Err, last)
}

// ExitCode is the command's exit code, or -1.
func (e *CmdError) ExitCode() int {
	var ee *exec.ExitError
	if errors.As(e.Err, &ee) {
		return ee.ExitCode()
	}
	return -1
}
