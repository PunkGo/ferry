# Codex App Server: worker-scoped hook disable research

Date: 2026-08-24
Scope: official Codex/App Server surfaces only; Ferry and Flint may change, Codex and DeepSeek may not.
Versions verified locally: official Codex CLI `0.149.0`, official `openai-codex` Python SDK `0.147.0`.

## Conclusion

Yes. Ferry can disable hooks only for its SDK-owned worker thread while leaving the user's outer Codex/Flint hooks enabled.

The strongest, already-proved seam is the stable App Server `thread/start.config` override:

```python
config={"features": {"hooks": False}}
```

The installed official Python SDK exposes the same `config` parameter on both `AsyncCodex.thread_start(...)` and `AsyncCodex.thread_resume(...)`. Ferry must apply it at both calls so a fresh worker and a resumed/follow-up worker have identical behavior. This changes only the effective configuration of that App Server thread; it does not edit `~/.codex/config.toml`, Flint configuration, or the outer Codex process.

There is also a process-scoped official SDK option:

```python
CodexConfig(config_overrides=("features.hooks=false",))
```

The SDK translates every entry to `codex --config <entry> app-server ...`. This would disable hooks for every thread in Ferry's private App Server process, while other Codex processes keep their normal configuration. It is structurally valid, but the real DeepSeek A/B below tested the thread-level `config` form, so that is the evidence-backed first choice.

## Official documentation evidence

- The Hooks guide says hooks are enabled by default and identifies `[features] hooks = false` as the canonical off switch; `codex_hooks` is only a deprecated alias. It also says managed requirements can pin hooks on, which is the one policy exception Ferry cannot override silently: [Hooks — Turn hooks off](https://learn.chatgpt.com/docs/hooks#turn-hooks-off).
- The CLI supports one-invocation configuration. `--config` accepts arbitrary nested keys, while `--disable hooks` translates to `-c features.hooks=false`: [Advanced configuration — one-off overrides](https://learn.chatgpt.com/docs/config-file/config-advanced#one-off-overrides-from-the-cli), [Developer commands — global flags](https://learn.chatgpt.com/docs/developer-commands?surface=cli#global-flags).
- The App Server documentation describes `thread/start` configuration overrides and the Python SDK as an official JSON-RPC App Server client: [Codex App Server](https://learn.chatgpt.com/docs/app-server), [Codex SDK](https://learn.chatgpt.com/docs/codex-sdk).
- The stable public environment-variable list contains no hook-disable variable. `CODEX_HOME` could point at a separate state root, but it is not a hook switch and would also separate config/auth/sessions, so it is not the right Ferry seam: [Environment variables](https://learn.chatgpt.com/docs/config-file/environment-variables).

## Local official schema and source evidence

The stable schema was regenerated from the installed official binary with:

```text
codex app-server generate-json-schema --out /private/tmp/codex-app-server-schema-0.149.0-hooks-research-stable
```

Its `v2/ThreadStartParams.json` declares `config` as `object | null` with `additionalProperties: true`. The retained tagged source independently shows the same field and semantics:

- `/Users/feijiui/.local/share/ferry-diagnostics/codex-0.149.0-structural-proxy/codex-rs/app-server-protocol/schema/json/v2/ThreadStartParams.json:331`
- `.../codex-rs/app-server/src/request_processors/thread_processor.rs:1065` passes `ThreadStartParams.config` into the thread-start task.
- `.../codex-rs/app-server/src/request_processors/thread_processor.rs:1249` and `:1266` load that map as per-request configuration overrides.
- `.../codex-rs/app-server/src/config_manager.rs:224` converts the request JSON to TOML configuration overrides.
- `.../codex-rs/features/src/lib.rs:1036` defines stable feature key `hooks`, enabled by default.
- `.../codex-rs/core/src/session/mod.rs:4217` builds each session's hook configuration from that effective feature value.
- `.../codex-rs/hooks/src/registry.rs:274` returns no discovered hooks when the effective feature is disabled.

The diagnostic source tree is dirty because it contains unrelated diagnostic patches, but all files cited above were verified byte-for-byte unchanged from tag `rust-v0.149.0` at commit `758ef40f50c1a458425c7cfbf1eb12cbc07af0b0`.

The installed official SDK sources show:

- `openai_codex/client.py:193-252`: `CodexConfig.config_overrides` and its translation to repeated `--config` arguments before `app-server`.
- `openai_codex/api.py:374-413`: `AsyncCodex.thread_start(..., config=...)` forwards the map to `ThreadStartParams`.
- `openai_codex/api.py:447-478`: `AsyncCodex.thread_resume(..., config=...)` exposes the same override on resume.

Installed path: `/Users/feijiui/.local/share/uv/tools/ferry-codex/lib/python3.12/site-packages/openai_codex/`.

## Real DeepSeek A/B receipt

A one-shot probe used the official SDK, official Codex `0.149.0`, provider `deepseek`, model `deepseek-v4-flash`, read-only sandbox, and exactly:

```python
config={"features": {"hooks": False}}
```

Result:

- thread `01a031de-9952-7391-97af-e8e8d1e96062`, turn `01a031de-9c74-7fd0-89d0-9fe778c1f9df`;
- completed in about five seconds (`03:44:27.800Z` through `03:44:32.579Z`);
- rollout order was exactly `call_00`, `call_01`, `output_00`, `output_01` with matching native call ids;
- zero hook records appeared in the worker rollout;
- the expected completion nonce was present and Git was unchanged;
- Flint hooks remained active in the outer Codex session.

Secret values, provider endpoint, and credentials were not inspected or recorded. The worker rollout is locally retained at `/Users/feijiui/.codex/sessions/2026/08/24/rollout-2026-08-24T11-44-26-01a031de-9952-7391-97af-e8e8d1e96062.jsonl`.

This discriminates the live hypothesis: with hooks enabled, hook-injected developer context separated function calls from their outputs and DeepSeek rejected the continuation; with the one thread variable changed to `features.hooks=false`, the same coding-critical double-tool continuation completed with adjacent native call/output items.

## Newer schema fields: useful, but not fixes

Current stable App Server schema also exposes these hook/context-related surfaces:

| Surface | What it does | Relevance to this bug |
| --- | --- | --- |
| `initialize.capabilities.optOutNotificationMethods` | Suppresses exact notification methods for one connection. | Observation only. It does not stop hook execution or model-context injection. |
| `hook/started`, `hook/completed` | Reports synchronous hook execution and final summaries. | Useful verification/diagnostics; not a disable control. |
| `hooks/list` | Lists effective hook metadata/state. | Useful as a Doctor assertion that the worker has zero effective hooks. |
| `turn/start.additionalContext` | Adds client-provided context fragments. | Additive only; cannot remove/reorder hook-injected context. |
| `thread/inject_items` | Appends raw Responses API items to model-visible persisted history. | A transcript mutation surface, not a repair; Ferry should not rewrite Codex history. |
| `ThreadStartParams.experimentalRawEvents` | Emits raw Responses API items; marked internal-use-only. | Observability only and experimental; not a supported compatibility seam. |

Official references: [App Server initialization and notification opt-out](https://learn.chatgpt.com/docs/app-server#initialization), [App Server hooks and notifications](https://learn.chatgpt.com/docs/app-server#notifications), [App Server raw item injection](https://learn.chatgpt.com/docs/app-server#inject-items-into-a-thread). The corresponding generated stable schemas are under `/private/tmp/codex-app-server-schema-0.149.0-hooks-research-stable/v2/`.

## Recommended Ferry boundary and uncertainty

Implement the existing official SDK `config` argument at Ferry's worker start and resume seams. Do not edit user configuration, disable Flint globally, create a separate `CODEX_HOME`, rewrite transcripts, use raw App Server transport, or add a provider-specific shim.

Verification should prove through Ferry's public worker seam that:

1. both initial and resumed/follow-up threads have zero hook records/effective hooks;
2. the two sequential tool continuations retain matching adjacent call/output pairs;
3. outer-session Flint hooks still fire;
4. exact provider/model/cwd/sandbox evidence and Git invariance remain unchanged;
5. a managed requirement that forces hooks on is preserved as a typed `BLOCKED` result rather than reported as disabled.

The only material uncertainty is managed policy precedence: official documentation permits administrators to force hooks on. The local machine's A/B proves the override works for the currently active user/project/plugin hook layers, including Flint, but it is not evidence that Ferry can override an administrator-enforced requirement—and Ferry should not try.
