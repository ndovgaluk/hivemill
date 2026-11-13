---
name: worktree-postinit
description: Brings the local-only files a fresh worktree lacks (environment files, the task manager pointer) from the main checkout, when the project asks for it. Use when you start in your worktree and the repository root holds a file named worktree-postinit-rules.md
---

Purpose: a worktree holds only committed files, so local-only files of the main checkout are missing in it. Some projects list what to bring over.

1. Look for `worktree-postinit-rules.md` in the root of your worktree. No such file: this skill does nothing; go on with your task.
2. The file exists: read it and follow it before you install dependencies, run tests or change code.
3. It never asks you to commit the files it names. If a step fails, say so in your `factory done` summary and go on.
