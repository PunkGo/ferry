# Set up a Codex custom provider for Ferry

1. Identify the provider and model the user wants. Ask only if either is unclear.
2. Read the current official
   [Codex custom-provider documentation](https://learn.chatgpt.com/docs/config-file/config-advanced#custom-model-providers),
   then inspect the installed Codex runtime and version. Use the current
   documentation and runtime rather than a copied provider schema.
3. Confirm that the provider exposes the Responses API required by Codex.
   Configure only Codex-owned user settings and authentication. Keep the
   provider and authentication needed by Ferry visible from the base
   `~/.codex/config.toml`, not only a profile. Do not edit Ferry or project files,
   and never put a plaintext credential in TOML or output.
4. Run one minimal no-mutation Codex smoke without `--profile`. Verify the exact
   provider, model, authentication, and Responses API path Ferry will use.
   Preserve the exact cause if any check fails.
5. Report `Ferry prerequisite satisfied` only after verification succeeds.
   Include the provider, model, and a secret-free verification result.

Ferry does not own provider, endpoint, model, or credential configuration.
