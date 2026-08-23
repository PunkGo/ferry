# Set up a Codex custom provider for Ferry

1. Identify the provider and model the user wants. Ask only if either is unclear.
2. Read the current official
   [Codex custom-provider documentation](https://developers.openai.com/codex/config-advanced#custom-model-providers),
   then inspect the installed Codex runtime and version. Use the current
   documentation and runtime rather than a copied provider schema.
3. Configure only Codex-owned user settings and authentication. Do not edit Ferry
   or project files, and do not print, paste, or store a plaintext credential.
4. Verify the requested provider and model through the base Codex seam Ferry
   uses, without `--profile`. Preserve the exact cause if configuration,
   authentication, provider identity, or model verification fails.
5. Report `Ferry prerequisite satisfied` only after verification succeeds.
   Include the provider, model, and a secret-free verification result.

Ferry does not own provider, endpoint, model, or credential configuration.
