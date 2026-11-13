---
name: rework-brief
description: Format of a FAIL verdict summary, which is the coder's whole rework request. Use when you are about to run `factory verdict <T> --fail`.
---

# Rework brief (R8)

The FAIL summary is what the coder receives as the rework request (and what the flow debugger shows on the Review gate → Coders arrow). Write it so the coder can fix every blocking finding without opening the PR comment.

For each blocking finding, in this order:

1. **Where:** `file:line` (or the function), on the head you reviewed.
2. **What breaks:** a concrete input or state and the wrong result it gives (or the crash, the data lost, the contract broken).
3. **What correct looks like:** the expected behaviour, or the acceptance criterion it fails.
4. **Proof:** the test to add or the command to run that fails now and passes after the fix.

Then:

- On a retry (R2): the earlier blocking findings as RESOLVED, OPEN or DECLINED.
- Nits, if any, in one "follow-ups:" line; they never cause FAIL (R1).
- The PR comment URL with the full review.

Too thin: `Changes needed: web/cart_page.js:62 the loop reads the file again for every item.`

Enough:

```
1. web/cart_page.js:62 renderCart() calls readCatalog() inside the item loop.
   Breaks: a 200-item cart reads catalog.json 200 times; page load goes from ~40 ms to ~3 s.
   Correct: read the catalog once before the loop and look items up by id.
   Proof: add a test that renders 200 items with a counting readCatalog stub and asserts 1 call.
Review: https://github.com/example/repo/pull/12#issuecomment-1
```
