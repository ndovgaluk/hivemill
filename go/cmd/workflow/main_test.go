package main

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

// TestBinary runs the compiled binary as the factory does: status on a fresh home, then a usage error.
func TestBinary(t *testing.T) {
	bin := filepath.Join(t.TempDir(), "factory-workflow")
	if out, err := exec.Command("go", "build", "-o", bin, ".").CombinedOutput(); err != nil {
		t.Fatalf("go build: %v\n%s", err, out)
	}
	home := t.TempDir()
	cmd := exec.Command(bin, "status")
	cmd.Env = []string{"FACTORY_HOME=" + home, "HOME=" + home, "PATH=/usr/bin:/bin"}
	out, err := cmd.Output()
	if err != nil || strings.TrimSpace(string(out)) != "no runs" {
		t.Fatalf("status: err %v out %q", err, out)
	}
	if st, err := os.Stat(filepath.Join(home, "db", "workflow.db")); err != nil || st.Mode().Perm() != 0o600 {
		t.Fatalf("workflow.db: %v %v", st, err)
	}
	cmd = exec.Command(bin, "bogus")
	cmd.Env = []string{"FACTORY_HOME=" + home, "HOME=" + home}
	if err := cmd.Run(); err == nil || err.(*exec.ExitError).ExitCode() != 2 {
		t.Fatalf("bogus: want exit 2, got %v", err)
	}
}
