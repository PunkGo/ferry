"""STDIO entrypoint. The only runtime dependency surface is MCP + openai-codex."""

from __future__ import annotations

import shutil
import os
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Any, Callable

from mcp.server import MCPServer
from openai_codex import ApprovalMode, AsyncCodex, CodexConfig, Sandbox

from . import __version__
from .adapter import FerryAdapter
from .advisory import UpdateAdvisory


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

    server = MCPServer("ferry", version=os.environ.get("FERRY_BUILD_VERSION", __version__), instructions="Explicit alternate-provider Codex worker control.",
                       lifespan=lifespan)

    def adapter() -> FerryAdapter:
        if "adapter" not in state:
            raise RuntimeError("LIFECYCLE_UNAVAILABLE: Ferry MCP lifecycle did not initialize")
        return state["adapter"]

    def response(result: dict[str, Any]) -> dict[str, Any]:
        advisory = state.get("advisory")
        return advisory.add_to(result) if advisory is not None else result


    @server.tool(description="Start one explicit alternate-provider worker turn.")
    async def worker_start(cwd: str, provider: str, brief: str, model: str | None = None,
                           sandbox: str = "read-only") -> dict[str, Any]:
        return response(await adapter().worker_start(cwd, provider, brief, model, sandbox))


    @server.tool(description="Consume one bounded native stream segment.")
    async def worker_wait(thread_id: str, turn_id: str, timeout_ms: int = 500,
                          max_events: int = 1) -> dict[str, Any]:
        return response(await adapter().worker_wait(thread_id, turn_id, timeout_ms, max_events))


    @server.tool(description="Steer the one currently-live native turn.")
    async def worker_steer(thread_id: str, turn_id: str, correction: str) -> dict[str, Any]:
        return response(await adapter().worker_steer(thread_id, turn_id, correction))


    @server.tool(description="Interrupt the one currently-live native turn.")
    async def worker_interrupt(thread_id: str, turn_id: str) -> dict[str, Any]:
        return response(await adapter().worker_interrupt(thread_id, turn_id))


    @server.tool(description="Resume a completed native thread and start its next turn.")
    async def worker_follow_up(thread_id: str, provider: str, brief: str, cwd: str,
                               model: str | None = None, sandbox: str = "read-only") -> dict[str, Any]:
        return response(await adapter().worker_follow_up(thread_id, provider, brief, cwd, model, sandbox))
    return server


server = create_server()


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
