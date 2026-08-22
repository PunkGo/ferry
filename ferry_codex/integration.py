"""Installed-console integration; Codex remains the plugin lifecycle owner."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from importlib import metadata
from pathlib import Path
from typing import Any

from .build_identity import FULL_VERSION, PUBLIC_VERSION


SDK_PIN = "0.147.0"
SDK_NAME = "openai-codex"
SDK_CLI_REQUIREMENT = "openai-codex-cli-bin"


class IntegrationError(RuntimeError):
    pass


def run(*args: str) -> None:
    subprocess.run(args, check=True)


def run_json(*args: str) -> Any:
    try:
        completed = subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        detail = f": {stderr}" if stderr else ""
        raise IntegrationError(f"Codex command failed ({exc.returncode}) for {' '.join(args[1:])}{detail}") from exc
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise IntegrationError(f"Codex returned invalid JSON for {' '.join(args[1:])}: {exc}") from exc


def plugin_digest(plugin: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in plugin.rglob("*") if item.is_file()):
        relative = path.relative_to(plugin).as_posix()
        data = path.read_bytes()
        if relative == ".codex-plugin/plugin.json":
            manifest = json.loads(data)
            manifest["version"] = manifest["version"].split("+", 1)[0]
            data = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        digest.update(relative.encode() + b"\0" + data + b"\0")
    return digest.hexdigest()[:12]


def _safe_parent(destination: Path, root: Path) -> Path:
    root = root.resolve()
    if not destination.is_relative_to(root):
        raise IntegrationError("staged destination escaped install root")
    current = root
    for part in destination.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            raise IntegrationError(f"refusing symlinked staged destination: {current}")
        if current.exists() and not current.is_dir() and current != destination:
            raise IntegrationError(f"staged parent is not a directory: {current}")
    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    if not parent.resolve().is_relative_to(root):
        raise IntegrationError("staged parent escaped install root")
    return parent


def _safe_stage(source: Path, destination: Path, root: Path) -> Path:
    parent = _safe_parent(destination, root)
    candidate = Path(tempfile.mkdtemp(prefix=".ferry-stage-", dir=parent))
    try:
        shutil.copytree(source, candidate, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        return candidate
    except BaseException:
        shutil.rmtree(candidate)
        raise


def _stage_file(source: Path, destination: Path, root: Path, replace=os.replace) -> None:
    parent = _safe_parent(destination, root)
    fd, raw_candidate = tempfile.mkstemp(prefix=".ferry-marketplace-", dir=parent)
    os.close(fd)
    candidate = Path(raw_candidate)
    try:
        shutil.copyfile(source, candidate)
        replace(candidate, destination)
    except BaseException:
        if candidate.exists():
            candidate.unlink()
        raise


def _replace_stage(candidate: Path, destination: Path, replace=os.replace) -> None:
    parent = destination.parent
    backup = parent / f".ferry-backup-{uuid.uuid4().hex}"
    had_old = destination.exists()
    try:
        if had_old:
            replace(destination, backup)
        replace(candidate, destination)
    except BaseException as primary:
        rollback_error = None
        if had_old and backup.exists() and not destination.exists():
            try:
                replace(backup, destination)
            except BaseException as rollback:
                rollback_error = rollback
        if candidate.exists():
            shutil.rmtree(candidate)
        if rollback_error is not None:
            raise IntegrationError(f"stage replacement failed: {primary}; rollback failed: {rollback_error}; retained_backup={backup}") from primary
        raise
    finally:
        if backup.exists() and destination.exists():
            shutil.rmtree(backup)


def package_plugin_root() -> Path:
    root = Path(sys.prefix) / "ferry_codex_resources" / "plugins" / "ferry"
    required = (".codex-plugin/plugin.json", ".mcp.json", "skills/ferry/SKILL.md", "src/ferry_mcp/server.py")
    if not root.is_dir() or any(not (root / item).is_file() for item in required):
        raise IntegrationError(f"installed Ferry package resources are incomplete: {root}")
    return root


def marketplace_file() -> Path:
    path = Path(sys.prefix) / "ferry_codex_resources" / ".agents" / "plugins" / "marketplace.json"
    if not path.is_file():
        raise IntegrationError(f"installed Ferry marketplace resource is missing: {path}")
    return path


def _codex_path(value: str | None = None) -> Path:
    raw = value or shutil.which("codex")
    if raw is None:
        raise IntegrationError("HOST_CODEX_UNAVAILABLE: host codex executable was not found on PATH")
    path = Path(raw).absolute()
    if not path.is_file():
        raise IntegrationError("HOST_CODEX_UNAVAILABLE: host codex executable is not an existing absolute file")
    return path


def _validate_sdk_runtime() -> None:
    # Repository setup imports this module before it installs its venv.  Keep the
    # import path stdlib-only; packaging is an ordinary installed runtime dep.
    from packaging.requirements import Requirement
    try:
        installed = metadata.version(SDK_NAME)
    except metadata.PackageNotFoundError as exc:
        raise IntegrationError(f"{SDK_NAME}=={SDK_PIN} is not installed; run ferry setup") from exc
    if installed != SDK_PIN:
        raise IntegrationError(f"{SDK_NAME} must be exactly {SDK_PIN}; found {installed}")
    try:
        bundled_cli = metadata.version(SDK_CLI_REQUIREMENT)
    except metadata.PackageNotFoundError:
        pass
    else:
        raise IntegrationError(f"{SDK_CLI_REQUIREMENT} must be absent; found {bundled_cli}")
    failures: list[str] = []
    for raw in metadata.requires(SDK_NAME) or []:
        requirement = Requirement(raw)
        if requirement.name.lower().replace("_", "-") == SDK_CLI_REQUIREMENT:
            if str(requirement.specifier) != f"=={SDK_PIN}":
                failures.append(f"unexpected SDK CLI metadata requirement: {raw}")
            continue
        if requirement.marker and not requirement.marker.evaluate():
            continue
        try:
            actual = metadata.version(requirement.name)
        except metadata.PackageNotFoundError:
            failures.append(f"missing {raw}")
        else:
            if requirement.specifier and actual not in requirement.specifier:
                failures.append(f"conflicting {raw}; found {actual}")
    if failures:
        raise IntegrationError("SDK runtime requirements are not satisfied: " + "; ".join(failures))


def install_sdk() -> None:
    pin = f"{SDK_NAME}=={SDK_PIN}"
    if importlib.util.find_spec("pip") is not None:
        run(sys.executable, "-m", "pip", "install", "--no-deps", pin)
    else:
        metadata_path = Path(sys.prefix) / "pipx_metadata.json"
        if metadata_path.is_symlink() or not metadata_path.is_file():
            raise IntegrationError("pip is unavailable and this Ferry environment has no valid pipx metadata")
        try:
            pipx_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            environment = pipx_metadata["environment"]
            package = pipx_metadata["main_package"]["package"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise IntegrationError("pip is unavailable and pipx metadata is malformed") from exc
        prefix = Path(sys.prefix)
        if environment != "ferry-codex" or package != "ferry-codex" or prefix.name != environment or prefix.parent.name != "venvs":
            raise IntegrationError("pipx metadata does not identify this environment as ferry-codex")
        pipx = shutil.which("pipx")
        if pipx is None or not Path(pipx).is_file():
            raise IntegrationError("pip is unavailable and pipx executable was not found on PATH")
        run(str(Path(pipx).absolute()), "runpip", environment, "install", "--no-deps", pin)
    _validate_sdk_runtime()


def _set_staged_binding(candidate: Path, codex: Path) -> None:
    config_path = candidate / ".mcp.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    server = config["mcpServers"]["ferry"]
    server["command"] = str(Path(sys.executable))
    server["args"] = ["./bin/ferry-mcp.py"]
    server["cwd"] = "."
    server["env"] = {**server.get("env", {}), "FERRY_CODEX_BIN": str(codex), "FERRY_BUILD_VERSION": FULL_VERSION}
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    manifest_path = candidate / ".codex-plugin" / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["version"] != PUBLIC_VERSION:
        raise IntegrationError("plugin public version does not match package metadata")
    manifest["version"] = FULL_VERSION
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _records(payload: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    raise IntegrationError("Codex JSON response did not contain the expected record list")


def _owned_marketplace(host: Path, root: Path) -> bool:
    records = _records(run_json(str(host), "plugin", "marketplace", "list", "--json"), ("marketplaces", "items"))
    matches = [record for record in records if record.get("name") == "ferry"]
    if not matches:
        return False
    if len(matches) != 1:
        raise IntegrationError("Codex reports multiple marketplaces named ferry")
    observed = matches[0].get("root", matches[0].get("path"))
    if not isinstance(observed, str):
        raise IntegrationError("Codex ferry marketplace JSON omitted its root path")
    if Path(observed).expanduser().resolve() != root.resolve():
        raise IntegrationError(f"refusing foreign marketplace named ferry: {observed}")
    return True


def _installed_plugin(host: Path) -> dict[str, Any] | None:
    records = _records(run_json(str(host), "plugin", "list", "--marketplace", "ferry", "--json"), ("installed",))
    matches = [record for record in records if record.get("pluginId") == "ferry@ferry" and record.get("marketplaceName") == "ferry"]
    if len(matches) > 1:
        raise IntegrationError("Codex reports multiple ferry@ferry plugins")
    if not matches:
        return None
    record = matches[0]
    if not isinstance(record.get("version"), str):
        raise IntegrationError("Codex ferry@ferry JSON omitted its version")
    return record


def _matching_plugin(host: Path) -> bool:
    record = _installed_plugin(host)
    if record is None:
        return False
    if record.get("enabled") is not True:
        raise IntegrationError("ferry@ferry is not enabled")
    if record.get("version") != FULL_VERSION:
        raise IntegrationError(f"ferry@ferry version is stale: expected {FULL_VERSION}, found {record.get('version')!r}")
    return True


def _restore_prior(host: Path, stage_root: Path, snapshot: Path | None, prior_files: dict[Path, bytes] | None,
                   had_marketplace: bool, prior_plugin: dict[str, Any] | None) -> None:
    failures: list[BaseException] = []
    try:
        if stage_root.exists():
            shutil.rmtree(stage_root)
        if snapshot is not None:
            os.replace(snapshot, stage_root)
    except BaseException as exc:
        failures.append(exc)
    try:
        if _installed_plugin(host) is not None:
            run(str(host), "plugin", "remove", "ferry@ferry", "--json")
        if had_marketplace:
            run(str(host), "plugin", "marketplace", "add", str(stage_root), "--json")
            if prior_plugin is not None:
                run(str(host), "plugin", "add", "ferry@ferry", "--json")
        else:
            if _owned_marketplace(host, stage_root):
                run(str(host), "plugin", "marketplace", "remove", "ferry", "--json")
    except BaseException as exc:
        failures.append(exc)
    try:
        if _owned_marketplace(host, stage_root) != had_marketplace:
            raise IntegrationError("rollback marketplace registration does not match its prior state")
        restored_plugin = _installed_plugin(host)
        if prior_plugin is None:
            if restored_plugin is not None:
                raise IntegrationError("rollback left ferry@ferry installed although it was previously absent")
        elif restored_plugin is None or any(restored_plugin.get(key) != prior_plugin.get(key)
                                             for key in ("pluginId", "marketplaceName", "enabled", "version")):
            raise IntegrationError("rollback ferry@ferry registration does not match its prior state")
        if prior_files is not None:
            restored_files = {item.relative_to(stage_root): item.read_bytes()
                              for item in stage_root.rglob("*") if item.is_file()}
            if restored_files != prior_files:
                raise IntegrationError("rollback staged marketplace files do not match their prior state")
    except BaseException as exc:
        failures.append(exc)
    if failures:
        raise IntegrationError("; ".join(str(item) for item in failures)) from failures[0]


def setup(*, ferry_home: Path | None = None, codex: str | None = None) -> None:
    if sys.version_info < (3, 10):
        raise IntegrationError("Ferry requires Python 3.10 or later")
    host = _codex_path(codex)
    root = (ferry_home or Path.home() / ".ferry").expanduser().resolve()
    stage_root = root / "marketplace"
    # This observation is deliberately before dependency installation: a foreign
    # ferry marketplace is a fail-closed ownership collision, never setup work.
    had_marketplace = _owned_marketplace(host, stage_root)
    if stage_root.exists() and not had_marketplace:
        raise IntegrationError(f"refusing unregistered Ferry marketplace: {stage_root}")
    prior_plugin = _installed_plugin(host) if had_marketplace else None
    source = package_plugin_root()
    marketplace = marketplace_file()
    install_sdk()
    root.mkdir(parents=True, exist_ok=True)
    staged_plugin = stage_root / "plugins" / "ferry"
    staged_marketplace = stage_root / ".agents" / "plugins" / "marketplace.json"
    snapshot: Path | None = None
    snapshot_parent: Path | None = None
    prior_files: dict[Path, bytes] | None = None
    candidate: Path | None = None
    mutation_started = False
    try:
        if stage_root.exists():
            if stage_root.is_symlink():
                raise IntegrationError(f"refusing symlinked Ferry marketplace: {stage_root}")
            snapshot = Path(tempfile.mkdtemp(prefix=".ferry-rollback-", dir=root)) / "marketplace"
            snapshot_parent = snapshot.parent
            shutil.copytree(stage_root, snapshot)
            prior_files = {item.relative_to(stage_root): item.read_bytes()
                           for item in stage_root.rglob("*") if item.is_file()}
        candidate = _safe_stage(source, staged_plugin, root)
        _set_staged_binding(candidate, host)
        mutation_started = True
        _stage_file(marketplace, staged_marketplace, root)
        _replace_stage(candidate, staged_plugin)
        run(str(host), "plugin", "marketplace", "add", str(stage_root), "--json")
        run(str(host), "plugin", "add", "ferry@ferry", "--json")
        if not _owned_marketplace(host, stage_root) or not _matching_plugin(host):
            raise IntegrationError("Codex did not register exactly one current enabled ferry@ferry plugin")
    except BaseException as primary:
        if mutation_started:
            try:
                _restore_prior(host, stage_root, snapshot, prior_files, had_marketplace, prior_plugin)
            except BaseException as rollback:
                raise IntegrationError(f"setup failed: {primary}; rollback failed: {rollback}") from primary
        raise
    finally:
        if candidate is not None and candidate.exists():
            shutil.rmtree(candidate)
        if snapshot_parent is not None and snapshot_parent.exists():
            shutil.rmtree(snapshot_parent)
    print(f"Ferry {FULL_VERSION} is registered. Start a fresh Codex session to discover its Skill and MCP tools.")


def _validate_staged_runtime(stage_root: Path, host: Path) -> None:
    plugin_root = stage_root / "plugins" / "ferry"
    config_path = plugin_root / ".mcp.json"
    entrypoint = plugin_root / "bin" / "ferry-mcp.py"
    source_root = plugin_root / "src"
    server = source_root / "ferry_mcp" / "server.py"
    if not config_path.is_file() or not entrypoint.is_file() or not server.is_file():
        raise IntegrationError(f"Ferry MCP runtime is incomplete at {plugin_root}")
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        mcp = config["mcpServers"]["ferry"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise IntegrationError(f"Ferry MCP binding is unreadable at {config_path}") from exc
    if (mcp.get("command") != str(Path(sys.executable)) or mcp.get("args") != ["./bin/ferry-mcp.py"]
            or mcp.get("cwd") != "." or not isinstance(mcp.get("env"), dict)
            or mcp["env"].get("FERRY_CODEX_BIN") != str(host)
            or mcp["env"].get("FERRY_BUILD_VERSION") != FULL_VERSION):
        raise IntegrationError(f"Ferry MCP binding does not match the current runtime at {config_path}")
    probe = f"import sys; sys.path.insert(0, {str(source_root)!r}); import ferry_mcp.server"
    try:
        subprocess.run((sys.executable, "-c", probe), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        detail = f": {stderr}" if stderr else ""
        raise IntegrationError(f"Ferry MCP runtime import failed ({exc.returncode}) at {source_root}{detail}") from exc


def status(*, ferry_home: Path | None = None, codex: str | None = None) -> None:
    host = _codex_path(codex)
    _validate_sdk_runtime()
    root = (ferry_home or Path.home() / ".ferry").expanduser().resolve()
    stage_root = root / "marketplace"
    if not _owned_marketplace(host, stage_root):
        raise IntegrationError(f"Ferry marketplace is absent at {stage_root}; run ferry setup")
    if not _matching_plugin(host):
        raise IntegrationError("ferry@ferry is absent; run ferry setup")
    plugin = stage_root / "plugins" / "ferry" / ".codex-plugin" / "plugin.json"
    if not plugin.is_file():
        raise IntegrationError(f"Ferry integration is absent at {root / 'marketplace'}; run ferry setup")
    manifest = json.loads(plugin.read_text(encoding="utf-8"))
    if manifest.get("version") != FULL_VERSION:
        raise IntegrationError(f"Ferry integration is stale or unreadable: expected {FULL_VERSION}, found {manifest.get('version')!r}")
    _validate_staged_runtime(stage_root, host)
    print(json.dumps({"version": FULL_VERSION, "python": sys.executable, "codex": str(host), "marketplace": str(stage_root), "plugin_version": manifest["version"], "current": True}, sort_keys=True))


def uninstall(*, ferry_home: Path | None = None, codex: str | None = None) -> None:
    host = _codex_path(codex)
    root = (ferry_home or Path.home() / ".ferry").expanduser().resolve()
    marketplace = root / "marketplace"
    if marketplace.exists() and marketplace.is_symlink():
        raise IntegrationError(f"refusing symlinked Ferry marketplace: {marketplace}")
    owned = _owned_marketplace(host, marketplace)
    if marketplace.exists() and not owned:
        raise IntegrationError(f"refusing unregistered Ferry marketplace: {marketplace}")
    installed = _installed_plugin(host)
    if installed is not None:
        run(str(host), "plugin", "remove", "ferry@ferry", "--json")
    if owned:
        run(str(host), "plugin", "marketplace", "remove", "ferry", "--json")
    if _owned_marketplace(host, marketplace):
        raise IntegrationError("Codex did not remove the Ferry marketplace")
    if _installed_plugin(host) is not None:
        raise IntegrationError("Codex did not remove ferry@ferry")
    if marketplace.exists():
        shutil.rmtree(marketplace)
    print("Ferry integration is removed. Close every Ferry-using Codex session, then run pipx uninstall ferry-codex.")
