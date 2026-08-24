"""STDIO entrypoint. The only runtime dependency surface is MCP + openai-codex."""

from __future__ import annotations

import shutil
import os
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Annotated, Any, Callable

from mcp.server import MCPServer
from openai_codex import ApprovalMode, AsyncCodex, CodexConfig, Sandbox
from pydantic import Field

from . import __version__
from .adapter import (ALLOWED_HOOK_POLICIES, ALLOWED_SANDBOXES, ALLOWED_SKILL_POLICIES,
                      MAX_EVENTS, MAX_TEXT, MAX_WAIT_MS, FerryAdapter)
from .advisory import UpdateAdvisory


ThreadId = Annotated[str, Field(json_schema_extra={"minLength": 1, "maxLength": MAX_TEXT},
    description=f"Exact non-whitespace thread ID returned by start or follow-up, at most {MAX_TEXT} characters.")]
TurnId = Annotated[str, Field(json_schema_extra={"minLength": 1, "maxLength": MAX_TEXT},
    description=f"Exact non-whitespace current turn ID returned by start or follow-up, at most {MAX_TEXT} characters.")]
Cwd = Annotated[str, Field(json_schema_extra={"minLength": 1, "maxLength": MAX_TEXT},
    description=f"Non-whitespace existing absolute worktree directory, at most {MAX_TEXT} characters.")]
Provider = Annotated[str, Field(json_schema_extra={"minLength": 1, "maxLength": MAX_TEXT},
    description=f"Non-whitespace configured provider name, at most {MAX_TEXT} characters.")]
Model = Annotated[str, Field(json_schema_extra={"minLength": 1, "maxLength": MAX_TEXT},
    description=f"Non-whitespace configured model name when supplied, at most {MAX_TEXT} characters.")]
Brief = Annotated[str, Field(json_schema_extra={"minLength": 1, "maxLength": MAX_TEXT},
    description=f"Non-whitespace bounded worker brief, at most {MAX_TEXT} characters.")]
Correction = Annotated[str, Field(json_schema_extra={"minLength": 1, "maxLength": MAX_TEXT},
    description=f"Non-whitespace correction for the exact active turn, at most {MAX_TEXT} characters.")]
SandboxName = Annotated[str, Field(json_schema_extra={"enum": list(ALLOWED_SANDBOXES)},
    description="Sandbox for the next start or follow-up; one of the supported modes.")]
HookPolicy = Annotated[str, Field(json_schema_extra={"enum": list(ALLOWED_HOOK_POLICIES)},
    description="Worker hook policy: disabled (default) sends native thread config features.hooks=false to avoid inherited hook execution; inherit omits that override so Codex's effective hook configuration and per-hook trust/enablement apply. Concrete hook selection remains Codex-owned.")]
SkillPolicy = Annotated[str, Field(json_schema_extra={"enum": list(ALLOWED_SKILL_POLICIES)},
    description="Worker skill policy: inherit (default) retains Codex automatic skill instructions; disabled sends native thread config skills.include_instructions=false to suppress them and reduce worker context. Concrete skill selection remains Codex-owned.")]
TimeoutMs = Annotated[int, Field(json_schema_extra={"minimum": 1, "maximum": MAX_WAIT_MS},
    description="Milliseconds for one bounded wait; reserves native-liveness time.")]
MaxEvents = Annotated[int, Field(json_schema_extra={"minimum": 1, "maximum": MAX_EVENTS},
    description="Retained events returned by one wait.")]
FailureGuidance = "On ok:false inspect error.code, error.operation, error.message, optional error.cause, and top-level events."
PolicyGuidance = "Policies: hook_policy disabled (default) avoids inherited worker hook execution; inherit leaves effective Codex hooks and per-hook trust/enablement. skill_policy inherit (default) retains automatic skill instructions; disabled suppresses them to reduce worker context. Concrete hook and skill selection remains Codex-owned; inspect the schema for exact modes."


def _sandbox(name: str) -> Sandbox:
    return {
        "read-only": Sandbox.read_only,
        "workspace-write": Sandbox.workspace_write,
        "danger-full-access": Sandbox.full_access,
    }[name]


def _production_adapter() -> FerryAdapter:
    configured = os.environ.get("FERRY_CODEX_BIN")
    codex_bin = configured or shutil.which("codex")
    if codex_bin is None or not Path(codex_bin).is_absolute() or not Path(codex_bin).is_file():
        raise RuntimeError("HOST_CODEX_UNAVAILABLE: host codex executable was not found on PATH")
    return FerryAdapter(AsyncCodex(CodexConfig(codex_bin=codex_bin)), _sandbox,
                        approval_mode=ApprovalMode.deny_all, service_name="ferry")


def create_server(adapter_factory: Callable[[], FerryAdapter] = _production_adapter,
                  advisory_factory: Callable[[], UpdateAdvisory] | None = None) -> MCPServer[Any]:
    state: dict[str, FerryAdapter] = {}

    @asynccontextmanager
    async def lifespan(_: MCPServer[Any]):
        adapter = adapter_factory()
        state["adapter"] = adapter
        advisory: UpdateAdvisory | None = None
        try:
            try:
                advisory = (advisory_factory or (lambda: UpdateAdvisory(
                    os.environ.get("FERRY_BUILD_VERSION", __version__).split("+", 1)[0])))()
                await advisory.start()
            except BaseException:
                if advisory is not None:
                    try:
                        await advisory.close()
                    except BaseException:
                        pass
                advisory = None
            if advisory is not None:
                state["advisory"] = advisory
            yield adapter
        finally:
            try:
                if advisory is not None:
                    try:
                        await advisory.close()
                    except BaseException:
                        pass
                await adapter.close()
            finally:
                state.pop("adapter", None)
                state.pop("advisory", None)

    server = MCPServer("ferry", version=os.environ.get("FERRY_BUILD_VERSION", __version__), instructions=(
        "Lifecycle: worker_start, then worker_wait; optionally steer or interrupt only after that exact turn is active; "
        "observe terminal before worker_follow_up on the same thread. Policy overview: hook_policy defaults disabled to avoid inherited hooks; "
        "skill_policy defaults inherit to retain automatic skill instructions; concrete selection remains Codex-owned. "
        "Inspect the worker_start and worker_follow_up schemas for defaults and tradeoffs. " + FailureGuidance),
                       lifespan=lifespan)

    def adapter() -> FerryAdapter:
        if "adapter" not in state:
            raise RuntimeError("LIFECYCLE_UNAVAILABLE: Ferry MCP lifecycle did not initialize")
        return state["adapter"]

    def response(result: dict[str, Any]) -> dict[str, Any]:
        advisory = state.get("advisory")
        return advisory.add_to(result) if advisory is not None else result


    @server.tool(description="Start one explicit alternate-provider turn; returns starting, so call worker_wait before live control. " + PolicyGuidance + " " + FailureGuidance)
    async def worker_start(cwd: Cwd, provider: Provider, brief: Brief, model: Model | None = None,
                           sandbox: SandboxName = "read-only", hook_policy: HookPolicy = "disabled",
                           skill_policy: SkillPolicy = "inherit") -> dict[str, Any]:
        return response(await adapter().worker_start(cwd, provider, brief, model, sandbox,
                                                     hook_policy, skill_policy))


    @server.tool(description="Consume one bounded stream segment; control only after this exact turn reports active, and follow-up only after terminal. " + FailureGuidance)
    async def worker_wait(thread_id: ThreadId, turn_id: TurnId, timeout_ms: TimeoutMs = 500,
                          max_events: MaxEvents = 1) -> dict[str, Any]:
        return response(await adapter().worker_wait(thread_id, turn_id, timeout_ms, max_events))


    @server.tool(description="Steer the exact currently-live turn only after worker_wait reports active; preserve a native control failure. " + FailureGuidance)
    async def worker_steer(thread_id: ThreadId, turn_id: TurnId, correction: Correction) -> dict[str, Any]:
        return response(await adapter().worker_steer(thread_id, turn_id, correction))


    @server.tool(description="Interrupt the exact currently-live turn only after worker_wait reports active; use only a real stop or redirect. " + FailureGuidance)
    async def worker_interrupt(thread_id: ThreadId, turn_id: TurnId) -> dict[str, Any]:
        return response(await adapter().worker_interrupt(thread_id, turn_id))


    @server.tool(description="Start the next turn on the exact same thread only after terminal completion is observed. " + PolicyGuidance + " " + FailureGuidance)
    async def worker_follow_up(thread_id: ThreadId, provider: Provider, brief: Brief, cwd: Cwd,
                               model: Model | None = None, sandbox: SandboxName = "read-only",
                               hook_policy: HookPolicy = "disabled",
                               skill_policy: SkillPolicy = "inherit") -> dict[str, Any]:
        return response(await adapter().worker_follow_up(thread_id, provider, brief, cwd, model, sandbox,
                                                         hook_policy, skill_policy))
    return server


server = create_server()


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
