package tsr

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"time"
)

// Client talks to one Taskosaur instance with one token. The token never appears in an error, a log or an event.
type Client struct {
	base  string // ends in /api, no trailing slash
	token string
	http  *http.Client
	pause time.Duration // between tries; tests set 0
}

// New returns a client with a 15 s timeout per request that never follows a redirect.
func New(baseURL, token string) *Client {
	return &Client{base: strings.TrimRight(baseURL, "/"), token: token, pause: RetryPause, http: &http.Client{
		Timeout:       RequestTimeout,
		CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse },
	}}
}

// Error is a request that Taskosaur answered with a non-2xx status, or that never got an answer (Status 0).
type Error struct {
	Method, Path string // the route, never the full URL with a query of ids
	Status       int
	Message      string // Taskosaur's message, or the network error
}

func (e *Error) Error() string {
	if e.Status == 0 {
		return fmt.Sprintf("taskosaur %s %s: %s", e.Method, e.Path, e.Message)
	}
	return fmt.Sprintf("taskosaur %s %s: HTTP %d: %s", e.Method, e.Path, e.Status, e.Message)
}

// Load builds a client from <dir>/tsr-url and <dir>/tsr-token. Both must be regular files (not symlinks), mode 0600,
// owned by this user and not empty; a failing file is named with the rule, never with its content.
func Load(dir string) (*Client, error) {
	u, err := readSecretFile(filepath.Join(dir, URLFile))
	if err != nil {
		return nil, err
	}
	t, err := readSecretFile(filepath.Join(dir, TokenFile))
	if err != nil {
		return nil, err
	}
	pu, err := url.Parse(u)
	if err != nil || (pu.Scheme != "http" && pu.Scheme != "https") || pu.Host == "" {
		return nil, fmt.Errorf("%s: must hold one http(s) base URL", filepath.Join(dir, URLFile))
	}
	return New(u, t), nil
}

// readSecretFile is _token_file_ok of bin/factory_cli.py plus the read: lstat first, so a symlink is never followed.
func readSecretFile(path string) (string, error) {
	rule := fmt.Errorf("%s: must be a regular file (not a symlink), mode 0600, owned by you and not empty", path)
	st, err := os.Lstat(path)
	if err != nil {
		return "", fmt.Errorf("%w (%v)", rule, errors.Unwrap(err))
	}
	sys, ok := st.Sys().(*syscall.Stat_t)
	if !st.Mode().IsRegular() || st.Mode().Perm() != 0o600 || !ok || int(sys.Uid) != os.Getuid() || st.Size() == 0 {
		return "", rule
	}
	b, err := os.ReadFile(path)
	if err != nil {
		return "", rule
	}
	s := strings.TrimSpace(string(b))
	if s == "" || strings.ContainsAny(s, "\r\n") {
		return "", fmt.Errorf("%s: must hold exactly one line", path)
	}
	return s, nil
}

// send performs one request with retries: at most MaxTries on a network error or a 5xx, none on a 4xx or a redirect.
// The returned response has a 2xx status; the caller closes its body.
func (c *Client) send(method, route string, query url.Values, body any) (*http.Response, error) {
	var payload []byte
	if body != nil {
		var err error
		if payload, err = json.Marshal(body); err != nil {
			return nil, err
		}
	}
	target := c.base + route
	if len(query) > 0 {
		target += "?" + query.Encode()
	}
	var last error
	for try := 1; try <= MaxTries; try++ {
		if try > 1 {
			time.Sleep(c.pause)
		}
		req, err := http.NewRequest(method, target, bytes.NewReader(payload))
		if err != nil {
			return nil, &Error{Method: method, Path: route, Message: "bad request: " + err.Error()}
		}
		req.Header.Set("Authorization", "Bearer "+c.token)
		req.Header.Set("Accept", "application/json")
		if body != nil {
			req.Header.Set("Content-Type", "application/json")
		}
		resp, err := c.http.Do(req)
		if err != nil {
			last = &Error{Method: method, Path: route, Message: scrubURL(err)}
			continue
		}
		if resp.StatusCode >= 200 && resp.StatusCode < 300 {
			return resp, nil
		}
		last = &Error{Method: method, Path: route, Status: resp.StatusCode, Message: apiMessage(resp)}
		resp.Body.Close()
		if resp.StatusCode < 500 {
			return nil, last
		}
	}
	return nil, last
}

// scrubURL drops the URL from a transport error: it is the configured address, not something a caller needs.
func scrubURL(err error) string {
	var ue *url.Error
	if errors.As(err, &ue) {
		return ue.Err.Error()
	}
	return err.Error()
}

// apiMessage is Taskosaur's error message ({"message": "..."} or a list of validation messages), at most 500 bytes.
func apiMessage(resp *http.Response) string {
	raw, _ := io.ReadAll(io.LimitReader(resp.Body, 64<<10))
	var e struct {
		Message any `json:"message"`
	}
	msg := http.StatusText(resp.StatusCode)
	if json.Unmarshal(raw, &e) == nil {
		switch m := e.Message.(type) {
		case string:
			msg = m
		case []any:
			parts := make([]string, 0, len(m))
			for _, p := range m {
				parts = append(parts, fmt.Sprint(p))
			}
			msg = strings.Join(parts, "; ")
		}
	}
	if loc := resp.Header.Get("Location"); resp.StatusCode >= 300 && resp.StatusCode < 400 && loc != "" {
		msg = "redirect not followed"
	}
	if len(msg) > 500 {
		msg = msg[:500]
	}
	return msg
}

func (c *Client) json(method, route string, query url.Values, body, out any) error {
	resp, err := c.send(method, route, query, body)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if out == nil {
		_, _ = io.Copy(io.Discard, resp.Body)
		return nil
	}
	if err := json.NewDecoder(resp.Body).Decode(out); err != nil {
		return &Error{Method: method, Path: route, Status: resp.StatusCode, Message: "unreadable answer: " + err.Error()}
	}
	return nil
}
