# Support and proof matrix

Ferry is pre-release. Each row describes only the exact seam, runtime, and platform observed.

| Path | Platform | Runtime | Result |
| --- | --- | --- | --- |
| Native built-in worker | macOS | Codex 0.149.0 | Proved: spawn, wait, same-thread follow-up, worktree binding, and bounded interrupt; the canonical worker reached native `interrupted` without repository mutation |
| SDK → App Server → DeepSeek | macOS | `openai-codex` 0.147.0 + Codex 0.149.0 | Proved: explicit provider and two nonce turns on one thread |
| SDK live steer and interrupt | macOS arm64 | Codex 0.149.0 + `openai-codex` 0.147.0 + MCP 2.0.0 + Python 3.14.6 | Proved through the installed product MCP after the native-liveness repair: bounded OpenAI and DeepSeek steer completed; bounded OpenAI and DeepSeek interrupt reached native `interrupted` |
| pipx distribution and installed lifecycle | macOS arm64 + Windows x64 | Codex 0.149.0 + Python 3.13.12 + pipx 1.16.7 + `openai-codex` 0.147.0 + Ferry `0.1.0+44b9f226d4eb` | Proved: final cutover artifacts and lifecycle; the installed provider call remains proved on the pre-cutover `0.1.0+8cf98cf0cca6` artifact; two-version upgrade, owner calls, and installed-entry advisory faults passed |

The custom-provider proof ran in a disposable Python environment and used the local Codex binary. The SDK exposed `thread_start(model_provider=...)`, `Thread.run/read/compact`, and `TurnHandle.stream/steer/interrupt`. A read-only DeepSeek thread returned `SDK_DEEPSEEK_SPAWN_OK` and `SDK_DEEPSEEK_FOLLOWUP_OK` on the same native thread. No credential was printed and Git did not change.

## Runtime requirements

- Codex native worker support for the default path;
- the official stable `openai-codex` SDK and a supported Codex/App Server runtime for an alternate-provider path;
- machine-local Codex provider/model/auth configuration for the explicitly requested provider;
- Git and repository-specific verification tools when the task requires them.

Ferry owns no provider credential, provider configuration, daemon, database, or durable task state.

## Install and uninstall

Python 3.10+, pipx, and a host `codex` CLI are prerequisites. Ferry's only public
installation path is:

```sh
pipx install ferry-codex
ferry setup
```

Start a fresh Codex session before use. Setup installs the exact SDK pin without
`openai-codex-cli-bin` in the pipx application environment and registers
`ferry@ferry` through official Codex commands.

Close every Ferry-using Codex session before `ferry uninstall && pipx uninstall
ferry-codex`. This does not delete Codex threads, provider configuration, or
credentials. Distribution gates are proved; publication remains an explicit
operator-controlled action.
