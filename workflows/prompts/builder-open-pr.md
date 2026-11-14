Every child is built and reviewed. Open the one pull request for the whole branch now.

Title: `{title}`

Body, on standard input. It already follows the repository's pull request template and lists each story with its children; keep its headings and add nothing above them:

{body}

Steps, each command alone in its own call:

1. Bring the branch up to date with the base branch if it is behind (`git fetch origin` then `git merge origin/{base}`), run the affected tests again if the merge changed files, and push.
2. `factory pr create --title "{title}" --body -`
3. `factory prcheck`. Fix every FAIL it prints (a body FAIL is fixed by editing the pull request body, not the code) and run it again until it passes. This is the only time in a story run that the pre-PR check is used.
4. `factory task update {task} --status in_review --pr <the url printed by step 2>`
5. `factory done "<url>: {child_count} children of {story_count} stories built and reviewed; checks run per child and before the pull request"`

From here the factory's own final review, tests and merge take over. If CI is red or the final review asks for changes, you are started again in this session with the details; fix them on this branch and push.
