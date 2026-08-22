"""Nonzero contract checks through the same STDIO MCP protocol used by Codex."""

from __future__ import annotations

import asyncio
import ast
import tempfile
import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


ROOT = Path(__file__).resolve().parents[1]
ERRLOG = tempfile.TemporaryFile(mode="w+")


@asynccontextmanager
async def connected(extra_env: dict[str, str] | None = None):
    environment = os.environ.copy()
    if extra_env:
        environment.update(extra_env)
    params = StdioServerParameters(command=sys.executable, args=["-m", "tests.fake_server"], cwd=ROOT, env=environment)
    async with stdio_client(params, errlog=ERRLOG) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def call(session: ClientSession, name: str, **arguments: object) -> dict:
    result = await session.call_tool(name, arguments)
    return json.loads(result.content[0].text)


async def main() -> None:
    async with connected() as session:
            tools = await session.list_tools()
            assert {tool.name for tool in tools.tools} == {
                "worker_start", "worker_wait", "worker_steer", "worker_interrupt", "worker_follow_up"}

            invalid = await call(session, "worker_start", cwd="relative", provider="openai", brief="x")
            assert invalid["error"]["code"] == "INVALID_CWD"
            mismatch = await call(session, "worker_start", cwd=str(ROOT), provider="mismatch", brief="x")
            assert mismatch["error"]["code"] == "PROVIDER_MISMATCH"
            model_mismatch = await call(session, "worker_start", cwd=str(ROOT), provider="openai", model="mismatch-model", brief="x")
            assert model_mismatch["error"]["code"] == "MODEL_MISMATCH"

            start = await call(session, "worker_start", cwd=str(ROOT), provider="openai", brief="x")
            assert start["ok"]
            collision = await call(session, "worker_start", cwd=str(ROOT), provider="openai", brief="x")
            assert collision["error"]["code"] == "ACTIVE_TURN_EXISTS"
            before=asyncio.get_running_loop().time()
            active = await call(session, "worker_wait", thread_id=start["thread_id"], turn_id=start["turn_id"], timeout_ms=100, max_events=16)
            assert active["status"] == "active"
            assert asyncio.get_running_loop().time()-before < 0.5
            steered = await call(session, "worker_steer", thread_id=start["thread_id"], turn_id=start["turn_id"], correction="finish")
            assert steered["ok"]
            terminal = await call(session, "worker_wait", thread_id=start["thread_id"], turn_id=start["turn_id"], timeout_ms=10, max_events=4)
            assert terminal["status"] == "terminal"
            follow = await call(session, "worker_follow_up", thread_id=start["thread_id"], provider="openai", cwd=str(ROOT), brief="next")
            assert follow["ok"] and follow["thread_id"] == start["thread_id"]
            pending = await call(session, "worker_wait", thread_id=follow["thread_id"], turn_id=follow["turn_id"], timeout_ms=20, max_events=2)
            assert pending["status"] == "active"
            interrupted = await call(session, "worker_interrupt", thread_id=follow["thread_id"], turn_id=follow["turn_id"])
            assert interrupted["status"] == "interrupt_requested"
            stopped = await call(session, "worker_wait", thread_id=follow["thread_id"], turn_id=follow["turn_id"], timeout_ms=10, max_events=4)
            assert stopped["status"] == "terminal"
            idle_backlog = await call(session, "worker_start", cwd=str(ROOT), provider="openai", brief="idle-backlog")
            backlog = await call(session, "worker_wait", thread_id=idle_backlog["thread_id"], turn_id=idle_backlog["turn_id"], timeout_ms=10, max_events=1)
            assert backlog["status"] == "terminal_pending" and len(backlog["events"]) == 1
            drained = await call(session, "worker_wait", thread_id=idle_backlog["thread_id"], turn_id=idle_backlog["turn_id"], timeout_ms=10, max_events=4)
            assert drained["status"] == "terminal" and drained["native_status"] == "completed"
            read_failure = await call(session, "worker_start", cwd=str(ROOT), provider="openai", brief="native-read-failure")
            failed_read = await call(session, "worker_wait", thread_id=read_failure["thread_id"], turn_id=read_failure["turn_id"], timeout_ms=10, max_events=1)
            assert failed_read["error"]["code"] == "SDK_OPERATION_FAILED"
            assert failed_read["error"]["cause_type"] == "RuntimeError"
            assert failed_read["error"]["cause"] == "controlled native thread read failure"
            assert [event["method"] for event in failed_read["events"]] == ["turn/started"]
            await call(session, "worker_interrupt", thread_id=read_failure["thread_id"], turn_id=read_failure["turn_id"])
            read_failure_terminal = await call(session, "worker_wait", thread_id=read_failure["thread_id"], turn_id=read_failure["turn_id"], timeout_ms=10, max_events=4)
            assert read_failure_terminal["status"] == "terminal"
            assert [event["method"] for event in read_failure_terminal["events"]] == ["turn/completed"]
            freshness = await call(session, "worker_start", cwd=str(ROOT), provider="openai", brief="liveness-transition")
            transitioned = await call(session, "worker_wait", thread_id=freshness["thread_id"], turn_id=freshness["turn_id"], timeout_ms=100, max_events=2)
            assert transitioned["status"] == "terminal_pending"
            transitioned_terminal = await call(session, "worker_wait", thread_id=freshness["thread_id"], turn_id=freshness["turn_id"], timeout_ms=10, max_events=4)
            assert transitioned_terminal["status"] == "terminal"
            stalled_read = await call(session, "worker_start", cwd=str(ROOT), provider="openai", brief="native-read-timeout")
            before = asyncio.get_running_loop().time()
            liveness_timeout = await call(session, "worker_wait", thread_id=stalled_read["thread_id"], turn_id=stalled_read["turn_id"], timeout_ms=100, max_events=1)
            assert liveness_timeout["error"]["code"] == "NATIVE_LIVENESS_TIMEOUT"
            assert [event["method"] for event in liveness_timeout["events"]] == ["turn/started"]
            assert asyncio.get_running_loop().time() - before < 0.3
            repeated_timeout = await call(session, "worker_wait", thread_id=stalled_read["thread_id"], turn_id=stalled_read["turn_id"], timeout_ms=1, max_events=1)
            assert repeated_timeout["error"]["code"] == "NATIVE_LIVENESS_TIMEOUT"
            released_interrupt = await call(session, "worker_interrupt", thread_id=stalled_read["thread_id"], turn_id=stalled_read["turn_id"])
            assert released_interrupt["status"] == "interrupt_requested"
            stalled_terminal = await call(session, "worker_wait", thread_id=stalled_read["thread_id"], turn_id=stalled_read["turn_id"], timeout_ms=10, max_events=4)
            assert stalled_terminal["status"] == "terminal"
            assert [event["method"] for event in stalled_terminal["events"]] == ["turn/completed"]
            concurrent = await asyncio.gather(
                call(session, "worker_start", cwd=str(ROOT), provider="openai", brief="concurrent-a"),
                call(session, "worker_start", cwd=str(ROOT), provider="openai", brief="concurrent-b"),
            )
            winner = next(item for item in concurrent if item["ok"])
            assert sum(item["ok"] for item in concurrent) == 1
            assert sum(item.get("error", {}).get("code") == "ACTIVE_TURN_EXISTS" for item in concurrent) == 1
            await call(session, "worker_interrupt", thread_id=winner["thread_id"], turn_id=winner["turn_id"])
            await call(session, "worker_wait", thread_id=winner["thread_id"], turn_id=winner["turn_id"], timeout_ms=10, max_events=4)
            failed_terminal = await call(session, "worker_start", cwd=str(ROOT), provider="openai", brief="failed-terminal")
            native_failure = await call(session, "worker_wait", thread_id=failed_terminal["thread_id"], turn_id=failed_terminal["turn_id"], timeout_ms=10, max_events=4)
            assert native_failure["error"]["code"] == "TURN_FAILED"
            assert native_failure["error"]["native_error"] == "{'message': 'native failed cause'}"
            assert [event["method"] for event in native_failure["events"]] == ["turn/started", "turn/completed"]
            missing_terminal = await call(session, "worker_start", cwd=str(ROOT), provider="openai", brief="missing-terminal")
            missing_status = await call(session, "worker_wait", thread_id=missing_terminal["thread_id"], turn_id=missing_terminal["turn_id"], timeout_ms=10, max_events=4)
            assert missing_status["error"]["code"] == "TURN_FAILED"
            assert [event["method"] for event in missing_status["events"]] == ["turn/started", "turn/completed"]
            cleanup_failure = await call(session, "worker_start", cwd=str(ROOT), provider="openai", brief="cleanup-failure")
            failed_cleanup = await call(session, "worker_wait", thread_id=cleanup_failure["thread_id"], turn_id=cleanup_failure["turn_id"], timeout_ms=10, max_events=4)
            assert failed_cleanup["error"]["code"] == "SDK_OPERATION_FAILED"
            assert failed_cleanup["error"]["cause"] == "controlled terminal cleanup failure"
            assert [event["method"] for event in failed_cleanup["events"]] == ["turn/started", "turn/completed"]
            unexpected = await call(session, "worker_start", cwd=str(ROOT), provider="openai", brief="unexpected-status")
            unexpected_status = await call(session, "worker_wait", thread_id=unexpected["thread_id"], turn_id=unexpected["turn_id"], timeout_ms=10, max_events=1)
            assert unexpected_status["error"]["code"] == "UNEXPECTED_NATIVE_THREAD_STATUS"
            assert [event["method"] for event in unexpected_status["events"]] == ["turn/started"]
            await call(session, "worker_interrupt", thread_id=unexpected["thread_id"], turn_id=unexpected["turn_id"])
            unexpected_terminal = await call(session, "worker_wait", thread_id=unexpected["thread_id"], turn_id=unexpected["turn_id"], timeout_ms=10, max_events=4)
            assert [event["method"] for event in unexpected_terminal["events"]] == ["turn/completed"]
            huge = await call(session, "worker_start", cwd=str(ROOT), provider="openai", brief="huge-terminal")
            huge_terminal = await call(session, "worker_wait", thread_id=huge["thread_id"], turn_id=huge["turn_id"], timeout_ms=10, max_events=4)
            assert huge_terminal["native_status"] == "completed" and len(huge_terminal["final_response"]) <= 4_110
            assert huge_terminal["final_response_verification"] == "terminal-payload"
            abandoned = await call(session, "worker_start", cwd=str(ROOT), provider="openai", brief="abandon")
            await call(session, "worker_interrupt", thread_id=abandoned["thread_id"], turn_id=abandoned["turn_id"])
            await call(session, "worker_wait", thread_id=abandoned["thread_id"], turn_id=abandoned["turn_id"], timeout_ms=10, max_events=4)
            failed = await call(session, "worker_start", cwd=str(ROOT), provider="openai", brief="failure")
            failure = await call(session, "worker_wait", thread_id=failed["thread_id"], turn_id=failed["turn_id"], timeout_ms=10, max_events=4)
            assert failure["error"]["code"] == "SDK_OPERATION_FAILED"
            assert [event["method"] for event in failure["events"]] == ["turn/started"]
            occupied = await call(session, "worker_start", cwd=str(ROOT), provider="openai", brief="must-not-start")
            assert occupied["error"]["code"] == "ACTIVE_TURN_EXISTS"
            recovered = await call(session, "worker_interrupt", thread_id=failed["thread_id"], turn_id=failed["turn_id"])
            assert recovered["ok"]
    async with connected() as restarted:
        lost = await call(restarted, "worker_steer", thread_id=abandoned["thread_id"], turn_id=abandoned["turn_id"], correction="x")
        assert lost["error"]["code"] == "LIVE_HANDLE_UNAVAILABLE"
        resumed = await call(restarted, "worker_follow_up", thread_id=start["thread_id"], provider="openai", cwd=str(ROOT), brief="after restart")
        assert resumed["ok"] and resumed["thread_id"] == start["thread_id"]
    async with connected({"FERRY_FAKE_BROKEN_ADVISORY": "1"}) as optional_advisory_failure:
        assert len((await optional_advisory_failure.list_tools()).tools) == 5
    ERRLOG.seek(0)
    assert "controlled terminal stream failure" in ERRLOG.read()
    count=sum(isinstance(node, ast.Assert) for node in ast.walk(ast.parse(Path(__file__).read_text())))
    print(f"mcp contract: {count} assert statements passed")


if __name__ == "__main__":
    asyncio.run(main())
