# 45. The changed-files panel beside the Claude Code chat

## Q: I see the panel separation - on the left side chat and on the right side changed files. Where does it come from? Orca or Claude Code settings? How can I turn it on/off?

It comes from **Claude Code**, not from Orca and not from a setting. It is the built-in `/diff` view: the panel's own header says `19 files changed +216 -10   /diff to close   source: Current`.

- **Turn on:** type `/diff` in the Claude Code prompt.
- **Turn off:** type `/diff` again (the header's "/diff to close").
- `source: Current` (with a dropdown arrow) seems to choose which changes are shown; `Current` matches the uncommitted working tree (19 files in `git status`). Not checked: the other sources.
- `[ ask ]` next to a file name: not checked what it does.
- Nothing in `~/.claude/settings.json` turns it on; it opens only through the command and is not persisted as a setting (not checked: whether it reopens by itself in a resumed session).

What Orca adds to a Claude Code session in this setup is different and has no panel inside the terminal: hooks in `~/.claude/settings.json` that report the session state to Orca, and the `orca-agent-view` plugin ("Open Claude subagents from the Orca sidebar"), which shows subagents in Orca's own sidebar.
