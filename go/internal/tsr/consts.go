// Package tsr is the Taskosaur REST client of the workflow engine (TSR task HM-23, docs/workflow-engine.md). Factory
// agents have no MCP, so the engine reaches Taskosaur over REST with one personal access token that only this code
// reads. The routes and fields are those of Taskosaur's backend (modules tasks, task-statuses, task-comments,
// task-commits, task-attachments).
package tsr

import "time"

// CheckKind is the "kind" of PATCH /tasks/:id/agent-check.
type CheckKind string

const (
	CheckReview CheckKind = "REVIEW"
	CheckQA     CheckKind = "QA"
)

// CheckResult is the "result" of PATCH /tasks/:id/agent-check; a nil *CheckResult clears the mark.
type CheckResult string

const (
	ResultPassed CheckResult = "PASSED"
	ResultFailed CheckResult = "FAILED"
)

// Status categories and user actions of a Taskosaur status (prisma StatusCategory, UserActionType).
const (
	CategoryTodo       = "TODO"
	CategoryInProgress = "IN_PROGRESS"
	CategoryDone       = "DONE"
	UserActionReview   = "REVIEW"
)

// Request body fields.
const (
	fieldStatusID  = "statusId"
	fieldTaskID    = "taskId"
	fieldContent   = "content"
	fieldKind      = "kind"
	fieldResult    = "result"
	fieldAgentName = "agentName"
	fieldRef       = "ref"
	fieldSHA       = "sha"
	fieldMessage   = "message"
)

// Routes, relative to the base URL (which ends in /api).
const (
	pathTaskByKey      = "/tasks/key/"
	pathTasks          = "/tasks"
	pathStatuses       = "/task-statuses/project"
	pathComments       = "/task-comments"
	pathCommits        = "/task-commits"
	pathAttachmentsFor = "/task-attachments/task/"
	pathAttachment     = "/task-attachments/"
	suffixStatus       = "/status"
	suffixAgentCheck   = "/agent-check"
	suffixDownload     = "/download"
)

// Query parameters of GET /tasks and GET /task-statuses/project.
const (
	queryOrganizationID = "organizationId"
	queryParentTaskID   = "parentTaskId"
	queryProjectID      = "projectId"
	queryIncludeDone    = "includeDone"
	querySortBy         = "sortBy"
	querySortOrder      = "sortOrder"
	queryLimit          = "limit"
	queryPage           = "page"
	sortListRank        = "listRank" // the list order of the board (Taskosaur DVDG-270)
	sortAsc             = "asc"
	pageSize            = "100"
	valueTrue           = "true"
)

// Limits and timing.
const (
	// MaxAttachmentBytes is the largest attachment Download accepts: Taskosaur's own upload limit.
	MaxAttachmentBytes = 50 << 20
	RequestTimeout     = 15 * time.Second
	MaxTries           = 3
	RetryPause         = 2 * time.Second
)

// Configuration files under ~/.config/factory.
const (
	URLFile   = "tsr-url"
	TokenFile = "tsr-token"
)
