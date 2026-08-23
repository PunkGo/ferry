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
sys.path.insert(0, str(ROOT / "plugins" / "ferry" / "src"))

from ferry_mcp.adapter import ALLOWED_SANDBOXES, MAX_EVENTS, MAX_TEXT, MAX_WAIT_MS, FerryAdapter
from ferry_mcp.server import FailureGuidance, _sandbox
from fake_server import Client


@asynccontextmanager
async def connected(extra_env: dict[str, str] | None = None):
    environment = os.environ.copy()
    if extra_env:
        environment.update(extra_env)
    params = StdioServerParameters(command=sys.executable, args=["-m", "tests.fake_server"], cwd=ROOT, env=environment)
    async with stdio_client(params, errlog=ERRLOG) as (read, write):
        async with ClientSession(read, write) as session:
            initialized = await session.initialize()
            yield session, initialized


async def call(session: ClientSession, name: str, **arguments: object) -> dict:
    result = await session.call_tool(name, arguments)
    return json.loads(result.content[0].text)


async def main() -> None:
    server_ast = ast.parse((ROOT / "plugins" / "ferry" / "src" / "ferry_mcp" / "server.py").read_text())
    assert not any(isinstance(argument, ast.Starred) for subscript in ast.walk(server_ast)
                   if isinstance(subscript, ast.Subscript) for argument in ast.walk(subscript.slice))
    skill_contract = (ROOT / "plugins" / "ferry" / "skills" / "ferry" / "SKILL.md").read_text()
    for instruction in (
        "`worker_wait(timeout_ms=30000, max_events=16)` for ordinary progress and terminal\ndraining",
        "`worker_wait(timeout_ms=30000, max_events=1)` so the first meaningful retained\nevent returns immediately",
        "already-running command completes after control dispatch, its output is allowed\nand that completion alone is not a steer failure",
        "same-turn native acknowledgement, observe the correction as same-turn input,\nand produce the corrected nonce or result in terminal completion",
    ):
        assert instruction in skill_contract
    doctor_steer_contract = skill_contract.split("## Doctor\n", 1)[1].split("\n\nIf a tool continuation fails", 1)[0]
    assert "exclude the original\ncompletion marker" not in doctor_steer_contract
    assert "correction input or effect" not in doctor_steer_contract
    async with connected() as (session, initialized):
            tools = await session.list_tools()
            assert {tool.name for tool in tools.tools} == {
                "worker_start", "worker_wait", "worker_steer", "worker_interrupt", "worker_follow_up"}
            schemas = {tool.name: tool.input_schema for tool in tools.tools}
            assert initialized.instructions is not None and "worker_start, then worker_wait" in initialized.instructions
            assert FailureGuidance in initialized.instructions
            tool_guidance = {
                "worker_start": "returns starting, so call worker_wait before live control",
                "worker_wait": "control only after this exact turn reports active, and follow-up only after terminal",
                "worker_steer": "only after worker_wait reports active",
                "worker_interrupt": "only after worker_wait reports active",
                "worker_follow_up": "only after terminal completion is observed",
            }
            for tool in tools.tools:
                assert tool_guidance[tool.name] in tool.description and FailureGuidance in tool.description
            expected_required = {
                "worker_start": ["cwd", "provider", "brief"],
                "worker_wait": ["thread_id", "turn_id"],
                "worker_steer": ["thread_id", "turn_id", "correction"],
                "worker_interrupt": ["thread_id", "turn_id"],
                "worker_follow_up": ["thread_id", "provider", "brief", "cwd"],
            }
            assert {name: schema["required"] for name, schema in schemas.items()} == expected_required
            text_fields = {
                "worker_start": {"cwd": f"Non-whitespace existing absolute worktree directory, at most {MAX_TEXT} characters.", "provider": f"Non-whitespace configured provider name, at most {MAX_TEXT} characters.", "brief": f"Non-whitespace bounded worker brief, at most {MAX_TEXT} characters.", "model": f"Non-whitespace configured model name when supplied, at most {MAX_TEXT} characters."},
                "worker_wait": {"thread_id": f"Exact non-whitespace thread ID returned by start or follow-up, at most {MAX_TEXT} characters.", "turn_id": f"Exact non-whitespace current turn ID returned by start or follow-up, at most {MAX_TEXT} characters."},
                "worker_steer": {"thread_id": f"Exact non-whitespace thread ID returned by start or follow-up, at most {MAX_TEXT} characters.", "turn_id": f"Exact non-whitespace current turn ID returned by start or follow-up, at most {MAX_TEXT} characters.", "correction": f"Non-whitespace correction for the exact active turn, at most {MAX_TEXT} characters."},
                "worker_interrupt": {"thread_id": f"Exact non-whitespace thread ID returned by start or follow-up, at most {MAX_TEXT} characters.", "turn_id": f"Exact non-whitespace current turn ID returned by start or follow-up, at most {MAX_TEXT} characters."},
                "worker_follow_up": {"thread_id": f"Exact non-whitespace thread ID returned by start or follow-up, at most {MAX_TEXT} characters.", "provider": f"Non-whitespace configured provider name, at most {MAX_TEXT} characters.", "brief": f"Non-whitespace bounded worker brief, at most {MAX_TEXT} characters.", "cwd": f"Non-whitespace existing absolute worktree directory, at most {MAX_TEXT} characters.", "model": f"Non-whitespace configured model name when supplied, at most {MAX_TEXT} characters."},
            }
            for tool_name, fields in text_fields.items():
                for field_name, description in fields.items():
                    field = schemas[tool_name]["properties"][field_name]
                    if field_name == "model":
                        assert field["default"] is None and field["anyOf"][1] == {"type": "null"}
                        field = field["anyOf"][0]
                    assert field["type"] == "string" and field["minLength"] == 1 and field["maxLength"] == MAX_TEXT
                    assert field["description"] == description
            wait_properties = schemas["worker_wait"]["properties"]
            assert wait_properties["timeout_ms"] == {"default": 500, "description": "Milliseconds for one bounded wait; reserves native-liveness time.", "maximum": MAX_WAIT_MS, "minimum": 1, "title": "Timeout Ms", "type": "integer"}
            assert wait_properties["max_events"] == {"default": 1, "description": "Retained events returned by one wait.", "maximum": MAX_EVENTS, "minimum": 1, "title": "Max Events", "type": "integer"}
            for tool_name in ("worker_start", "worker_follow_up"):
                sandbox = schemas[tool_name]["properties"]["sandbox"]
                assert sandbox["default"] == "read-only" and sandbox["enum"] == list(ALLOWED_SANDBOXES)
                assert sandbox["description"] == "Sandbox for the next start or follow-up; one of the supported modes."

            runtime_adapter = FerryAdapter(Client(), _sandbox)
            runtime_start = await runtime_adapter.worker_start(str(ROOT), "openai", "runtime", None, "read-only")
            runtime_too_many = await runtime_adapter.worker_wait(runtime_start["thread_id"], runtime_start["turn_id"], 100, 100)
            assert runtime_too_many["error"]["code"] == "INVALID_ARGUMENT"
            await runtime_adapter.close()

            invalid = await call(session, "worker_start", cwd="relative", provider="openai", brief="x")
            assert invalid["error"]["code"] == "INVALID_CWD"
            mismatch = await call(session, "worker_start", cwd=str(ROOT), provider="mismatch", brief="x")
            assert mismatch["error"]["code"] == "PROVIDER_MISMATCH"
            model_mismatch = await call(session, "worker_start", cwd=str(ROOT), provider="openai", model="mismatch-model", brief="x")
            assert model_mismatch["error"]["code"] == "MODEL_MISMATCH"

            start = await call(session, "worker_start", cwd=str(ROOT), provider="openai", brief="x")
            assert start["ok"]
            assert start["status"] == "starting"
            assert start["requested_model"] is None and start["observed_model"] is None
            assert start["model_verification"] == "not_available"
            assert start["model_verification_reason"] == "codex_thread_metadata_not_available"
            public_too_many = await call(session, "worker_wait", thread_id=start["thread_id"], turn_id=start["turn_id"], timeout_ms=100, max_events=100)
            assert public_too_many["error"]["code"] == "INVALID_ARGUMENT"
            immediate_interrupt = await call(session, "worker_interrupt", thread_id=start["thread_id"], turn_id=start["turn_id"])
            assert immediate_interrupt["error"]["code"] == "SDK_OPERATION_FAILED"
            assert immediate_interrupt["error"]["cause"] == "native active turn is not registered"
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
            model_visible = await call(session, "worker_start", cwd=str(ROOT), provider="openai", model="visible-model", brief="visible")
            assert model_visible["status"] == "starting"
            assert model_visible["requested_model"] == "visible-model" and model_visible["observed_model"] == "visible-model"
            assert model_visible["model_verification"] == "verified" and "model_verification_reason" not in model_visible
            visible_active = await call(session, "worker_wait", thread_id=model_visible["thread_id"], turn_id=model_visible["turn_id"], timeout_ms=20, max_events=1)
            assert visible_active["status"] == "active"
            await call(session, "worker_interrupt", thread_id=model_visible["thread_id"], turn_id=model_visible["turn_id"])
            await call(session, "worker_wait", thread_id=model_visible["thread_id"], turn_id=model_visible["turn_id"], timeout_ms=10, max_events=4)
            follow = await call(session, "worker_follow_up", thread_id=start["thread_id"], provider="openai", cwd=str(ROOT), brief="next")
            assert follow["ok"] and follow["thread_id"] == start["thread_id"] and follow["status"] == "starting"
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
            reasoning_noise = await call(session, "worker_start", cwd=str(ROOT), provider="openai", brief="reasoning-noise")
            noise_started = await call(session, "worker_wait", thread_id=reasoning_noise["thread_id"], turn_id=reasoning_noise["turn_id"], timeout_ms=20, max_events=1)
            assert noise_started["status"] == "active" and [event["method"] for event in noise_started["events"]] == ["turn/started"]
            before = asyncio.get_running_loop().time()
            noise_retained = await call(session, "worker_wait", thread_id=reasoning_noise["thread_id"], turn_id=reasoning_noise["turn_id"], timeout_ms=100, max_events=1)
            assert asyncio.get_running_loop().time() - before < 0.5
            assert noise_retained["status"] == "active" and [event["method"] for event in noise_retained["events"]] == ["item/agentMessage/delta"]
            noise_terminal = await call(session, "worker_wait", thread_id=reasoning_noise["thread_id"], turn_id=reasoning_noise["turn_id"], timeout_ms=20, max_events=7)
            assert noise_terminal["status"] == "terminal" and [event["method"] for event in noise_terminal["events"]] == ["item/plan/delta", "item/commandExecution/outputDelta", "turn/plan/updated", "thread/tokenUsage/updated", "warning", "item/updated", "turn/completed"]
            reasoning_failure = await call(session, "worker_start", cwd=str(ROOT), provider="openai", brief="reasoning-failed-terminal")
            await call(session, "worker_wait", thread_id=reasoning_failure["thread_id"], turn_id=reasoning_failure["turn_id"], timeout_ms=20, max_events=1)
            retained_failure = await call(session, "worker_wait", thread_id=reasoning_failure["thread_id"], turn_id=reasoning_failure["turn_id"], timeout_ms=100, max_events=4)
            assert retained_failure["error"]["code"] == "TURN_FAILED" and retained_failure["error"]["native_error"] == "{'message': 'reasoning failure cause'}"
            assert [event["method"] for event in retained_failure["events"]] == ["error", "item/updated", "turn/completed"]
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
            concurrent_ready = await call(session, "worker_wait", thread_id=winner["thread_id"], turn_id=winner["turn_id"], timeout_ms=20, max_events=1)
            assert concurrent_ready["status"] == "active"
            await call(session, "worker_interrupt", thread_id=winner["thread_id"], turn_id=winner["turn_id"])
            await call(session, "worker_wait", thread_id=winner["thread_id"], turn_id=winner["turn_id"], timeout_ms=10, max_events=4)
            failed_terminal = await call(session, "worker_start", cwd=str(ROOT), provider="openai", brief="failed-terminal")
            assert failed_terminal["ok"], failed_terminal
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
            system_error = await call(session, "worker_start", cwd=str(ROOT), provider="openai", brief="system-error")
            system_draining = await call(session, "worker_wait", thread_id=system_error["thread_id"], turn_id=system_error["turn_id"], timeout_ms=10, max_events=1)
            assert system_draining["status"] == "failed_draining" and system_draining["native_status"] == "systemError"
            assert [event["method"] for event in system_draining["events"]] == ["turn/started"]
            system_terminal = await call(session, "worker_wait", thread_id=system_error["thread_id"], turn_id=system_error["turn_id"], timeout_ms=10, max_events=4)
            assert system_terminal["error"]["code"] == "TURN_FAILED"
            assert system_terminal["error"]["native_error"] == "{'message': 'native system error cause'}"
            assert [event["method"] for event in system_terminal["events"]] == ["item/updated", "turn/completed"]
            system_replay = await call(session, "worker_wait", thread_id=system_error["thread_id"], turn_id=system_error["turn_id"], timeout_ms=10, max_events=1)
            assert system_replay["error"]["code"] == "LIVE_HANDLE_UNAVAILABLE"
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
            abandoned_ready = await call(session, "worker_wait", thread_id=abandoned["thread_id"], turn_id=abandoned["turn_id"], timeout_ms=20, max_events=1)
            assert abandoned_ready["status"] == "active"
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
    async with connected() as (restarted, _):
        lost = await call(restarted, "worker_steer", thread_id=abandoned["thread_id"], turn_id=abandoned["turn_id"], correction="x")
        assert lost["error"]["code"] == "LIVE_HANDLE_UNAVAILABLE"
        resumed = await call(restarted, "worker_follow_up", thread_id=start["thread_id"], provider="openai", cwd=str(ROOT), brief="after restart")
        assert resumed["ok"] and resumed["thread_id"] == start["thread_id"]
    async with connected({"FERRY_FAKE_BROKEN_ADVISORY": "1"}) as (optional_advisory_failure, _):
        assert len((await optional_advisory_failure.list_tools()).tools) == 5
    ERRLOG.seek(0)
    assert "controlled terminal stream failure" in ERRLOG.read()
    count=sum(isinstance(node, ast.Assert) for node in ast.walk(ast.parse(Path(__file__).read_text())))
    print(f"mcp contract: {count} assert statements passed")


if __name__ == "__main__":
    asyncio.run(main())
