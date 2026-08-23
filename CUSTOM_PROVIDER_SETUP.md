# Custom-provider setup prompt

Give the following prompt to Codex before using Ferry with a custom provider:

```text
Configure and verify my custom provider for Ferry. First read the current official
Codex custom-provider documentation and inspect the installed Codex runtime and
version. Confirm the provider name, model, Responses-compatible endpoint, and
credential source before changing anything.

Modify only Codex-owned user configuration. Do not edit Ferry or project files.
Do not print, paste, or write a plaintext credential to a file. Do not copy a
static provider schema: use the current official documentation and the installed
runtime instead.

Then prove the requested provider/model through an unprofiled Codex seam (no
`--profile`). Report `Ferry prerequisite satisfied` only after that succeeds,
including the provider/model and a secret-free verification result.
```

Ferry does not own provider, endpoint, model, or credential configuration.
