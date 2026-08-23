# Ferry

<p align="center">
  <strong>保留 Codex，降低成本。</strong>
</p>

<p align="center">
  <a href="README.md">English</a> · 简体中文
</p>

<p align="center">
  <a href="https://pypi.org/project/ferry-codex/"><img alt="PyPI" src="https://img.shields.io/pypi/v/ferry-codex"></a>
</p>

Ferry 让 Codex 把边界明确的实现任务委派给你已经配置好的 custom model。主
Codex session 保留项目上下文、控制工作并作出最终判断。

## 安装

最简单的方式是让 Codex 完成 Ferry setup。把这句话粘贴给 Codex：

```text
Read https://raw.githubusercontent.com/PunkGo/ferry/main/README.md and https://raw.githubusercontent.com/PunkGo/ferry/main/CUSTOM_PROVIDER_SETUP.md. Configure and verify my custom provider first, then install Ferry using the recommended path.
```

Ferry 用来把 Codex 工作委派给 custom provider 和 model。如果你只需要 Codex
原生 worker，直接使用 Codex 自带的 worker 即可。

安装 Ferry 前，请先[配置并验证 custom provider](#使用-custom-provider)。它的
provider、model 和认证必须已经能在 Codex 中正常工作。

如果选择手动安装，需要 Python 3.10+、已经安装的 Codex CLI，以及 `uv`（推荐）
或 `pipx`。

Ferry 只能选择一个 package manager；默认路径是 `uv tool`：

```sh
uv tool install ferry-codex
ferry setup
```

`pipx` 仍是支持的替代方案；不要让两个 manager 同时安装同一个 Ferry package。

```sh
pipx install ferry-codex
ferry setup
```

随后启动一个新的 Codex session，并执行同一真实 seam 的 readiness check：

```text
Run Ferry Doctor for my configured custom provider and model in this project. Keep it read-only, test the real coding-tool lifecycle, and explain any BLOCKED result by owner.
```

Ferry 复用宿主 `codex` executable；它不打包 Python，也不会安装第二份 Codex CLI。

## 使用

Custom provider 在 Codex 中跑通后，直接用自然语言告诉 Codex 即可，不需要学习
Ferry worker 命令。

```text
使用 Ferry，把这个边界明确的实现任务交给我已经配置好的 DeepSeek provider。
当前 Codex thread 继续担任 lead，并独立验证最终 diff 和测试。
```

在同一段对话里纠正或停止 worker：

```text
Steer Ferry worker：保留 public API，并把改动限制在 src/parser.py。
```

```text
现在 interrupt Ferry worker。
```

Worker report 只是交付数据。Codex 会检查真实 worktree，并执行真正的验收命令，
然后才决定是否接受。

## 为什么需要 Ferry

前沿模型值得用在困难推理、规划和审查上，但边界明确的实现任务不一定都需要
最昂贵的模型。

Ferry 把判断权留在 Codex，让成本更低的 custom model 完成聚焦的执行工作。
Codex 随后检查真实 diff、执行检查，并决定接受、steer、返工、interrupt 或停止。

> **Ferry work, not judgment. 把工作运出去，不把判断权交出去。**

![Codex 担任 lead，Ferry 将边界明确的工作交给原生或 custom-model worker](diagrams/ferry-cost-control.svg)

## 使用 custom provider

Ferry 不配置模型、endpoint、认证或凭证。Provider、model 和认证必须先在 Codex
中正常工作，Ferry 才会使用它们。请遵循 Codex 官方的
[custom provider 配置教程](https://learn.chatgpt.com/docs/config-file/config-advanced#custom-model-providers)。

明确请求的 provider 缺失、配置错误，或 native identity 不一致时，Ferry 绝不会
静默换成 owner model。

## 管理集成

```sh
ferry status
```

升级或卸载前，先关闭所有正在使用 Ferry 的 Codex session。

```sh
uv tool upgrade ferry-codex && ferry setup
```

```sh
ferry uninstall && uv tool uninstall ferry-codex
```

使用受支持的 `pipx` 替代方案时，执行：

```sh
pipx upgrade ferry-codex && ferry setup
```

```sh
ferry uninstall && pipx uninstall ferry-codex
```

这些命令只管理 Ferry package 和 Codex plugin 集成，不会删除 Codex threads、
provider 配置、凭证或项目文件。

## 支持与安全

Ferry 已经为 native worker、OpenAI、DeepSeek、steer、interrupt、uv/pipx 生命周期和
Windows 路径保存了带版本边界的 conformance evidence。精确测试矩阵见
[SUPPORT.md](SUPPORT.md)。

安全问题请通过 [SECURITY.md](SECURITY.md) 报告。参与贡献前请阅读
[CONTRIBUTING.md](CONTRIBUTING.md)。

## License

[MIT](LICENSE)
