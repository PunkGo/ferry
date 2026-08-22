# Contributing

Ferry is intentionally a small Codex Skill bundle that composes native
workers, the official Codex SDK/App Server, and the existing worker-brief
pattern. Changes should make that composition clearer or safer without
introducing a second scheduler, configuration owner, protocol, or lifecycle.

Before proposing a change:

1. read `ARCHITECTURE.md` and preserve its ownership boundaries;
2. update `plugins/ferry/skills/ferry/SKILL.md` when behavior changes;
3. reuse `plugins/ferry/skills/ferry/references/worker-brief.md` and the official SDK rather than adding a
   competing packet schema or App Server client;
4. keep machine-local models, providers, endpoints, and credentials out of the
   repository;
5. add or update a behavioral case under `evals/` when observable behavior
   changes;
6. run the current Skill validator, parse checked-in TOML, and run the relevant
   case through a fresh Codex session in a disposable Git repository;
7. report the exact Codex and SDK versions, platform, selected route/provider,
   native thread id, executed test count, and unresolved capabilities.

Do not commit generated session history, temporary worktrees, or provider
secrets. Do not report a case as passing when it ran
zero tests or bypassed the native worker seam.

An SDK-backed adapter is acceptable only for the measured alternate-provider
owner-call seam. It must forward official SDK operations, preserve typed causes,
and contain no durable task state or process supervision.

The project is licensed under MIT. By contributing, you agree that your
contribution is provided under the same license.
