"""Optional, process-local PyPI update advisory with no worker-path I/O."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Awaitable, Callable

from packaging.version import InvalidVersion, Version


COOLDOWN_SECONDS = 24 * 60 * 60
PYPI_URL = "https://pypi.org/pypi/ferry-codex/json"


def default_cache_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "Ferry" / "update.json"
    if "FERRY_CACHE_HOME" in os.environ:
        return Path(os.environ["FERRY_CACHE_HOME"]) / "ferry" / "update.json"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "Ferry" / "update.json"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "ferry" / "update.json"


class UpdateAdvisory:
    """Best-effort advisory state; its failures are deliberately invisible to MCP."""

    def __init__(self, installed_version: str, *, cache_path: Path | None = None,
                 fetch: Callable[[], Awaitable[str]] | None = None,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                 now: Callable[[], float] = time.time,
                 task_factory: Callable[[Awaitable[None]], asyncio.Task[None]] = asyncio.create_task) -> None:
        self._installed_version = installed_version
        self._cache_path = cache_path or default_cache_path()
        self._fetch = fetch or self._fetch_pypi
        self._sleep, self._now, self._task_factory = sleep, now, task_factory
        self._latest: str | None = None
        self._disabled = False
        self._emitted = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        try:
            if self._task is not None:
                return
            cached = self._read_cache()
            if self._disabled:
                return
            if cached is not None:
                self._latest = cached.get("latest") if isinstance(cached.get("latest"), str) else None
                if isinstance(cached.get("next_check"), (int, float)) and cached["next_check"] > self._now():
                    return
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            coroutine = self._guarded_check()
            try:
                task = self._task_factory(coroutine)
                self._task = task
                task.add_done_callback(self._observe_task)
            except BaseException:
                coroutine.close()
                raise
        except BaseException:
            self._disabled = True

    def _observe_task(self, task: asyncio.Task[None]) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except BaseException:
            self._disabled = True

    async def close(self) -> None:
        task, self._task = self._task, None
        if task is None or task.done():
            return
        task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=0.1)
        except BaseException:
            pass

    def add_to(self, result: dict[str, Any]) -> dict[str, Any]:
        if self._disabled or self._emitted or not self._is_newer(self._latest):
            return result
        self._emitted = True
        return {**result, "advisory": {"code": "FERRY_UPDATE_AVAILABLE",
                "message": f"Ferry {self._latest} is available; close Ferry-using Codex sessions, then run uv tool upgrade ferry-codex && ferry setup (or pipx upgrade ferry-codex && ferry setup).",
                "latest_version": self._latest}}

    def _read_cache(self) -> dict[str, Any] | None:
        try:
            if not self._cache_path.exists():
                return None
            data = json.loads(self._cache_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("update cache must be an object")
            return data
        except BaseException:
            self._disabled = True
            return None

    async def _guarded_check(self) -> None:
        try:
            await self._check()
        except BaseException:
            self._disabled = True

    async def _check(self) -> None:
        for attempt in range(3):
            try:
                latest = self._parse_version(await self._fetch())
                self._latest = latest
                self._write_cache({"latest": latest, "next_check": self._now() + COOLDOWN_SECONDS})
                return
            except (TimeoutError, ConnectionError, urllib.error.URLError, urllib.error.HTTPError) as exc:
                transient = not isinstance(exc, urllib.error.HTTPError) or exc.code >= 500
                if (not transient and attempt == 0) or attempt == 2:
                    break
                await self._sleep((1, 3)[attempt])
            except BaseException:
                break
        self._write_cache({"latest": self._latest, "next_check": self._now() + COOLDOWN_SECONDS})

    async def _fetch_pypi(self) -> str:
        def request() -> str:
            with urllib.request.urlopen(PYPI_URL, timeout=5) as response:
                return response.read().decode("utf-8")
        return await asyncio.to_thread(request)

    @staticmethod
    def _parse_version(payload: str) -> str:
        value = json.loads(payload)["info"]["version"]
        if not isinstance(value, str):
            raise ValueError("PyPI latest version is not a string")
        Version(value)
        return value

    def _write_cache(self, data: dict[str, Any]) -> None:
        candidate: Path | None = None
        try:
            fd, raw = tempfile.mkstemp(prefix=".ferry-update-", dir=self._cache_path.parent)
            candidate = Path(raw)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, sort_keys=True)
                stream.write("\n")
            os.replace(candidate, self._cache_path)
        finally:
            if candidate is not None and candidate.exists():
                candidate.unlink()

    def _is_newer(self, latest: str | None) -> bool:
        try:
            return latest is not None and Version(latest) > Version(self._installed_version)
        except InvalidVersion:
            return False
