# Delegate one writer

This behavioral case exercises Ferry through Codex's public worker-thread
seam. It is deliberately not a unit test of Skill wording.

## What it proves

- repository Skill discovery through an explicit `$ferry` request;
- default selection of Codex's built-in `worker`, with no alternate-provider
  worker tool or separately launched Codex/App Server runtime;
- one bounded writer in an exact temporary worktree;
- native spawn, wait, and same-thread follow-up;
- root inspection of the resulting diff;
- a final verification command that executes at least five tests.

It does not prove an alternate provider, interrupt, or Windows.

## Run

1. Create a temporary directory outside this repository.
2. Copy the contents of `fixture/` into it.
3. Copy `plugins/ferry/skills/ferry/` from the Ferry checkout to
   `plugins/ferry/skills/ferry/` in the temporary directory and use that path as
   the fixture's sole Skill authority.
4. Initialize Git and commit the copied fixture so the root can inspect an exact
   baseline.
5. Start a fresh Codex session in the temporary directory and submit the
   contents of `prompt.md` verbatim.
6. After Codex finishes, run `python3 -m unittest -v` and inspect `git diff`.

The case passes only when all acceptance criteria in `prompt.md` hold. Delete
the temporary directory after retaining any output needed for a failure report.

### Codex 0.149.0 note

On macOS, `codex exec --ephemeral` could not create the default full-history
fork because the root session was intentionally not persisted. The root
preserved that failure, then successfully spawned with `fork_turns="none"`
because the bounded worker prompt contained all required context. A normal
persistent interactive session does not have this measured constraint. Treat
future occurrences as a Codex invocation-mode fact, not as proof of provider or
worker failure.
