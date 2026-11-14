package workflow

import (
	"errors"
	"strings"
	"testing"
)

// TestChooseEveryCombination checks the rule for every size, complexity and children, written out as the owner's
// sentences: huge wins over medium wins over simple.
func TestChooseEveryCombination(t *testing.T) {
	for _, size := range []string{"", "XS", "S", "M", "L", "XL"} {
		for c := 0; c <= 5; c++ {
			for _, kids := range []bool{false, true} {
				got, err := Choose(size, c, kids)
				if size == "" && c == 0 {
					if !errors.Is(err, ErrUnrated) {
						t.Errorf("unrated (children %v): %q %v", kids, got, err)
					}
					continue
				}
				want := WorkflowSimple
				switch {
				case size == "L" || size == "XL" || c >= 4 || kids:
					want = WorkflowHuge
				case size == "M" || c == 3:
					want = WorkflowMedium
				}
				if err != nil || got != want {
					t.Errorf("size %q complexity %d children %v: %q %v, want %q", size, c, kids, got, err, want)
				}
			}
		}
	}
}

func TestStartChoosesOrTakesTheGivenWorkflow(t *testing.T) {
	r := newStartRig(t)
	single := enriched("ONE") // a task without children: its own only child
	single.Size, single.Complexity = "M", 2
	r.tracker.tasks["ONE"] = single
	if code, _, errs := run(r.env, "start", "--story", "ONE"); code != 0 {
		t.Fatal(errs)
	}
	if _, out, _ := run(r.env, "status"); out != "G-001 ONE medium (chosen) building\n" {
		t.Fatalf("chosen: %q", out)
	}

	r2 := newStartRig(t)
	xl := r2.tracker.tasks["ST-1"]
	xl.Size, xl.Complexity = "XL", 5
	r2.tracker.tasks["ST-1"] = xl
	if code, _, errs := run(r2.env, "start", "--story", "ST-1", "--workflow", "simple"); code != 0 {
		t.Fatal(errs)
	}
	if _, out, _ := run(r2.env, "status"); out != "G-001 ST-1 simple (given) building\n" {
		t.Fatalf("given: %q", out)
	}
}

func TestStartRefusesAnUnratedStory(t *testing.T) {
	r := newStartRig(t)
	st := r.tracker.tasks["ST-1"]
	st.Size, st.Complexity = "", 0
	r.tracker.tasks["ST-1"] = st
	code, _, errs := run(r.env, "start", "--story", "ST-1")
	if code != exitUsage || !strings.Contains(errs, "ST-1: neither size nor complexity is set; rate it") || len(r.factory.calls) != 0 {
		t.Fatalf("unrated: %d %q %v", code, errs, r.factory.calls)
	}
	if code, _, errs := run(r.env, "start", "--story", "ST-1", "--workflow", "medium"); code != 0 {
		t.Fatalf("named workflow on an unrated story: %q", errs)
	}
	if code, _, _ := run(r.env, "start", "--story", "ST-9", "--workflow", "giant"); code != exitUsage {
		t.Fatal("unknown workflow accepted")
	}
}
