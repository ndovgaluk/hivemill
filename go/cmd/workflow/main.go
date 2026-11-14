// Command workflow is the story workflow engine, built as factory-workflow and called as `factory wf …`
// (docs/workflow-engine.md). The logic lives in internal/workflow.
package main

import (
	"os"
	"time"

	"factory/go/internal/identity"
	"factory/go/internal/workflow"
)

func main() {
	env := identity.Env{Getenv: os.Getenv, LookupEnv: os.LookupEnv, Uid: os.Getuid(), Now: time.Now, Stderr: os.Stderr}
	os.Exit(workflow.Main(os.Args[1:], env, os.Stdout, os.Stderr))
}
