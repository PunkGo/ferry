---
name: ferry
description: Delegate bounded coding work to a Codex worker, including an explicitly configured alternate model/provider through the official Codex SDK and App Server, or diagnose worker readiness. Use when the user asks to delegate, use a worker/custom model/provider, steer or interrupt delegated work, or run Ferry doctor. Do not use for ordinary single-thread coding or generic project health checks.
---

# Ferry

Combine Codex's existing worker machinery with the field-tested worker brief in [references/worker-brief.md](references/worker-brief.md). Do not invent a scheduler, lifecycle, packet schema, receipt ledger, context store, provider bridge, or second model configuration.

The current Codex thread is the owner. It alone scopes work, chooses the route, corrects the worker, inspects the worktree, runs acceptance checks, and accepts or rejects the result.

## Installed Ferry integration

When Ferry is installed as `ferry-codex`, its only console integration commands are
`ferry setup`, `ferry status`, and `ferry uninstall`; `ferry --version` reports the
embedded build identity. Install with `uv tool install ferry-codex`, then run
`ferry setup` and start a fresh Codex session. `uv` is the primary public
installation path; `pipx install ferry-codex` remains a supported alternative.
Install Ferry with exactly one manager because their executable directories can
overlap. Ferry uses the running tool environment's Python, installs its exact tested
SDK pin without dependencies during setup, and reuses the host `codex`; it never
bundles a Python runtime or another Codex CLI. Publication is a separate authorized
action.

Before upgrading or uninstalling, close every Ferry-using Codex session. Use
`uv tool upgrade ferry-codex && ferry setup` (or `pipx upgrade ferry-codex && ferry
setup`) to reconcile an upgrade. For complete removal, use `ferry uninstall && uv
tool uninstall ferry-codex` (or `ferry uninstall && pipx uninstall ferry-codex`).
These are package-manager and Codex-plugin lifecycle actions, not worker operations:
do not invent a Ferry update command, provider configuration command, daemon, or
duplicate Doctor.

## Choose the route

1. If no alternate model or provider is explicitly requested, use Codex's native `worker`. Let it inherit the current session configuration. Do not start a second runtime.
2. If the user explicitly requests another configured model or provider, use the Ferry MCP `worker_start` tool backed by the official `openai-codex` SDK and Codex App Server.
3. If that tool is unavailable or the requested Codex-owned provider/model configuration does not resolve, stop with the observed cause. Do not silently use the current session model or another provider.
4. Never copy provider definitions, endpoints, or credentials into Ferry files. Ferry has no configuration TOML.

If the user asks for readiness or `doctor`, run Doctor before normal delegation.

## Delegate

1. Read repository authority. Resolve the exact absolute worktree and capture Git identity and porcelain state when Git is available.
2. Read [references/worker-brief.md](references/worker-brief.md) completely and construct one bounded brief using its existing section order.
3. Keep one writer. Additional agents are read-only unless the user explicitly authorizes independent parallel writers.
4. Start the selected native worker or `worker_start` with exact worktree, brief, sandbox, and requested model/provider.
5. For the MCP route, repeatedly call bounded `worker_wait`; inspect its top-level `events` even when `ok: false`, because events already dequeued in that call are returned exactly once with the typed failure and will not replay. Its timeout reserves a final native liveness query after the stream segment. Its `active` status is a native thread-liveness snapshot, not a promise of hard real-time control. `terminal_pending` means the native thread is already idle while terminal stream events remain to be consumed; continue `worker_wait` and do not steer or interrupt. `NATIVE_LIVENESS_TIMEOUT` is neither status: do not infer active or idle, and preserve the native result of any same-turn steer or interrupt. Use `worker_steer` only on that same live turn and `worker_interrupt` only for a user redirect, scope violation, unsafe action, or explicit stop condition.
6. A native turn can finish after an `active` snapshot and before control reaches App Server. Preserve that native steer or interrupt failure; do not retry or fall back automatically. Only after terminal completion is observed, use `worker_follow_up` with the returned native thread id. On MCP restart, only a completed thread can be resumed; steer/interrupt of an absent live handle must return `LIVE_HANDLE_UNAVAILABLE`.
7. Require the final response to follow the worker brief report. Treat it as delivery data, not a verdict.
8. Independently inspect the actual worktree and diff. Run real acceptance commands and verify relevant checks actually executed.

Do not push, merge, deploy, publish, or mutate external state unless separately authorized.

## Doctor

Doctor is read-only and exercises the same route normal work uses. It never installs dependencies, edits configuration, displays secrets, cleans changes, or manages processes.

Snapshot absolute current directory, Git top level, `HEAD`, `HEAD^{tree}`, exact porcelain, platform, Codex version, route, model, and provider. A dirty starting tree is allowed but must be preserved exactly.

For an alternate provider, use the five MCP tools: verify SDK/runtime through `worker_start`, require native provider metadata before the brief starts, run a fixed nonce and same-thread follow-up, and when required prove bounded wait plus steer/interrupt. Model prose is never provider proof. Missing provider/auth, mismatch, wrong worktree, a failed turn, zero executed checks, or Git mutation is `BLOCKED` and retains the original cause.

Report `READY` only when every required capability is proved through the actual seam; `DEGRADED` only for an optional unused recovery capability; otherwise `BLOCKED`. Persist no readiness cache or receipt.
