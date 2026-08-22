"""The five Ferry MCP operations, backed by the official Codex SDK only."""

from __future__ import annotations

import asyncio
from enum import Enum
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Optional


MAX_TEXT = 32_000
MAX_WAIT_MS = 30_000
MAX_EVENTS = 16
MAX_EVENT_TEXT = 4_096
MIN_LIVENESS_READ_RESERVE_S = 0.001
MAX_LIVENESS_READ_RESERVE_S = 0.050
ALLOWED_SANDBOXES = {"read-only", "workspace-write", "danger-full-access"}


class FerryFailure(Exception):
    def __init__(self, code: str, operation: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.operation = operation
        self.details = details

    def result(self) -> dict[str, Any]:
        return {"ok": False, "error": {"code": self.code, "operation": self.operation,
                "message": str(self), **self.details}}


def _cause(operation: str, exc: Exception, **details: Any) -> FerryFailure:
    return FerryFailure("SDK_OPERATION_FAILED", operation, str(exc),
                        cause_type=type(exc).__name__, cause=str(exc), **details)


def _text(value: str, name: str, operation: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FerryFailure("INVALID_ARGUMENT", operation, f"{name} must be non-empty")
    if len(value) > MAX_TEXT:
        raise FerryFailure("INVALID_ARGUMENT", operation, f"{name} exceeds {MAX_TEXT} characters")
    return value


def _cwd(value: str, operation: str) -> str:
    path = Path(_text(value, "cwd", operation))
    if not path.is_absolute() or not path.is_dir():
        raise FerryFailure("INVALID_CWD", operation, "cwd must be an existing absolute directory", cwd=value)
    return str(path.resolve(strict=True))


def _sandbox(value: str, operation: str) -> str:
    if value not in ALLOWED_SANDBOXES:
        raise FerryFailure("INVALID_SANDBOX", operation, "sandbox is not allowed", sandbox=value)
    return value


def _bound(value: int, name: str, maximum: int, operation: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1 or value > maximum:
        raise FerryFailure("INVALID_ARGUMENT", operation, f"{name} must be between 1 and {maximum}")
    return value


def _metadata(native: Any) -> tuple[str | None, str | None, str | None]:
    """Read generated SDK data without relying on wrapper reprs."""
    thread = getattr(native, "thread", native)
    provider = getattr(thread, "model_provider", None)
    model = getattr(thread, "model", None)
    cwd = getattr(getattr(thread, "cwd", None), "root", None)
    return provider, model, cwd


def _value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def _bounded(value: Any) -> str:
    text = str(value)
    return text if len(text) <= MAX_EVENT_TEXT else text[:MAX_EVENT_TEXT] + "…[truncated]"


def _field(value: Any, name: str) -> Any:
    return value.get(name) if isinstance(value, dict) else getattr(value, name, None)


def _thread_liveness(native: Any, operation: str) -> str:
    """Read the public SDK ThreadStatus RootModel without inferring from events."""
    thread = _field(native, "thread")
    status = _field(thread, "status")
    root = _field(status, "root")
    liveness = _value(_field(root, "type"))
    if liveness not in ("active", "idle"):
        raise FerryFailure("UNEXPECTED_NATIVE_THREAD_STATUS", operation,
                           "native thread read did not contain an active or idle ThreadStatus",
                           native_status=_bounded(liveness), status_type=type(status).__name__)
    return liveness


def _result_with_events(result: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    """Preserve this call's consumed native events when its later work fails."""
    return {**result, "events": events} if events else result


@dataclass
class LiveTurn:
    thread: Any
    turn: Any
    stream: AsyncIterator[Any]
    next_event: Optional[asyncio.Task[Any]] = None
    native_read: Optional[asyncio.Task[Any]] = None


class FerryAdapter:
    """One SDK client and one live native handle; no queue, scheduler, or history."""

    def __init__(self, client: Any, sandbox_factory: Callable[[str], Any], *,
                 approval_mode: Any = None, service_name: str | None = None) -> None:
        self._client = client
        self._sandbox_factory = sandbox_factory
        self._live: Optional[LiveTurn] = None
        self._lock = asyncio.Lock()
        self._approval_mode = approval_mode
        self._service_name = service_name

    async def close(self) -> None:
        live = self._live
        failures: list[BaseException] = []
        # Close SDK first: its transport failure wakes the SDK-owned waiter safely.
        try:
            close = getattr(self._client, "close", None)
            if close is not None:
                result = close()
                if hasattr(result, "__await__"):
                    await result
        except BaseException as exc:
            failures.append(exc)
        finally:
            if live and live.next_event:
                try:
                    await live.next_event
                except BaseException as exc:
                    failures.append(exc)
            if live:
                try:
                    await self._cancel_native_read(live)
                except BaseException as exc:
                    failures.append(exc)
                try:
                    await live.stream.aclose()
                except BaseException as exc:
                    failures.append(exc)
            self._live = None
        if failures:
            raise RuntimeError("Ferry SDK shutdown failed: " + "; ".join(str(item) for item in failures)) from failures[0]

    async def worker_start(self, cwd: str, provider: str, brief: str, model: str | None,
                           sandbox: str) -> dict[str, Any]:
        async with self._lock:
            return await self._worker_start(cwd, provider, brief, model, sandbox)

    async def _worker_start(self, cwd: str, provider: str, brief: str, model: str | None,
                           sandbox: str) -> dict[str, Any]:
        operation = "worker_start"
        try:
            cwd = _cwd(cwd, operation)
            provider = _text(provider, "provider", operation)
            brief = _text(brief, "brief", operation)
            sandbox = _sandbox(sandbox, operation)
            if model is not None:
                model = _text(model, "model", operation)
            if self._live is not None:
                raise FerryFailure("ACTIVE_TURN_EXISTS", operation, "an alternate-provider turn is already live",
                                   thread_id=self._live.thread.id, turn_id=self._live.turn.id)
            thread = await self._client.thread_start(cwd=cwd, model_provider=provider, model=model,
                                                     sandbox=self._sandbox_factory(sandbox),
                                                     approval_mode=self._approval_mode, ephemeral=False,
                                                     service_name=self._service_name)
            native = await thread.read(include_turns=False)
            actual_provider, actual_model, actual_cwd = _metadata(native)
            if actual_provider != provider:
                raise FerryFailure("PROVIDER_MISMATCH", operation, "native provider metadata differs before turn",
                                   requested_provider=provider, actual_provider=actual_provider,
                                   thread_id=thread.id, cwd=actual_cwd)
            if model is not None and actual_model is not None and actual_model != model:
                raise FerryFailure("MODEL_MISMATCH", operation, "native model metadata differs before turn",
                                   requested_model=model, actual_model=actual_model, thread_id=thread.id)
            if actual_cwd != cwd:
                raise FerryFailure("CWD_MISMATCH", operation, "native cwd metadata differs before turn",
                                   expected_cwd=cwd, actual_cwd=actual_cwd, thread_id=thread.id)
            turn = await thread.turn(brief, cwd=cwd, sandbox=self._sandbox_factory(sandbox))
            self._live = LiveTurn(thread=thread, turn=turn, stream=turn.stream())
            return {"ok": True, "thread_id": thread.id, "turn_id": turn.id, "provider": actual_provider,
                    "model": actual_model, "model_verification": "verified" if model and actual_model == model else "unsupported",
                    "cwd": actual_cwd, "status": "active"}
        except FerryFailure as exc:
            return exc.result()
        except Exception as exc:
            return _cause(operation, exc).result()

    def _require_live(self, operation: str, thread_id: str, turn_id: str) -> LiveTurn:
        _text(thread_id, "thread_id", operation)
        _text(turn_id, "turn_id", operation)
        if self._live is None or self._live.thread.id != thread_id or self._live.turn.id != turn_id:
            raise FerryFailure("LIVE_HANDLE_UNAVAILABLE", operation, "no matching live SDK handle",
                               thread_id=thread_id, turn_id=turn_id)
        return self._live

    async def worker_wait(self, thread_id: str, turn_id: str, timeout_ms: int = 500,
                          max_events: int = 1) -> dict[str, Any]:
        async with self._lock:
            return await self._worker_wait(thread_id, turn_id, timeout_ms, max_events)

    async def _worker_wait(self, thread_id: str, turn_id: str, timeout_ms: int = 500,
                          max_events: int = 1) -> dict[str, Any]:
        operation = "worker_wait"
        events: list[dict[str, Any]] = []
        try:
            live = self._require_live(operation, thread_id, turn_id)
            timeout_ms = _bound(timeout_ms, "timeout_ms", MAX_WAIT_MS, operation)
            max_events = _bound(max_events, "max_events", MAX_EVENTS, operation)
            timeout_seconds = timeout_ms / 1000
            deadline = asyncio.get_running_loop().time() + timeout_seconds
            stream_deadline = deadline - min(MAX_LIVENESS_READ_RESERVE_S,
                                             max(MIN_LIVENESS_READ_RESERVE_S, timeout_seconds / 4))
            for _ in range(max_events):
                if live.next_event is None:
                    live.next_event = asyncio.create_task(anext(live.stream))
                remaining = stream_deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    return await self._nonterminal_wait_result(live, thread_id, turn_id, events, deadline)
                done, _ = await asyncio.wait({live.next_event}, timeout=remaining)
                if not done:
                    return await self._nonterminal_wait_result(live, thread_id, turn_id, events, deadline)
                event = live.next_event.result()
                live.next_event = None
                payload = getattr(event, "payload", None)
                events.append({"method": getattr(event, "method", type(event).__name__), "payload": _bounded(payload)})
                if getattr(event, "method", None) == "turn/completed":
                    terminal = _value(getattr(getattr(payload, "turn", None), "status", None))
                    if terminal is None and isinstance(payload, dict):
                        terminal = _value(payload.get("status"))
                    turn_payload = _field(payload, "turn") or payload
                    native_error = _field(turn_payload, "error")
                    final_response = _field(turn_payload, "final_response") or _field(turn_payload, "finalResponse")
                    evidence = _bounded(payload)
                    self._live = None
                    try:
                        await self._cancel_native_read(live)
                        await live.stream.aclose()
                    except Exception as cleanup:
                        return _result_with_events(
                            _cause(operation, cleanup, thread_id=thread_id, turn_id=turn_id,
                                   native_terminal=evidence).result(), events)
                    if terminal not in ("completed", "interrupted"):
                        return _result_with_events(
                            FerryFailure("TURN_FAILED", operation, "native turn reached a failed terminal state",
                                         thread_id=thread_id, turn_id=turn_id, native_status=terminal,
                                         native_error=_bounded(native_error), native_terminal=evidence).result(), events)
                    return {"ok": True, "thread_id": thread_id, "turn_id": turn_id,
                            "status": "terminal", "events": events, "native_status": terminal,
                            "final_response": _bounded(final_response) if final_response is not None else None,
                            "final_response_verification": "terminal-payload" if final_response is not None else "event-stream",
                            "native_terminal": evidence}
            return await self._nonterminal_wait_result(live, thread_id, turn_id, events, deadline)
        except FerryFailure as exc:
            return _result_with_events(exc.result(), events)
        except Exception as exc:
            details = {"thread_id": thread_id, "turn_id": turn_id}
            return _result_with_events(_cause(operation, exc, **details).result(), events)

    async def _nonterminal_wait_result(self, live: LiveTurn, thread_id: str, turn_id: str,
                                        events: list[dict[str, Any]], deadline: float) -> dict[str, Any]:
        if live.native_read is None:
            live.native_read = asyncio.create_task(live.thread.read(include_turns=False))
        else:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return self._liveness_timeout(thread_id, turn_id, events)
            done, _ = await asyncio.wait({live.native_read}, timeout=remaining)
            if not done:
                return self._liveness_timeout(thread_id, turn_id, events)
            stale_read = live.native_read
            live.native_read = None
            stale_read.result()
            live.native_read = asyncio.create_task(live.thread.read(include_turns=False))
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            return self._liveness_timeout(thread_id, turn_id, events)
        done, _ = await asyncio.wait({live.native_read}, timeout=remaining)
        if not done:
            return self._liveness_timeout(thread_id, turn_id, events)
        native_read = live.native_read
        live.native_read = None
        native = native_read.result()
        liveness = _thread_liveness(native, "worker_wait")
        return {"ok": True, "thread_id": thread_id, "turn_id": turn_id,
                "status": "active" if liveness == "active" else "terminal_pending", "events": events}

    @staticmethod
    def _liveness_timeout(thread_id: str, turn_id: str, events: list[dict[str, Any]]) -> dict[str, Any]:
        return _result_with_events(
            FerryFailure("NATIVE_LIVENESS_TIMEOUT", "worker_wait",
                         "native thread liveness read did not complete within worker_wait timeout",
                         thread_id=thread_id, turn_id=turn_id).result(), events)

    @staticmethod
    async def _cancel_native_read(live: LiveTurn) -> None:
        task = live.native_read
        live.native_read = None
        if task is None:
            return
        if not task.done():
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            if not task.cancelled():
                raise

    async def worker_steer(self, thread_id: str, turn_id: str, correction: str) -> dict[str, Any]:
        async with self._lock:
            return await self._worker_steer(thread_id, turn_id, correction)

    async def _worker_steer(self, thread_id: str, turn_id: str, correction: str) -> dict[str, Any]:
        operation = "worker_steer"
        try:
            live = self._require_live(operation, thread_id, turn_id)
            await live.turn.steer(_text(correction, "correction", operation))
            return {"ok": True, "thread_id": thread_id, "turn_id": turn_id, "status": "active"}
        except FerryFailure as exc:
            return exc.result()
        except Exception as exc:
            return _cause(operation, exc, thread_id=thread_id, turn_id=turn_id).result()

    async def worker_interrupt(self, thread_id: str, turn_id: str) -> dict[str, Any]:
        async with self._lock:
            return await self._worker_interrupt(thread_id, turn_id)

    async def _worker_interrupt(self, thread_id: str, turn_id: str) -> dict[str, Any]:
        operation = "worker_interrupt"
        try:
            live = self._require_live(operation, thread_id, turn_id)
            await live.turn.interrupt()
            return {"ok": True, "thread_id": thread_id, "turn_id": turn_id, "status": "interrupt_requested"}
        except FerryFailure as exc:
            return exc.result()
        except Exception as exc:
            return _cause(operation, exc, thread_id=thread_id, turn_id=turn_id).result()

    async def worker_follow_up(self, thread_id: str, provider: str, brief: str, cwd: str,
                               model: str | None, sandbox: str) -> dict[str, Any]:
        async with self._lock:
            return await self._worker_follow_up(thread_id, provider, brief, cwd, model, sandbox)

    async def _worker_follow_up(self, thread_id: str, provider: str, brief: str, cwd: str,
                               model: str | None, sandbox: str) -> dict[str, Any]:
        operation = "worker_follow_up"
        try:
            if self._live is not None:
                raise FerryFailure("ACTIVE_TURN_EXISTS", operation, "wait or interrupt the live turn first",
                                   thread_id=self._live.thread.id, turn_id=self._live.turn.id)
            thread_id = _text(thread_id, "thread_id", operation)
            cwd = _cwd(cwd, operation)
            provider = _text(provider, "provider", operation)
            brief = _text(brief, "brief", operation)
            sandbox = _sandbox(sandbox, operation)
            if model is not None:
                model = _text(model, "model", operation)
            thread = await self._client.thread_resume(thread_id, cwd=cwd, model_provider=provider, model=model,
                                                      sandbox=self._sandbox_factory(sandbox),
                                                      approval_mode=self._approval_mode)
            native = await thread.read(include_turns=False)
            actual_provider, actual_model, actual_cwd = _metadata(native)
            if actual_provider != provider:
                raise FerryFailure("PROVIDER_MISMATCH", operation, "native provider metadata differs before turn",
                                   requested_provider=provider, actual_provider=actual_provider, thread_id=thread.id)
            if model is not None and actual_model is not None and actual_model != model:
                raise FerryFailure("MODEL_MISMATCH", operation, "native model metadata differs before turn",
                                   requested_model=model, actual_model=actual_model, thread_id=thread.id)
            if actual_cwd != cwd:
                raise FerryFailure("CWD_MISMATCH", operation, "native cwd metadata differs before turn",
                                   expected_cwd=cwd, actual_cwd=actual_cwd, thread_id=thread.id)
            turn = await thread.turn(brief, cwd=cwd, sandbox=self._sandbox_factory(sandbox))
            self._live = LiveTurn(thread=thread, turn=turn, stream=turn.stream())
            return {"ok": True, "thread_id": thread.id, "turn_id": turn.id, "provider": actual_provider,
                    "model": actual_model, "model_verification": "verified" if model and actual_model == model else "unsupported",
                    "cwd": actual_cwd, "status": "active"}
        except FerryFailure as exc:
            return exc.result()
        except Exception as exc:
            return _cause(operation, exc, thread_id=thread_id).result()
