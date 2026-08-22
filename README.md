# Ferry

<p align="center">
  <strong>Keep Codex as the lead. Delegate bounded work to your own models.</strong>
</p>

<p align="center">
  English · <a href="README.zh-CN.md">简体中文</a>
</p>

<p align="center">
  <a href="https://pypi.org/project/ferry-codex/"><img alt="PyPI" src="https://img.shields.io/pypi/v/ferry-codex"></a>
</p>

Ferry adds controlled worker delegation to Codex. Your main Codex session keeps
the project context, scopes the task, and judges the result. Bounded execution
can stay on a native Codex worker or run on an explicitly selected custom model
such as DeepSeek.

If you like the lead-and-worker feel of Claude Code agent teams, Ferry brings
that delegation pattern to Codex while letting workers use providers already
configured on your machine. Ferry is not a second agent harness or a shared
peer-to-peer team runtime. Codex remains the lead and final judge.

> **Ferry work, not judgment.**

## Why Ferry

Frontier models are worth using for hard reasoning, planning, and review. They
are not always the economical choice for a bounded implementation task.

Ferry lets you keep the Codex harness you already trust and spend expensive
model capacity where judgment matters. A lower-cost custom model can implement
a focused change; Codex then inspects the real diff, runs the checks, and decides
whether to accept, steer, rework, interrupt, or stop.

![Codex leads while Ferry routes bounded work to a native or custom-model worker](diagrams/ferry-cost-control.svg)

## Before you install: prove the provider in Codex

First, follow the official
[Codex custom-provider guide](https://developers.openai.com/codex/config-advanced#custom-model-providers)
to configure and test your provider. Ferry does not configure models, endpoints,
authentication, or credentials. The exact provider, model, and authentication
must already work in Codex before Ferry uses them.

### DeepSeek example

After following the Codex guide, if your working provider is named `deepseek`,
verify it directly through Codex. Replace the model id if your configuration
uses a different one.

```sh
export DEEPSEEK_API_KEY="YOUR_KEY"

codex exec -s read-only \
  -c 'model_provider="deepseek"' \
  -m deepseek-v4-pro \
  'Reply with exactly DEEPSEEK_CODEX_OK.'
```

Continue only after Codex returns `DEEPSEEK_CODEX_OK`. Ferry will never silently
fall back to the owner model when an explicitly requested provider is missing,
misconfigured, or reports a different native provider identity.

## Install

Requirements: Python 3.10+, `pipx`, and an existing Codex CLI installation.

```sh
pipx install ferry-codex
ferry setup
```

Start a fresh Codex session. Ferry reuses your host `codex` executable; it does
not bundle Python or install a second Codex CLI.

## Use

Ask Codex in natural language. There are no Ferry worker commands to learn.

Delegate to a native Codex worker:

```text
Use Ferry to delegate this bounded task to a native worker: update the parser,
run its focused tests, and do not touch unrelated files.
```

Delegate to the DeepSeek provider you already proved in Codex:

```text
Use Ferry with my configured DeepSeek provider and deepseek-v4-pro for this
bounded implementation. Keep this Codex thread as lead and independently verify
the resulting diff and tests.
```

Correct or stop live work in the same conversation:

```text
Steer the Ferry worker: preserve the public API and limit the change to src/parser.py.
```

```text
Interrupt the Ferry worker now.
```

The worker's report is delivery data. Codex checks the actual worktree and runs
the real acceptance commands before accepting it.

## Manage the integration

```sh
ferry status
```

Close every Codex session using Ferry before upgrading or uninstalling.

```sh
pipx upgrade ferry-codex && ferry setup
```

```sh
ferry uninstall && pipx uninstall ferry-codex
```

These commands manage only the Ferry package and Codex plugin integration. They
do not delete Codex threads, provider configuration, credentials, or project
files.

## Support and security

Ferry's native-worker, OpenAI, DeepSeek, steer, interrupt, pipx lifecycle, and
Windows paths have versioned conformance evidence. See [SUPPORT.md](SUPPORT.md)
for the exact tested matrix.

Report security issues through [SECURITY.md](SECURITY.md). Contributions are
welcome after reading [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
