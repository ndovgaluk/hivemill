package workflow

import (
	"errors"
	"fmt"
)

// The workflow rule (owner decision of 2026-11-13): the larger result of size and complexity wins.
//
//	size XS or S, complexity 1 or 2             -> simple
//	size M, or complexity 3                     -> medium
//	size L or XL, or complexity 4 or 5,
//	or the task already has children            -> huge
var (
	sizeRank = map[string]int{"XS": 1, "S": 1, "M": 2, "L": 3, "XL": 3}
	compRank = map[int]int{1: 1, 2: 1, 3: 2, 4: 3, 5: 3}
	rankName = map[int]string{1: WorkflowSimple, 2: WorkflowMedium, 3: WorkflowHuge}
)

// rankHuge is the rank a task with children gets.
const rankHuge = 3

// ErrUnrated means a task has neither a size nor a complexity, so no workflow can be chosen.
var ErrUnrated = errors.New("neither size nor complexity is set")

// Choose is the workflow for a task of this size ("" = none), complexity (0 = none) and children.
func Choose(size string, complexity int, hasChildren bool) (string, error) {
	s, okS := sizeRank[size]
	c, okC := compRank[complexity]
	if !okS && !okC {
		return "", ErrUnrated
	}
	r := max(s, c)
	if hasChildren {
		r = rankHuge
	}
	return rankName[r], nil
}

// Workflow origin, recorded as the factory event that start writes (no column in workflow.db for it).
const (
	eventWorkflowChosen = "workflow-chosen" // from size and complexity
	eventWorkflowGiven  = "workflow-given"  // named with --workflow
	originChosen        = "chosen"
	originGiven         = "given"
)

// chooseFor picks the workflow of a run: the largest over its stories.
func chooseFor(stories []planStory) (string, error) {
	best := 0
	for _, s := range stories {
		w, err := Choose(s.size, s.complexity, s.hasChildren)
		if err != nil {
			return "", usageError{fmt.Sprintf("%s: %v; rate it in the task manager (size or complexity), or name a "+
				"workflow with --workflow simple|medium|huge", s.key, err)}
		}
		for r, n := range rankName {
			if n == w && r > best {
				best = r
			}
		}
	}
	return rankName[best], nil
}

// planStory is what Choose needs of a story.
type planStory struct {
	key         string
	size        string
	complexity  int
	hasChildren bool
}

// workflowOrigin is "chosen" or "given" for a run, from the event start wrote ("" when there is none).
func (e *Engine) workflowOrigin(goal string) string {
	if e.Factory == nil {
		return ""
	}
	var action string
	if e.Factory.QueryRow(`SELECT action FROM events WHERE entity=? AND entity_id=? AND action IN (?, ?)
		ORDER BY id DESC LIMIT 1`, EventEntity, goal, eventWorkflowChosen, eventWorkflowGiven).Scan(&action) != nil {
		return ""
	}
	if action == eventWorkflowGiven {
		return originGiven
	}
	return originChosen
}
