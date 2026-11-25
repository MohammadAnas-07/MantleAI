# Known issues

Things that are true about Mantle today and that a user or contributor should know. The short
safety list is in the README under "Before you run it".

- Some lists stop at a fixed size with no message that more exist: a project's conversations at
  500, a conversation's messages at the first 500, the activity log at the newest 200 calls, and
  the agent run and gap finder lists at the newest 50 runs.
- The app reads at most 100 memory items per kind. The memory panel says "Showing X of Y", but a
  reference to a later item shows its short id instead of its title.
- The built web app is one script of about 610 kB.
- Model calls time out after 120 seconds of silence (`LLM_TIMEOUT_SECONDS`). An agent run on
  Gemini 3.8 Flash hit that limit; runs on Gemini 3.5 Flash Lite finished.
- Repositories don't yet check that a parent row belongs to the user. This must be fixed before
  login and accounts are added.
- There is no real-use evaluation yet: the 2-week trial in `docs/prd.md` hasn't started.
- Planner and Reviewer output has been checked on one sample only, so its quality is not proven.
- The larger retrieval evaluation (25 questions on a real repository) stopped at the Gemini daily
  limit and has no result.
- The switch demo scored 5 of 5 decision questions after a switch between two Gemini models, in
  two runs on 2026-11-18, with no saved result file.
- The teaching layer (teaching notes and the concepts list) and the model-written project summary
  are not built.
