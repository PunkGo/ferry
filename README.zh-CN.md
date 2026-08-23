# Ferry

<p align="center">
  <strong>让 Codex 担任 lead，把边界明确的工作交给你自己的模型。</strong>
</p>

<p align="center">
  <a href="README.md">English</a> · 简体中文
</p>

<p align="center">
  <a href="https://pypi.org/project/ferry-codex/"><img alt="PyPI" src="https://img.shields.io/pypi/v/ferry-codex"></a>
</p>

Ferry 为 Codex 增加受控的 worker 委派能力。主 Codex session 保留项目上下文、
界定任务并判断结果；边界明确的执行工作既可以交给 Codex 原生 worker，也可以
交给用户明确选择的 custom model，例如 DeepSeek。

如果你喜欢 Claude Code agent teams 的 lead/worker 使用感，Ferry 把这种委派
模式带到 Codex，并允许 worker 使用你机器上已经配置好的 provider。Ferry 不是
第二套 agent harness，也不是带共享任务列表和 worker 互聊的完整 team runtime。
Codex 始终是 lead 和最终判断者。

> **Ferry work, not judgment. 把工作运出去，不把判断权交出去。**

## 为什么需要 Ferry

前沿模型值得用在困难推理、规划和审查上，但边界明确的实现任务不一定都需要
最昂贵的模型。

Ferry 让你继续使用已经信任的 Codex harness，把昂贵模型能力留给真正需要判断
的环节。成本更低的 custom model 可以完成一个聚焦的改动；随后 Codex 检查真实
diff、执行检查，并决定接受、steer、返工、interrupt 或停止。

![Codex 担任 lead，Ferry 将边界明确的工作交给原生或 custom-model worker](diagrams/ferry-cost-control.svg)

## 安装前：先在 Codex 中跑通 provider

首先按照 Codex 官方的
[custom provider 配置教程](https://developers.openai.com/codex/config-advanced#custom-model-providers)
配置并验证 provider。Ferry 不配置模型、endpoint、认证或凭证；完全相同的
provider、model 和 auth 必须先在 Codex 中正常工作，Ferry 才会使用它们。

想让 Codex 直接完成配置？把这句话粘贴给 Codex：

```text
Read https://raw.githubusercontent.com/PunkGo/ferry/main/CUSTOM_PROVIDER_SETUP.md and set up a Codex custom provider for Ferry for me.
```

### DeepSeek 示例

按照 Codex 教程和 DeepSeek 官方的
[Codex 接入指南](https://api-docs.deepseek.com/zh-cn/quick_start/agent_integrations/codex)
完成配置后，如果基础配置暴露的 provider 名为 `deepseek`，验证 Ferry 将使用的
同一条无 profile seam。如果你的配置使用了其他 model id，请替换示例中的值；
认证由你已配置的 Codex auth 机制提供。

```sh
codex exec -s read-only \
  -c 'model_provider="deepseek"' \
  -m deepseek-v4-pro \
  'Reply with exactly DEEPSEEK_CODEX_OK.'
```

只有这条不带 `--profile` 的命令返回 `DEEPSEEK_CODEX_OK` 后才继续。明确请求的
provider 缺失、配置错误，或 native provider identity 不一致时，Ferry 绝不会
静默换成 owner model。

## 安装

要求：Python 3.10+、已经安装的 Codex CLI，以及 `uv`（推荐）或 `pipx`。

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

随后启动一个新的 Codex session。Ferry 复用宿主 `codex` executable；它不打包
Python，也不会安装第二份 Codex CLI。

## 使用

直接用自然语言告诉 Codex 即可，不需要学习 Ferry worker 命令。

委派给 Codex 原生 worker：

```text
使用 Ferry 把这个边界明确的任务交给原生 worker：更新 parser，运行聚焦测试，
不要修改无关文件。
```

委派给已经在 Codex 中跑通的 DeepSeek provider：

```text
使用 Ferry，把这个边界明确的实现任务交给我已经配置好的 DeepSeek provider 和
deepseek-v4-pro。当前 Codex thread 继续担任 lead，并独立验证最终 diff 和测试。
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
