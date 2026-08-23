# Security policy

Ferry does not own provider credentials or a background service. Its optional
worker tool delegates process and thread handling to the official Codex SDK and
App Server. Its security boundary is nevertheless meaningful: Skill instructions
and tool parameters can influence which provider writes, which worktree it
touches, and whether failed verification is accepted.

Please report instruction injection that crosses the declared mutation scope,
silent agent/provider fallback, secret disclosure, wrong-worktree writes,
masked SDK/App Server failure, or unsafe lifecycle behavior privately through
the hosting platform's security-advisory mechanism. Do not include live tokens,
credentials, or private repository contents in a public issue.

Include the Ferry commit, Codex and SDK versions, platform, selected route and
provider, minimal prompt, native thread id, exact observed worktree, and redacted output needed to reproduce the
problem. If no private advisory channel is available, ask the maintainer for a
private reporting route without publishing exploit details.

Version-scoped support is documented in `SUPPORT.md`. Unproved platform/provider
rows are not security guarantees.
