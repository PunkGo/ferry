# Ferry architecture

Status: Ferry's worker and pipx distribution gates are proved on macOS and native Windows with Codex 0.149.0, including clean standard artifacts, lifecycle control, upgrade, provider, and installed-entry advisory coverage. Ferry is ready for public release; publication remains an explicit operator-controlled action.

## Product thesis

Ferry is combination innovation. It combines:

- a Codex Skill for the owner-side operating procedure;
- a field-tested worker brief/report shape;
- the official `openai-codex` SDK;
- Codex App Server threads, turns, streaming, steering, interrupt, history, and compaction;
- the user's existing Codex model-provider configuration.

It does not create a new agent framework, task protocol, scheduler, lifecycle model, context store, receipt ledger, or provider format.

## Minimal architecture

```text
Codex owner thread                         sole mission owner, editor, and judge
  |
  +-- Ferry Skill                       when/how to delegate and verify
  |     `-- worker brief                    role, invariants, scope, gates, report
  |
  +-- native Codex worker thread           default; current-session inheritance
  |
  `-- Ferry worker tool                 only for an explicit alternate model/provider
          `-- official openai-codex SDK
                  `-- Codex App Server
                          `-- Codex thread / turns
                                  `-- configured model_provider -> Responses API
```

The worker tool is a thin adapter, not a dispatcher with its own intelligence. It exposes the official SDK operations needed by the owner and forwards their results. It contains no model, prompt planner, retry policy, task queue, durable registry, or independent judgment.

If Codex later exposes a stable native owner-to-external-provider worker seam, the adapter is deleted and the Skill points directly to that seam.

## Selection rule

1. No explicit alternate model/provider: use the current Codex session's native `worker` thread. Starting a second Codex runtime would waste tokens and process overhead, so Doctor warns against it.
2. Explicit custom provider or model: use the worker tool backed by the official SDK and App Server.
3. Missing requested configuration: fail closed with the observed cause. Never silently substitute another provider or the current session model.

Ferry has no `ferry.toml` and no model alias registry. Provider definitions, endpoints, credentials, model names, sandbox defaults, and profiles remain in Codex-owned machine-local configuration. Configuration is greater than code, and each fact has one owner.

## Installation boundary

Ferry requires a user-installed Python 3.10+ runtime and reuses the user's existing `codex` executable. It does not bundle a Python interpreter or the Python SDK's pinned second copy of the Codex CLI.

Ferry's only public installation path is `pipx install ferry-codex`, followed by
`ferry setup`. pipx owns the isolated Ferry environment; setup installs the pinned
Python SDK without `openai-codex-cli-bin`, registers the complete plugin through
official `codex plugin` commands, and requires a fresh Codex session for discovery.
Setup owns dependency installation only. It does not edit provider configuration,
credentials, project files, or task state. Doctor remains read-only and never
installs or repairs dependencies.

## Existing contracts, not a new protocol

The initial worker request follows this field-tested pattern:

```text
identity and exact worktree
  -> architectural invariants
  -> observable goals
  -> bounded work slices
  -> hard boundaries and stop conditions
  -> acceptance commands
  -> final report: files, evidence, decisions, unknowns
```

Follow-up or live steering uses the same thread to correct scope, answer a question, or request rework. The worker's final report is the conversational delivery returned to the owner. Ferry does not wrap it in a second wire schema, sign it, hash it, persist it, or call it settlement. The owner checks the real worktree and runs the real verification before accepting it.

## Ownership

Codex owner owns:

- task decomposition and the decision to delegate;
- the exact worker brief and later correction messages;
- native-worker versus custom-provider selection;
- repository inspection, verification, acceptance, and user communication.

The official SDK and App Server own:

- process startup and shutdown;
- thread and turn identity;
- start, resume, run, stream, steer, interrupt, read, and compact;
- conversation persistence, event delivery, approvals, sandbox behavior, and cleanup;
- provider/model routing for the App Server process and its threads.

Ferry owns:

- the Skill instructions;
- the worker brief/report template at `plugins/ferry/skills/ferry/references/worker-brief.md`;
- at most one thin owner-facing tool adapter over the official SDK;
- Doctor instructions and probes.

There is deliberately no Ferry-owned lifecycle.

## Lifetimes

| Layer | Lifetime | Context/state owner | Ferry responsibility |
| --- | --- | --- | --- |
| Owner thread | User session | Codex owner conversation | Keep mission intent and judge results |
| Skill | One relevant owner turn | Codex Skill loader | Supply procedure and brief template |
| Worker tool process | MCP host connection | Host + official SDK | Forward calls; no durable task state |
| App Server | SDK/tool process | Codex | Own runtime, events, auth, history access |
| Worker thread | One bounded delegated task | Codex thread store | Return thread id; resume the same thread |
| Turn | One request or correction | Codex App Server | Stream until completed, failed, or interrupted |
| Worktree | Repository lifetime | Git/filesystem | Owner verifies actual changes |

The adapter may retain SDK object handles while its process is alive because the SDK requires them for live `steer` and `interrupt`. Those are transient references to Codex-owned identities, not a second state machine. On adapter restart, stored Codex thread ids are resumed through the SDK; Ferry reconstructs no private state.

## Context model

There are only two model contexts:

- Owner context: product intent, user dialogue, delegation decisions, and final judgment.
- Worker-thread context: one coding assignment, its tool observations, corrections, and report.

App Server and the thin adapter have no model context. Codex persists worker conversation history and performs native compaction. Ferry does not summarize or compact independently.

Bounded tasks are the primary context control. Send corrections with App Server `turn/steer` while a turn is active or start another turn on the same thread after completion. If a worker thread has drifted or accumulated irrelevant history, start a fresh worker thread with a fresh complete brief; do not build a recovery/checkpoint subsystem.

## Normal flow

```text
owner reads project authority and exact Git state
        |
chooses native worker OR explicit custom-provider worker tool
        |
builds one Claude-shaped bounded brief
        |
starts Codex thread + turn
        |
streams/waits; steers or interrupts only when needed
        |
worker returns field-tested report shape
        |
owner inspects worktree and reruns acceptance checks
        |
accepts, sends same-thread rework, or reports blocker
```

One writer remains the default. Additional workers are read-only unless the user explicitly authorizes parallel writers and the worktree boundaries are independent.

## Doctor

Doctor proves the chosen path through the same public seam used for work.

For the native path it verifies native worker spawn, same-thread follow-up, wait, bounded interrupt when safe, exact worktree observation, and Git non-mutation.

For the custom-provider path it additionally verifies:

1. the supported `openai-codex` SDK and intended Codex runtime are available;
2. the requested model-provider name resolves from Codex-owned configuration without printing secrets;
3. a read-only App Server thread reports native `thread.modelProvider` matching the requested provider;
4. a fixed nonce completes, a second nonce completes on the same thread, and a bounded live turn can be steered/interrupted when required;
5. repository state is unchanged at the Git observation seam.

Model self-report is not provider evidence. Missing provider/auth, wrong native metadata, wrong worktree, failed turn, swallowed SDK error, unexpected mutation, or zero executed acceptance checks is `BLOCKED`. Use `DEGRADED` only for an optional capability that the intended task does not require.

Doctor does not install packages, edit provider config, reveal credentials, restart guessed processes, clean mutations, or persist readiness.

## Deletion test

Ferry will not ship:

- a general CLI or a second Codex UI;
- a custom App Server client or copied JSON-RPC protocol;
- a scheduler, queue, daemon supervisor, PID registry, heartbeat, polling loop, or cleanup policy;
- a task-state machine, packet wire format, receipt database, candidate digest, gate engine, or settlement layer;
- a context database, custom compactor, replay engine, or recovery checkpoint;
- a provider bridge or Ferry-owned provider/model/auth TOML;
- compatibility for deleted, unshipped implementations.

The one possible adapter earns its place only because the owner needs a callable surface for a different provider. Its implementation must use the official SDK rather than reproduce App Server behavior. Removing it must leave the Skill's native-worker path intact.

## Verified upstream surface

The design follows the current official [Codex App Server](https://learn.chatgpt.com/docs/app-server), [Codex SDK](https://learn.chatgpt.com/docs/codex-sdk), [subagent](https://learn.chatgpt.com/docs/agent-configuration/subagents), and [Skill](https://learn.chatgpt.com/docs/build-skills) documentation, checked 2026-08-22.

The stable Python SDK exposes `CodexConfig.config_overrides`, `thread_start(model_provider=...)`, `Thread.run/read/compact`, and `TurnHandle.stream/steer/interrupt`. A local PoC used the installed Codex 0.149.0 binary through that SDK to create a DeepSeek-backed read-only thread and complete two nonce turns on the same thread.

The official TypeScript SDK is not a language-equivalent App Server binding. At Codex 0.149.0 it wraps one `codex exec --experimental-json` subprocess per active run. Its public config passthrough can select `model_provider`, but its first native thread id arrives only after the first prompt starts, and it exposes no pre-turn thread read, live `turn/steer`, or native `turn/interrupt`. Generated TypeScript App Server protocol types exist upstream but no public TypeScript transport client exports them. Implementing that client inside Ferry would copy the App Server seam, so the Python SDK is required until an official TypeScript App Server client reaches parity.
