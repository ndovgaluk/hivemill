# Worktree post-init rules

For the coding agent. Follow these right after you start in your worktree, before you install dependencies, run tests or change code. They apply to a freshly created worktree and to a reused one.

A worktree holds only committed files. The local-only files below live in the main checkout and are never committed, so your worktree starts without them (or, when reused, with a previous task's copy).

## Files

| File | What it is |
|---|---|
| `.env` | local runtime settings |
| `.env.test` | settings used by the tests |
| `.tsr` | Taskosaur pointer (organisation, project, epic) |

## Steps

1. Find the main checkout: it is the first `worktree` line of

   ```
   git worktree list --porcelain
   ```

   If that path is your own cwd, stop: you are in the main checkout, and these rules do not apply.

2. For each file in the table, in your worktree root:

   1. Check that git ignores it: `git check-ignore -q <file>`. If the command fails, do not create the file. Tell your lead that `<file>` must be added to `.gitignore` first, and go on with the next file.
   2. If the main checkout has the file, copy it over your own copy: `cp -p <main>/<file> ./<file>`. Always take the main checkout's version, also in a reused worktree: the copy left there may be stale or changed by an earlier task.
   3. If the main checkout does not have the file, skip it and go on. That is normal, not an error: the project may not use that file. Do not create it and do not invent values.

3. Check the result: `git status --porcelain` must not list any of these files.

## Never

- Commit these files, or add them with `git add -f`.
- Print their contents, or put a value from them into a PR, a message, a log or a test.
- Change the copies in the main checkout. You only read there.
- Edit `.gitignore` as part of these steps to make the check in 2.1 pass.
- Write a file with made-up or placeholder values because the real one is missing.

## When something is in the way

- You cannot read the main checkout (for example it is hidden by a sandbox): stop these steps and tell your lead which file you could not read.
- A file is missing and your task cannot be built or tested without it: say so to your lead, naming the file. Do not work around it.
