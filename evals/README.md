# Behavioral evaluations

These cases exercise the installed Skill through Codex's native public seam.
They are prompts and isolated fixtures, not a mock Ferry runtime.

- [`delegate-one-writer/`](delegate-one-writer/README.md): positive mutation,
  same-thread follow-up, and countable root verification.
- [`interrupt-canary/`](interrupt-canary/README.md): bounded native interrupt
  of an active no-write worker with exact Git comparison.

Run every mutating case in a disposable temporary Git repository. Record the
Codex version and platform with the result because native lifecycle behavior is
version- and host-scoped.
