# Workflows (draft)

Drafts for TSR story DVDG-565. Nothing in this folder is loaded by the factory yet. The design is in `docs/knowledgebase/38-workflows-design.md`.

A workflow says which roles take part and what each does for a task of a given size. The workflow used today, with its full set of roles, is called `current` and is defined by `roles/`; it has no file here.

| File | What it is |
|---|---|
| `simple.md` | workflow for size XS or S, complexity 1 or 2 |
| `medium.md` | workflow for size M, or complexity 3 |
| `huge.md` | workflow for size L or XL, complexity 4 or 5, or a task that already has children |
| `roles/architect.md` | the planning agent |
| `roles/builder.md` | the implementing agent |
| `roles/reviewer.md` | the reviewing agent |
| `roles/qa.md` | the testing agent (huge only) |

Rules shared by every role in these workflows:

- The Taskosaur task is the record. Read it first; write what you did on it. Do not keep a design, a decision or a result only in a message.
- You do not start, stop or report to other agents. The factory routes the work from the state you record.
- You reach Taskosaur only through `factory tsr …`.
- A gap or a contradiction in a task is reported on that task and stops your work on it. You do not redesign on your own.
