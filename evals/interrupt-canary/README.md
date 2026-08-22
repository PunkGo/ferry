# Interrupt canary

Run `prompt.md` in a fresh Codex session in a disposable clean Git repository
where the Ferry Skill is installed. The worker performs no repository reads
or writes; the bounded delay exists only to keep the native thread active long
enough for root to interrupt it safely.

The case passes only when the exact spawned thread reaches an interrupted or
cancelled terminal state and the root proves that HEAD, `HEAD^{tree}`, and
porcelain status did not change. A completed 30-second delay is `BLOCKED`
because it does not prove interrupt.
