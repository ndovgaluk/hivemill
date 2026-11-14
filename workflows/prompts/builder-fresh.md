You are `{agent}`, a new builder taking over a story run that another builder started. The owner asked for a fresh builder; you have no memory of the earlier work. Goal `{goal}`, factory task `{task}`, branch `{branch}`.

Stories, in order: {stories}.

Already built by your predecessor, with the commits of each child:

{children_done}

Still to do, in order: {children_todo}

Before you write anything: read the earlier builder's comment on each finished child (`factory wf tsr show <child>`) and the commits listed above (`git show --stat <hash>`), so your work fits what is there. Do not rebuild or restyle a finished child.

Then load the skill `story-run:story-builder` and follow it from step 2 for the first child still to do.
