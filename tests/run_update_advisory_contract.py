"""Deterministic update-advisory checks, including optional-fault containment."""

from __future__ import annotations

import asyncio
import ast
import json
import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins" / "ferry" / "src"))
from ferry_mcp.advisory import COOLDOWN_SECONDS, UpdateAdvisory


async def main() -> None:
    with tempfile.TemporaryDirectory(prefix="ferry-advisory-") as raw:
        root = Path(raw)
        fresh = root / "fresh.json"
        fresh.write_text(json.dumps({"latest": "0.2.0", "next_check": 10_001}))
        calls = 0
        async def never() -> str:
            nonlocal calls; calls += 1; raise AssertionError("fresh cache made a request")
        advisory = UpdateAdvisory("0.1.0", cache_path=fresh, fetch=never, now=lambda: 10_000)
        await advisory.start()
        assert calls == 0
        first = advisory.add_to({"ok": True})
        assert first["advisory"]["code"] == "FERRY_UPDATE_AVAILABLE"
        assert "advisory" not in advisory.add_to({"ok": True})

        stale = root / "stale.json"
        stale.write_text(json.dumps({"latest": "0.1.0", "next_check": 0}))
        gate = asyncio.Event(); calls = 0
        async def delayed() -> str:
            nonlocal calls; calls += 1; await gate.wait(); return '{"info":{"version":"0.2.0"}}'
        advisory = UpdateAdvisory("0.1.0", cache_path=stale, fetch=delayed, now=lambda: 10_000)
        started = asyncio.get_running_loop().time(); await advisory.start()
        assert asyncio.get_running_loop().time() - started < 0.1 and calls == 0
        assert advisory._task is not None and not advisory._task.done()
        gate.set(); await asyncio.sleep(0)
        assert advisory.add_to({"ok": True})["advisory"]["latest_version"] == "0.2.0"
        await advisory.close(); assert advisory._task is None

        transient = root / "transient.json"; attempts = []; sleeps = []
        async def retry() -> str:
            attempts.append(1); raise ConnectionError("controlled")
        async def record_sleep(delay: float) -> None: sleeps.append(delay)
        advisory = UpdateAdvisory("0.1.0", cache_path=transient, fetch=retry, sleep=record_sleep, now=lambda: 10_000)
        await advisory._check()
        assert len(attempts) == 3 and sleeps == [1, 3]
        assert json.loads(transient.read_text())["next_check"] == 10_000 + COOLDOWN_SECONDS

        deterministic = root / "deterministic.json"; attempts = []
        async def invalid() -> str:
            attempts.append(1); return '{"info":{"version":"bad version"}}'
        advisory = UpdateAdvisory("0.1.0", cache_path=deterministic, fetch=invalid, now=lambda: 10_000)
        await advisory._check()
        assert len(attempts) == 1 and json.loads(deterministic.read_text())["next_check"] == 10_000 + COOLDOWN_SECONDS

        malformed = root / "malformed.json"; malformed.write_text("not-json")
        calls = 0
        async def blocked() -> str:
            nonlocal calls; calls += 1; return '{"info":{"version":"0.2.0"}}'
        advisory = UpdateAdvisory("0.1.0", cache_path=malformed, fetch=blocked)
        await advisory.start(); await asyncio.sleep(0)
        assert calls == 0 and advisory.add_to({"ok": True}) == {"ok": True}

        blocked_parent = root / "not-a-directory"; blocked_parent.write_text("x")
        advisory = UpdateAdvisory("0.1.0", cache_path=blocked_parent / "update.json", fetch=blocked)
        await advisory.start(); assert advisory.add_to({"ok": True}) == {"ok": True}

        write_fault = UpdateAdvisory("0.1.0", cache_path=root / "write.json", fetch=blocked)
        write_fault._write_cache = lambda _: (_ for _ in ()).throw(OSError("controlled write fault"))
        await write_fault.start(); await asyncio.sleep(0)
        assert write_fault.add_to({"ok": True}) == {"ok": True}

        def task_fault(_): raise RuntimeError("controlled task fault")
        advisory = UpdateAdvisory("0.1.0", cache_path=root / "task.json", fetch=blocked, task_factory=task_fault)
        await advisory.start(); assert advisory.add_to({"ok": True}) == {"ok": True}

        async def escaping() -> str: raise RuntimeError("controlled background fault")
        advisory = UpdateAdvisory("0.1.0", cache_path=root / "background.json", fetch=escaping)
        await advisory.start(); await asyncio.sleep(0)
        assert advisory.add_to({"ok": True}) == {"ok": True}
    count = sum(isinstance(node, ast.Assert) for node in ast.walk(ast.parse(Path(__file__).read_text())))
    print(f"update advisory contract: {count} assert statements passed")


if __name__ == "__main__":
    asyncio.run(main())
