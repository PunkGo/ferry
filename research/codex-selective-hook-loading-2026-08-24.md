# Codex worker hook and skill configuration surfaces

Date: 2026-08-24
Scope: current public OpenAI documentation, official Codex CLI/App Server `0.149.0`, and official `openai-codex` Python SDK `0.147.0`. Product code was not changed.

## Bottom line for Ferry

The stable, high-level worker seam supports only two hook policies that Ferry can expose without inventing its own hook registry:

- `disabled` (default): pass `config={"features": {"hooks": false}}` to both `thread_start` and `thread_resume`.
- `inherit`: omit that override and let Codex apply the user's effective hook configuration, trust, individual enablement, plugins, project layers, and managed policy.

There is no first-class stable `thread/start` or `thread/resume` field for a hook name list, source allowlist, or source denylist. App Server exposes hook discovery and generic config state, but turning those primitives into a Ferry-owned selector would require Ferry to snapshot positional hook keys, reconcile source/trust/policy changes, and define semantics Codex does not define. Ferry should not do that.

Skills are different: Codex has exact name/path overrides, but no single documented “disable every skill” feature switch. Ferry should therefore leave skills at `inherit` by default and expose no Ferry-owned skill list.

## Capability matrix

| Capability | Hooks | Skills |
| --- | --- | --- |
| All on/off | Yes: stable `features.hooks`; hooks default on. | No all-skills switch in the documented config or 0.149.0 `SkillsConfig`. `skills.bundled.enabled=false` disables bundled skills only; `skills.include_instructions=false` only removes the automatic instructions block. |
| Managed-only | Admin-only: `allow_managed_hooks_only=true` is supported only in `requirements.toml`, not user/session/thread config. | No analogous managed-only switch found. |
| Individual enable/disable | `/hooks` can disable/re-enable individual non-managed hooks. Managed hooks ignore user state. | Stable exact name/path rules via `skills.config`; later matching rules win. |
| Thread named/source selector | No first-class field or whitelist. Raw session config can carry exact `hooks.state` keys, but that is state-by-internal-key, not a named/source selector. | No whitelist field. Raw thread config can carry exact `skills.config` name/path rules because session config is one supported rule layer. |
| Inspect | Stable `hooks/list(cwds)` returns discovered entries with `enabled`, `source`, `sourcePath`, `isManaged`, hash, and trust state. It has no `threadId` or per-request config parameter and returns disabled entries too. | Stable `skills/list(cwds, forceReload)` returns metadata including `enabled`, path, and scope. |
| Stable write RPC | No hook-specific write RPC. Stable generic `config/batchWrite` can persist `hooks.state` to user `config.toml`. | Stable `skills/config/write` persists one name/path enablement override. |
| High-level Python SDK | `thread_start(config=...)` and `thread_resume(config=...)`; no high-level `hooks_list` or hook-config method. | Same raw thread config seam; no high-level `skills_list` or `skills_config_write` method. |

## Hooks

### All hooks on or off

Hooks are enabled by default. The canonical off switch is:

```toml
[features]
hooks = false
```

`codex_hooks` is only a deprecated alias. This is documented by [Hooks: Turn hooks off](https://learn.chatgpt.com/docs/hooks#turn-hooks-off) and the [`features.hooks` field table](https://learn.chatgpt.com/docs/config-file/config-reference#featureshooks).

Codex 0.149.0's stable generated `ThreadStartParams` and `ThreadResumeParams` schemas each contain an open `config: object | null`. The tagged protocol source declares the same `HashMap` fields for [thread start](https://github.com/openai/codex/blob/rust-v0.149.0/codex-rs/app-server-protocol/src/protocol/v2/thread.rs#L59-L99) and [thread resume](https://github.com/openai/codex/blob/rust-v0.149.0/codex-rs/app-server-protocol/src/protocol/v2/thread.rs#L332-L390). App Server appends request entries to the existing process CLI overrides and sends the result through `ConfigBuilder`; it does not replace the complete configuration object ([0.149.0 config manager](https://github.com/openai/codex/blob/rust-v0.149.0/codex-rs/app-server/src/config_manager.rs#L208-L238)).

The installed Python SDK exposes this raw config map on both sync and async `thread_start` and `thread_resume` ([0.147.0 `api.py`](https://github.com/openai/codex/blob/rust-v0.147.0/sdk/python/src/openai_codex/api.py#L132-L233)). Therefore Ferry can apply the hook feature value per worker start/resume without editing global config.

### Managed-only is not a worker option

The Hooks guide describes `allow_managed_hooks_only=true` under managed requirements: it skips user, project, session, and plugin hooks while retaining administrator-managed hooks ([Managed hooks](https://learn.chatgpt.com/docs/hooks#managed-hooks-from-requirementstoml)). The important runtime boundary is stricter than the field name suggests: Codex states that the setting is supported only in `requirements.toml`; putting it in `config.toml` does not enable the policy ([0.149.0 configuration source](https://github.com/openai/codex/blob/rust-v0.149.0/docs/config.md#L9-L15)). The 0.149.0 loader test also verifies that the same top-level value in user config leaves the requirement unset ([loader test](https://github.com/openai/codex/blob/rust-v0.149.0/codex-rs/core/src/config/config_loader_tests.rs#L363-L388)).

Consequently Ferry cannot offer “managed-only” as a thread policy. If an administrator enforces it, `inherit` observes it; `disabled` remains subject to managed requirements precedence and must fail visibly if the requested effective policy cannot be obtained.

### Individual non-managed hook state

The CLI `/hooks` browser can inspect sources, trust changed hooks, and disable or re-enable individual non-managed handlers; managed handlers cannot be disabled ([Hooks review and trust](https://learn.chatgpt.com/docs/hooks#review-and-trust-hooks), [`/hooks` command](https://learn.chatgpt.com/docs/developer-commands?surface=cli#view-and-manage-lifecycle-hooks-with-hooks)).

Codex 0.149.0 stores this state under exact `hooks.state` keys. Its App Server reference shows a stable generic `config/batchWrite` request that upserts `{enabled: false}` and writes user configuration; there is no `hooks/config/write` method ([tagged App Server reference](https://github.com/openai/codex/blob/rust-v0.149.0/codex-rs/app-server/README.md#L1961-L2036)). The locally generated stable `ClientRequest` schema contains `hooks/list`, `config/value/write`, and `config/batchWrite`, but no hook-specific write request.

Because `ThreadStartParams.config` is an open request-override map, an exact `hooks.state` table can technically be supplied as session config. That is not a supported hook-name/source selection contract: keys encode source identity plus positional event/group/handler selectors, discovery can change, managed hooks ignore user entries, and `hooks/list` has no thread/config preview parameter. Ferry should preserve this as Codex-owned state rather than expose or translate it.

### Discovery, inspection, and layer semantics

Hook sources are additive: all matching hooks from all active sources run; a higher-precedence config layer does not replace lower-precedence hook declarations. Within one layer, `hooks.json` and inline `[hooks]` are merged and trigger a warning ([Hook discovery](https://learn.chatgpt.com/docs/hooks#where-codex-looks-for-hooks)). This hook-specific accumulation rule is different from an ordinary scalar override such as `features.hooks`.

Stable `hooks/list` is useful for inventory, not proof of a thread-local selector. The 0.149.0 generated response schema exposes `enabled`, `eventName`, `key`, `source`, `sourcePath`, `isManaged`, `currentHash`, and `trustStatus`; its params contain only `cwds`. Codex explicitly returns disabled hooks so clients can render and re-enable them ([tagged App Server reference](https://github.com/openai/codex/blob/rust-v0.149.0/codex-rs/app-server/README.md#L1961-L2012)). Thus “the list is non-empty” does not mean hooks will execute, and `hooks/list` cannot directly inspect a specific loaded thread's raw config override.

## Skills

### Configuration granularity

Official documentation supports disabling a local skill with `[[skills.config]]`, using an exact path and `enabled=false` ([Build skills](https://learn.chatgpt.com/docs/build-skills#enable-or-disable-local-codex-skills), [`skills.config` field table](https://learn.chatgpt.com/docs/config-file/config-reference#skillsconfig)).

Codex 0.149.0 source is more precise:

- each rule selects exactly one `path` or `name` and carries `enabled`;
- `skills.bundled.enabled` controls bundled skills only and defaults to true;
- `skills.include_instructions` controls only the automatic skills instruction block;
- user and session layers contribute ordered rules, and later matching rules override earlier ones.

See [`SkillsConfig` and rule resolution](https://github.com/openai/codex/blob/rust-v0.149.0/codex-rs/config/src/skills_config.rs#L18-L58) and [user/session layer handling](https://github.com/openai/codex/blob/rust-v0.149.0/codex-rs/config/src/skills_config.rs#L84-L185). There is no wildcard, allowlist, or single all-skills boolean in that configuration type. An empty `skills.config` means no per-skill overrides, not “disable all.”

### App Server and SDK surfaces

Stable App Server provides:

- `skills/list`: list skills for one or more `cwd` values, including effective `enabled` state; supports `forceReload`.
- `skills/config/write`: persist one name/path enablement rule; the 0.149.0 stable schema accepts `name` or `path` plus `enabled` and returns `effectiveEnabled`.
- `skills/extraRoots/set`: replace process-level extra standalone roots without persistence.
- no `skills/read` request. `plugin/skill/read` is a different method for reading remote plugin skill Markdown.

The current documentation is [App Server: Skills](https://learn.chatgpt.com/docs/app-server#skills) and [API overview](https://learn.chatgpt.com/docs/app-server#api-overview). The locally generated 0.149.0 stable `ClientRequest` schema independently contains `skills/list`, `skills/extraRoots/set`, `skills/config/write`, and `plugin/skill/read`, but not `skills/read`.

The installed `openai-codex` 0.147.0 package generates protocol models for these requests, but its public high-level `Codex`/`AsyncCodex` methods do not include hook, skill, or config-management calls. Its documented/exported entry surface centers on threads and turns ([SDK package exports](https://github.com/openai/codex/blob/rust-v0.147.0/sdk/python/src/openai_codex/__init__.py#L1-L93)); protocol model availability is not the same as a high-level SDK method.

## Product consequence

Ferry should keep the product configuration shallow:

| Ferry policy | Default | Translation |
| --- | --- | --- |
| `worker_hooks = "disabled"` | Yes | `thread_start/resume(config={"features": {"hooks": false}})` |
| `worker_hooks = "inherit"` | No | Omit Ferry's hook override; Codex owns effective hook loading and state. |
| `worker_skills = "inherit"` | Yes | Omit skill overrides; Codex owns skill discovery and enablement. |

Do not add Ferry hook/skill names, source filters, duplicated trust state, or persistent config writes. Capability validation should check that the installed stable `ThreadStartParams` and `ThreadResumeParams` accept an open `config` object; if not, fail closed with the observed Codex/SDK version and schema cause.

## Local verification commands

The stable schema was regenerated directly from the installed official binary:

```text
codex --version
# codex-cli 0.149.0
codex app-server generate-json-schema --out <temporary-directory>
```

The installed SDK version and public methods were inspected with its own environment:

```text
openai-codex 0.147.0
Codex public methods: account, close, login_*, logout, models,
  thread_archive, thread_fork, thread_list, thread_resume, thread_start,
  thread_unarchive
```

No product files, user configuration, hook state, or skill state were modified by this research.
