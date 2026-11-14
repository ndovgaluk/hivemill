package tsr

import (
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
)

// Status is a Taskosaur task status.
type Status struct {
	ID         string  `json:"id"`
	Name       string  `json:"name"`
	Category   string  `json:"category"`
	Position   int     `json:"position"`
	UserAction *string `json:"userAction"`
}

// Task is the part of a Taskosaur task the engine reads. Acceptance criteria live inside Description.
type Task struct {
	ID           string `json:"id"`
	Key          string `json:"slug"`
	Title        string `json:"title"`
	Type         string `json:"type"`
	Size         string `json:"size"`
	Complexity   int    `json:"complexity"` // 0: not rated
	Description  string `json:"description"`
	E2ETests     string `json:"e2eTests"`
	ProjectID    string `json:"projectId"`
	ParentTaskID string `json:"parentTaskId"`
	Status       Status `json:"status"`
	Project      struct {
		Workspace struct {
			Organization struct {
				ID string `json:"id"`
			} `json:"organization"`
		} `json:"workspace"`
	} `json:"project"`
}

// OrganizationID is the task's organization (GET /tasks requires it).
func (t Task) OrganizationID() string { return t.Project.Workspace.Organization.ID }

// Attachment is one file attached to a task. FileName comes from the server: never use it as a path.
type Attachment struct {
	ID       string `json:"id"`
	TaskID   string `json:"taskId"`
	FileName string `json:"fileName"`
	FileSize int64  `json:"fileSize"`
	MimeType string `json:"mimeType"`
}

func seg(s string) string { return url.PathEscape(s) }

// TaskByKey is GET /tasks/key/:key.
func (c *Client) TaskByKey(key string) (Task, error) {
	var t Task
	return t, c.json(http.MethodGet, pathTaskByKey+seg(key), nil, nil, &t)
}

// Children lists the direct children of task in the board's list order, Done ones included, all pages.
func (c *Client) Children(task Task) ([]Task, error) {
	var all []Task
	for page := 1; ; page++ {
		q := url.Values{}
		q.Set(queryOrganizationID, task.OrganizationID())
		q.Set(queryParentTaskID, task.ID)
		q.Set(queryIncludeDone, valueTrue)
		q.Set(querySortBy, sortListRank)
		q.Set(querySortOrder, sortAsc)
		q.Set(queryLimit, pageSize)
		q.Set(queryPage, strconv.Itoa(page))
		var res struct {
			Data       []Task `json:"data"`
			TotalPages int    `json:"totalPages"`
		}
		if err := c.json(http.MethodGet, pathTasks, q, nil, &res); err != nil {
			return nil, err
		}
		all = append(all, res.Data...)
		if page >= res.TotalPages || len(res.Data) == 0 {
			return all, nil
		}
	}
}

// Statuses is GET /task-statuses/project?projectId=, ordered by position.
func (c *Client) Statuses(projectID string) ([]Status, error) {
	var s []Status
	return s, c.json(http.MethodGet, pathStatuses, url.Values{queryProjectID: {projectID}}, nil, &s)
}

// SetStatus is PATCH /tasks/:id/status.
func (c *Client) SetStatus(taskID, statusID string) error {
	return c.json(http.MethodPatch, pathTasks+"/"+seg(taskID)+suffixStatus, nil, map[string]string{fieldStatusID: statusID}, nil)
}

// Comment is POST /task-comments.
func (c *Client) Comment(taskID, markdown string) error {
	return c.json(http.MethodPost, pathComments, nil, map[string]string{fieldTaskID: taskID, fieldContent: markdown}, nil)
}

// AgentCheck is PATCH /tasks/:id/agent-check: set (or, with result nil, clear) the "reviewed" or "tested by agent"
// mark. Taskosaur accepts it only from an agent user and only in a user-action status.
func (c *Client) AgentCheck(taskID string, kind CheckKind, result *CheckResult, agentName, ref string) error {
	body := map[string]any{fieldKind: kind, fieldResult: result}
	if agentName != "" {
		body[fieldAgentName] = agentName
	}
	if ref != "" {
		body[fieldRef] = ref
	}
	return c.json(http.MethodPatch, pathTasks+"/"+seg(taskID)+suffixAgentCheck, nil, body, nil)
}

// LinkCommit is POST /task-commits once per task (the route takes one taskId).
func (c *Client) LinkCommit(taskIDs []string, sha, message string) error {
	for _, id := range taskIDs {
		body := map[string]string{fieldTaskID: id, fieldSHA: sha}
		if message != "" {
			body[fieldMessage] = message
		}
		if err := c.json(http.MethodPost, pathCommits, nil, body, nil); err != nil {
			return err
		}
	}
	return nil
}

// Attachments is GET /task-attachments/task/:taskId.
func (c *Client) Attachments(taskID string) ([]Attachment, error) {
	var a []Attachment
	return a, c.json(http.MethodGet, pathAttachmentsFor+seg(taskID), nil, nil, &a)
}

// AttachmentByID is GET /task-attachments/:id: one attachment's record, with the task it belongs to.
func (c *Client) AttachmentByID(id string) (Attachment, error) {
	var a Attachment
	return a, c.json(http.MethodGet, pathAttachment+seg(id), nil, nil, &a)
}

// ErrTooLarge means an attachment is over MaxAttachmentBytes; what was written to w is incomplete.
var ErrTooLarge = fmt.Errorf("attachment larger than %d bytes", MaxAttachmentBytes)

// Download streams GET /task-attachments/:id/download into w, at most MaxAttachmentBytes.
func (c *Client) Download(attachmentID string, w io.Writer) (int64, error) {
	resp, err := c.send(http.MethodGet, pathAttachment+seg(attachmentID)+suffixDownload, nil, nil)
	if err != nil {
		return 0, err
	}
	defer resp.Body.Close()
	n, err := io.Copy(w, io.LimitReader(resp.Body, MaxAttachmentBytes+1))
	if err != nil {
		return n, err
	}
	if n > MaxAttachmentBytes {
		return n, ErrTooLarge
	}
	return n, nil
}
