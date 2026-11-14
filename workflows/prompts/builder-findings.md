Review of `{child}`: changes requested (round {round} of {max_rounds}).

The findings are the newest reviewer comment on `{child}`: read them with `factory wf tsr show {child}`. The child is back In Progress in the task manager.

Finish the child you have in hand first. Then, before starting any other child: fix every finding, commit with `{child}` in the subject, push, comment on `{child}` saying what you changed for each finding, and run `factory wf tsr status {child} in_review`.

If a finding is wrong, do not ignore it and do not argue in code: answer it in your comment on `{child}` with the evidence, and set the child `in_review`. The reviewer reads your comment.
