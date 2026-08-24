"""Source-level console and build-identity contracts with a local fake Codex."""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ferry_codex import build_backend, integration
from ferry_codex.build_identity import FULL_VERSION, PUBLIC_VERSION
from ferry_codex.cli import main


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "ferry"
MARKETPLACE = ROOT / ".agents" / "plugins" / "marketplace.json"


project_version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
plugin_version = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text())["version"]
mcp_module = ast.parse((PLUGIN / "src" / "ferry_mcp" / "__init__.py").read_text())
mcp_version = next(node.value.value for node in mcp_module.body
                   if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "__version__"
                                                           for target in node.targets)
                   if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str))
assert PUBLIC_VERSION == "0.1.6"
assert project_version == plugin_version == mcp_version == PUBLIC_VERSION
skill_contract = (PLUGIN / "skills" / "ferry" / "SKILL.md").read_text()
for required in (
    "platform-appropriate long read-only\ncommand turns for steer and interrupt",
    "`CommandExecutionThreadItem` whose status is `inProgress`",
    "same\nowner tool execution",
    "native acknowledgement and terminal effect",
    "do not add an atomic Doctor operation, queue, retry,\nor fallback",
):
    assert required in skill_contract


FAKE = '''#!/usr/bin/env python3
import json, os, sys
state_path = os.environ["FERRY_FAKE_STATE"]
state = json.loads(open(state_path).read())
args = sys.argv[1:]
def save(): open(state_path, "w").write(json.dumps(state))
def mutate():
 state["mutations"] += 1; save()
 if state.get("fail_after") == state["mutations"]: raise SystemExit(23)
if args[:3] == ["plugin", "marketplace", "list"]:
 print(json.dumps({"marketplaces": state["marketplaces"]}))
elif args[:2] == ["plugin", "list"]:
 print(json.dumps({"installed": state["plugins"], "available": []}))
elif args[:3] == ["plugin", "marketplace", "add"]:
 root=args[3]; state["marketplaces"]=[{"name":"ferry","root":root}]; mutate(); print("{}")
elif args[:2] == ["plugin", "add"]:
 if state.get("ignore_plugin_add"): print("{}")
 else:
  root=state["marketplaces"][0]["root"]
  version=json.load(open(os.path.join(root,"plugins","ferry",".codex-plugin","plugin.json")))["version"]
  state["plugins"]=[{"pluginId":"ferry@ferry","marketplaceName":"ferry","enabled":True,"version":version}]; mutate(); print("{}")
elif args[:2] == ["plugin", "remove"]:
 if not state["plugins"]: raise SystemExit("ferry@ferry is absent")
 state["plugins"]=[]; mutate(); print("{}")
elif args[:3] == ["plugin", "marketplace", "remove"]:
 state["marketplaces"]=[]; mutate(); print("{}")
else: raise SystemExit("unexpected fake Codex arguments: " + repr(args))
'''


FAKE_UV = '''#!{python}
import json, os, sys
from pathlib import Path
if os.environ.get("FERRY_UV_FAIL") == "1":
 sys.stderr.write("FERRY_UV_SENTINEL\\n"); raise SystemExit(37)
Path(os.environ["FERRY_UV_RECORD"]).write_text(json.dumps([sys.argv[1:], os.getcwd()]))
'''


def state(path: Path, *, marketplace: Path | None = None, plugin: bool = False, enabled: bool = True, version: str = FULL_VERSION,
          fail_after: int | None = None, ignore_plugin_add: bool = False) -> None:
    payload = {"marketplaces": [], "plugins": [], "mutations": 0, "fail_after": fail_after,
               "ignore_plugin_add": ignore_plugin_add}
    if marketplace is not None:
        payload["marketplaces"] = [{"name": "ferry", "root": str(marketplace)}]
    if plugin:
        payload["plugins"] = [{"pluginId": "ferry@ferry", "marketplaceName": "ferry", "enabled": enabled, "version": version}]
    path.write_text(json.dumps(payload))


with tempfile.TemporaryDirectory(prefix="ferry-console-") as raw:
    temp = Path(raw); fake = temp / "codex"; fake.write_text(FAKE); fake.chmod(0o755)
    state_file = temp / "state.json"
    original_source, original_marketplace, original_sdk = integration.package_plugin_root, integration.marketplace_file, integration.install_sdk
    integration.package_plugin_root = lambda: PLUGIN
    integration.marketplace_file = lambda: MARKETPLACE
    sdk_calls = []
    integration.install_sdk = lambda: sdk_calls.append("install")
    old = os.environ.get("FERRY_FAKE_STATE"); os.environ["FERRY_FAKE_STATE"] = str(state_file)
    try:
        foreign = temp / "foreign"; foreign.mkdir(); state(state_file, marketplace=foreign)
        assert main(["--ferry-home", str(temp / "foreign-home"), "--codex", str(fake), "setup"]) == 1
        assert json.loads(state_file.read_text())["mutations"] == 0 and sdk_calls == []

        home = temp / "home"; stage = home / "marketplace"; stage.mkdir(parents=True); marker = stage / "foreign-marker"; marker.write_text("keep")
        state(state_file); sdk_calls.clear()
        assert main(["--ferry-home", str(home), "--codex", str(fake), "setup"]) == 1
        assert marker.read_text() == "keep" and json.loads(state_file.read_text())["mutations"] == 0 and sdk_calls == []
        assert main(["--ferry-home", str(home), "--codex", str(fake), "uninstall"]) == 1
        assert marker.read_text() == "keep" and json.loads(state_file.read_text())["mutations"] == 0
        shutil.rmtree(stage)

        # The packaged setup seam must reject every symlinked staged path before
        # it can mutate the external target.
        for relative in (Path("plugins"), Path(".agents"), Path(".agents/plugins"),
                         Path(".agents/plugins/marketplace.json")):
            symlink_home = temp / f"symlink-{relative.as_posix().replace('/', '-')}"
            symlink_stage = symlink_home / "marketplace"
            shutil.copytree(PLUGIN, symlink_stage / "plugins" / "ferry")
            marketplace_target = symlink_stage / ".agents" / "plugins" / "marketplace.json"
            marketplace_target.parent.mkdir(parents=True)
            shutil.copyfile(MARKETPLACE, marketplace_target)
            external = temp / f"external-{relative.as_posix().replace('/', '-')}"
            external.mkdir()
            marker = external / "marker"
            marker.write_text("keep")
            target = symlink_stage / relative
            if target.is_dir():
                shutil.rmtree(target)
                target.symlink_to(external, target_is_directory=True)
            else:
                target.unlink()
                target.symlink_to(marker)
            state(state_file, marketplace=symlink_stage)
            assert main(["--ferry-home", str(symlink_home), "--codex", str(fake), "setup"]) == 1 and marker.read_text() == "keep"

        state(state_file)
        setup_output = StringIO()
        with redirect_stdout(setup_output):
            assert main(["--ferry-home", str(home), "--codex", str(fake), "setup"]) == 0
        assert integration.DOCTOR_PROMPT in setup_output.getvalue()
        assert main(["--ferry-home", str(home), "--codex", str(fake), "status"]) == 0
        binding = stage / "plugins" / "ferry" / ".mcp.json"
        binding_payload = json.loads(binding.read_text()); binding_payload["mcpServers"]["ferry"]["env"]["FERRY_CODEX_BIN"] = "/wrong/codex"
        binding.write_text(json.dumps(binding_payload))
        assert main(["--ferry-home", str(home), "--codex", str(fake), "status"]) == 1
        binding_payload["mcpServers"]["ferry"]["env"]["FERRY_CODEX_BIN"] = str(fake.absolute())
        binding.write_text(json.dumps(binding_payload))
        runtime = stage / "plugins" / "ferry" / "src" / "ferry_mcp" / "server.py"; runtime.unlink()
        assert main(["--ferry-home", str(home), "--codex", str(fake), "status"]) == 1
        assert main(["--ferry-home", str(home), "--codex", str(fake), "setup"]) == 0
        assert main(["--ferry-home", str(home), "--codex", str(fake), "setup"]) == 0
        uninstall_output = StringIO()
        with redirect_stdout(uninstall_output):
            assert main(["--ferry-home", str(home), "--codex", str(fake), "uninstall"]) == 0
        assert "uv tool uninstall ferry-codex" in uninstall_output.getvalue()
        assert "pipx uninstall ferry-codex" in uninstall_output.getvalue()
        assert main(["--ferry-home", str(home), "--codex", str(fake), "uninstall"]) == 0
        assert not (home / "marketplace").exists()

        # A no-effect success on re-add must be detected by rollback verification.
        stage = home / "marketplace"; shutil.copytree(PLUGIN, stage / "plugins" / "ferry")
        manifest = stage / "plugins" / "ferry" / ".codex-plugin" / "plugin.json"
        old_version = "0.0.9+0123456789ab"
        payload = json.loads(manifest.read_text()); payload["version"] = old_version; manifest.write_text(json.dumps(payload))
        state(state_file, marketplace=stage, plugin=True, version=old_version, ignore_plugin_add=True)
        from contextlib import redirect_stderr
        from io import StringIO
        receipt = StringIO()
        with redirect_stderr(receipt):
            assert main(["--ferry-home", str(home), "--codex", str(fake), "setup"]) == 1
        assert "rollback failed" in receipt.getvalue() and (stage / "plugins" / "ferry" / ".codex-plugin" / "plugin.json").is_file()
        shutil.rmtree(stage)

        # Fail before either mutation and require the outer finally to clear the
        # exact snapshot/stage temporary directory in both early-failure paths.
        shutil.copytree(PLUGIN, stage / "plugins" / "ferry")
        state(state_file, marketplace=stage, plugin=True)
        original_copytree = integration.shutil.copytree
        def fail_snapshot(source, destination, *args, **kwargs):
            if Path(source).resolve() == stage.resolve(): raise OSError("controlled snapshot failure")
            return original_copytree(source, destination, *args, **kwargs)
        integration.shutil.copytree = fail_snapshot
        try:
            assert main(["--ferry-home", str(home), "--codex", str(fake), "setup"]) == 1
        finally:
            integration.shutil.copytree = original_copytree
        assert not list(home.glob(".ferry-rollback-*")) and not list(stage.glob(".ferry-stage-*"))

        def fail_candidate(source, destination, *args, **kwargs):
            if Path(source).resolve() == PLUGIN.resolve(): raise OSError("controlled candidate failure")
            return original_copytree(source, destination, *args, **kwargs)
        integration.shutil.copytree = fail_candidate
        try:
            assert main(["--ferry-home", str(home), "--codex", str(fake), "setup"]) == 1
        finally:
            integration.shutil.copytree = original_copytree
        assert not list(home.glob(".ferry-rollback-*")) and not list(stage.glob(".ferry-stage-*"))
        shutil.rmtree(stage)

        for fail_after in (1, 2):
            stage = home / "marketplace"
            if stage.exists(): shutil.rmtree(stage)
            shutil.copytree(PLUGIN, stage / "plugins" / "ferry")
            manifest = stage / "plugins" / "ferry" / ".codex-plugin" / "plugin.json"
            payload = json.loads(manifest.read_text()); payload["version"] = FULL_VERSION; manifest.write_text(json.dumps(payload))
            (stage / "marker").write_text("prior-stage")
            state(state_file, marketplace=stage, plugin=True, fail_after=fail_after)
            assert main(["--ferry-home", str(home), "--codex", str(fake), "setup"]) == 1
            restored = json.loads(state_file.read_text())
            assert (stage / "marker").read_text() == "prior-stage"
            assert len(restored["marketplaces"]) == 1
            assert restored["marketplaces"][0]["name"] == "ferry"
            assert Path(restored["marketplaces"][0]["root"]).resolve() == stage.resolve()
            assert len(restored["plugins"]) == 1 and restored["plugins"][0]["version"] == FULL_VERSION
            assert not list(home.glob(".ferry-rollback-*"))

        old_version = "0.0.9+0123456789ab"
        stage = home / "marketplace"; shutil.rmtree(stage); shutil.copytree(PLUGIN, stage / "plugins" / "ferry")
        manifest = stage / "plugins" / "ferry" / ".codex-plugin" / "plugin.json"
        payload = json.loads(manifest.read_text()); payload["version"] = old_version; manifest.write_text(json.dumps(payload))
        state(state_file, marketplace=stage, plugin=True, version=old_version)
        assert main(["--ferry-home", str(home), "--codex", str(fake), "setup"]) == 0
        assert json.loads(state_file.read_text())["plugins"][0]["version"] == FULL_VERSION
        assert not list(home.glob(".ferry-rollback-*"))

        shutil.rmtree(stage); shutil.copytree(PLUGIN, stage / "plugins" / "ferry")
        manifest = stage / "plugins" / "ferry" / ".codex-plugin" / "plugin.json"
        payload = json.loads(manifest.read_text()); payload["version"] = old_version; manifest.write_text(json.dumps(payload))
        (stage / "marker").write_text("old-stage")
        state(state_file, marketplace=stage, plugin=True, version=old_version, fail_after=2)
        assert main(["--ferry-home", str(home), "--codex", str(fake), "setup"]) == 1
        restored = json.loads(state_file.read_text())
        assert restored["plugins"][0]["version"] == old_version and (stage / "marker").read_text() == "old-stage"
        assert not list(home.glob(".ferry-rollback-*"))

        shutil.rmtree(stage); shutil.copytree(PLUGIN, stage / "plugins" / "ferry")
        (stage / "marker").write_text("no-plugin-stage")
        state(state_file, marketplace=stage, plugin=False, fail_after=2)
        assert main(["--ferry-home", str(home), "--codex", str(fake), "setup"]) == 1
        restored = json.loads(state_file.read_text())
        assert restored["plugins"] == [] and (stage / "marker").read_text() == "no-plugin-stage"
        assert not list(home.glob(".ferry-rollback-*"))

        shutil.rmtree(stage); state(state_file, fail_after=2)
        assert main(["--ferry-home", str(home), "--codex", str(fake), "setup"]) == 1
        restored = json.loads(state_file.read_text())
        assert restored["marketplaces"] == [] and restored["plugins"] == []

        shutil.copytree(PLUGIN, stage / "plugins" / "ferry")
        state(state_file, marketplace=stage, plugin=True, version=old_version)
        assert main(["--ferry-home", str(home), "--codex", str(fake), "uninstall"]) == 0
        assert json.loads(state_file.read_text())["marketplaces"] == [] and json.loads(state_file.read_text())["plugins"] == []

        state(state_file, plugin=True, version=old_version)
        assert main(["--ferry-home", str(home), "--codex", str(fake), "uninstall"]) == 0
        assert json.loads(state_file.read_text())["marketplaces"] == [] and json.loads(state_file.read_text())["plugins"] == []

        shutil.copytree(PLUGIN, stage / "plugins" / "ferry")
        state(state_file, marketplace=stage, plugin=True, enabled=False)
        assert main(["--ferry-home", str(home), "--codex", str(fake), "setup"]) == 0
        assert json.loads(state_file.read_text())["plugins"] == [{"pluginId": "ferry@ferry", "marketplaceName": "ferry", "enabled": True, "version": FULL_VERSION}]
        state(state_file, marketplace=stage, plugin=True, enabled=False)
        assert main(["--ferry-home", str(home), "--codex", str(fake), "uninstall"]) == 0
        assert json.loads(state_file.read_text())["marketplaces"] == [] and json.loads(state_file.read_text())["plugins"] == []
    finally:
        if old is None: os.environ.pop("FERRY_FAKE_STATE", None)
        else: os.environ["FERRY_FAKE_STATE"] = old
        integration.package_plugin_root, integration.marketplace_file, integration.install_sdk = original_source, original_marketplace, original_sdk

    commands = []
    original_run, original_validate = integration.run, integration._validate_sdk_runtime
    original_find_spec, original_which, original_prefix = integration.importlib.util.find_spec, integration.shutil.which, integration.sys.prefix
    try:
        integration.run = lambda *args: commands.append(args)
        integration._validate_sdk_runtime = lambda: commands.append(("validate",))
        integration.importlib.util.find_spec = lambda _: object()
        integration.install_sdk()
        assert commands == [(sys.executable, "-m", "pip", "install", "--no-deps", "openai-codex==0.147.0"), ("validate",)]

        pipx_prefix = temp / "pipx-home" / "venvs" / "ferry-codex"; pipx_prefix.mkdir(parents=True)
        metadata_path = pipx_prefix / "pipx_metadata.json"
        metadata_path.write_text(json.dumps({"environment": "ferry-codex", "main_package": {"package": "ferry-codex"}}))
        fake_pipx = temp / "pipx"; fake_pipx.write_text(""); fake_pipx.chmod(0o755)
        fake_uv = temp / "uv"; fake_uv.write_text(""); fake_uv.chmod(0o755)
        integration.sys.prefix = str(pipx_prefix)
        integration.importlib.util.find_spec = lambda _: None
        integration.shutil.which = lambda name: str(fake_pipx) if name == "pipx" else str(fake_uv) if name == "uv" else None
        commands.clear(); integration.install_sdk()
        assert commands == [(str(fake_pipx.absolute()), "runpip", "ferry-codex", "install", "--no-deps", "openai-codex==0.147.0"), ("validate",)]

        metadata_path.write_text("not-json"); commands.clear()
        try: integration.install_sdk()
        except integration.IntegrationError: pass
        else: raise AssertionError("malformed pipx metadata selected an installer")
        assert commands == []
        metadata_path.write_text(json.dumps({"environment": "ferry-codex", "main_package": {"package": "other"}}))
        try: integration.install_sdk()
        except integration.IntegrationError: pass
        else: raise AssertionError("foreign pipx metadata selected an installer")
        integration.shutil.which = lambda _: None
        metadata_path.write_text(json.dumps({"environment": "ferry-codex", "main_package": {"package": "ferry-codex"}}))
        try: integration.install_sdk()
        except integration.IntegrationError: pass
        else: raise AssertionError("absent pipx selected an installer")
        metadata_path.unlink()
        try: integration.install_sdk()
        except integration.IntegrationError as error:
            assert "executable uv" in str(error)
        else: raise AssertionError("missing uv selected an installer")

        integration.shutil.which = lambda name: str(fake_uv) if name == "uv" else None
        commands.clear(); integration.install_sdk()
        assert commands == [(str(fake_uv.absolute()), "--no-config", "pip", "install", "--python", sys.executable, "--no-deps", "openai-codex==0.147.0"), ("validate",)]

        def fail_uv(*args):
            raise subprocess.CalledProcessError(19, args, stderr="controlled uv stderr")
        integration.run = fail_uv
        try: integration.install_sdk()
        except subprocess.CalledProcessError as error:
            assert error.returncode == 19 and error.stderr == "controlled uv stderr"
        else: raise AssertionError("uv subprocess failure lost its cause")
    finally:
        integration.run, integration._validate_sdk_runtime = original_run, original_validate
        integration.importlib.util.find_spec, integration.shutil.which, integration.sys.prefix = original_find_spec, original_which, original_prefix

    # This child process uses the real CLI and installer from a pip-less tool
    # environment provisioned with only Ferry's required non-pip runtime. It
    # begins in hostile uv configuration, so only --no-config makes the fake
    # uv invocation independent of the caller's directory.
    tool = temp / "uv-tool"; subprocess.run(("uv", "venv", "--python", sys.executable, str(tool)), check=True)
    tool_python = tool / "bin" / "python"
    subprocess.run(("uv", "pip", "install", "--python", str(tool_python), "-r", str(ROOT / "plugins" / "ferry" / "requirements.lock")), check=True)
    subprocess.run(("uv", "pip", "install", "--python", str(tool_python), "--no-deps", "openai-codex==0.147.0"), check=True)
    pip_probe = subprocess.run((str(tool_python), "-c", "import importlib.util, json, sys; print(json.dumps({'pip_absent': importlib.util.find_spec('pip') is None, 'executable': sys.executable}))"),
                               check=True, stdout=subprocess.PIPE, text=True)
    pip_probe_result = json.loads(pip_probe.stdout)
    assert pip_probe_result["pip_absent"] is True
    resources = tool / "ferry_codex_resources"
    shutil.copytree(PLUGIN, resources / "plugins" / "ferry")
    marketplace_resources = resources / ".agents" / "plugins"; marketplace_resources.mkdir(parents=True)
    shutil.copyfile(MARKETPLACE, marketplace_resources / "marketplace.json")
    ferry = temp / "ferry"; ferry.write_text(f"#!{tool_python}\nfrom ferry_codex.cli import main\nraise SystemExit(main())\n"); ferry.chmod(0o755)
    fake_uv = temp / "uv"; fake_uv.write_text(FAKE_UV.format(python=sys.executable)); fake_uv.chmod(0o755)
    hostile = temp / "hostile-uv"; hostile.mkdir()
    (hostile / "uv.toml").write_text('index-url = "https://example.invalid/uv.toml"\n')
    (hostile / "pyproject.toml").write_text('[tool.uv]\nindex-url = "https://example.invalid/pyproject"\n')
    record = temp / "uv-record.json"; state(state_file)
    cli_env = {**os.environ, "FERRY_FAKE_STATE": str(state_file), "FERRY_UV_RECORD": str(record),
               "PATH": f"{temp}{os.pathsep}{os.environ['PATH']}", "PYTHONPATH": str(ROOT)}
    completed = subprocess.run((str(ferry), "--ferry-home", str(temp / "uv-home"), "--codex", str(fake), "setup"),
                               cwd=hostile, env=cli_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert completed.returncode == 0 and completed.stderr == "", completed.stderr
    assert integration.DOCTOR_PROMPT in completed.stdout
    uv_args, uv_cwd = json.loads(record.read_text())
    assert uv_args == ["--no-config", "pip", "install", "--python", pip_probe_result["executable"], "--no-deps", "openai-codex==0.147.0"]
    assert Path(uv_cwd).resolve() == hostile.resolve()
    state(state_file)
    failed_env = {**cli_env, "FERRY_UV_FAIL": "1"}
    failed = subprocess.run((str(ferry), "--ferry-home", str(temp / "uv-failed-home"), "--codex", str(fake), "setup"),
                            cwd=hostile, env=failed_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert failed.returncode == 1 and "FERRY_UV_SENTINEL" in failed.stderr and "CalledProcessError" in failed.stderr, (failed.returncode, failed.stdout, failed.stderr)
    assert integration.DOCTOR_PROMPT not in failed.stdout

    failed_codex = temp / "failed-codex"
    failed_codex.write_text("#!/usr/bin/env python3\nimport sys\nsys.stderr.write('controlled Codex stderr\\n')\nraise SystemExit(42)\n")
    failed_codex.chmod(0o755)
    try:
        integration.run_json(str(failed_codex), "plugin", "list", "--json")
    except integration.IntegrationError as error:
        assert "plugin list --json" in str(error) and "42" in str(error) and "controlled Codex stderr" in str(error)
        assert isinstance(error.__cause__, subprocess.CalledProcessError) and error.__cause__.returncode == 42
    else:
        raise AssertionError("Codex JSON command failure lost its diagnostic cause")

    identity = temp / "build_identity.py"
    identity.write_text('SOURCE_COMMIT = "0123456789abcdef0123456789abcdef01234567"\n')
    backend_root = temp / "backend"; package = backend_root / "ferry_codex"; package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    package_info = backend_root / "PKG-INFO"; package_info.write_text("Name: ferry-codex\n")
    original_identity, original_root = build_backend.IDENTITY, build_backend.ROOT
    build_backend.IDENTITY, build_backend.ROOT = identity, backend_root
    try:
        (backend_root / ".git").mkdir()
        assert build_backend._source_sdist_commit() is None
        shutil.rmtree(backend_root / ".git")
        assert build_backend._source_sdist_commit() == "0123456789abcdef0123456789abcdef01234567"
        package_info.unlink()
        assert build_backend._source_sdist_commit() is None
    finally:
        build_backend.IDENTITY, build_backend.ROOT = original_identity, original_root

    egg, bytecode = backend_root / "ferry_codex.egg-info", package / "__pycache__"
    original_root, original_egg, original_bytecode = build_backend.ROOT, build_backend.EGG_INFO, build_backend.BYTECODE
    build_backend.ROOT, build_backend.EGG_INFO, build_backend.BYTECODE = backend_root, egg, bytecode
    try:
        egg.mkdir(); (egg / "PKG-INFO").write_text("generated")
        bytecode.mkdir(); (bytecode / "__init__.cpython-313.pyc").write_bytes(b"generated")
        build_backend._clear_backend_byproducts()
        assert not egg.exists() and not bytecode.exists()
        egg.mkdir(); (egg / "unexpected").write_text("not-generated")
        try: build_backend._clear_backend_byproducts()
        except RuntimeError: pass
        else: raise AssertionError("unexpected egg-info contents were deleted")
        assert (egg / "unexpected").exists(); shutil.rmtree(egg)
        egg.mkdir(); (egg / "nested").mkdir()
        try: build_backend._clear_backend_byproducts()
        except RuntimeError: pass
        else: raise AssertionError("nested egg-info directory was deleted")
        assert (egg / "nested").is_dir(); shutil.rmtree(egg)
        outside = temp / "outside"; outside.mkdir(); egg.symlink_to(outside, target_is_directory=True)
        try: build_backend._clear_backend_byproducts()
        except RuntimeError: pass
        else: raise AssertionError("symlinked egg-info was deleted")
        assert egg.is_symlink(); egg.unlink()
        primary = ValueError("controlled hook failure")
        original_clear = build_backend._clear_backend_byproducts
        build_backend._clear_backend_byproducts = lambda: (_ for _ in ()).throw(OSError("controlled cleanup failure"))
        try:
            try: build_backend._run_hook(lambda: (_ for _ in ()).throw(primary))
            except RuntimeError as error:
                assert "controlled hook failure" in str(error) and "controlled cleanup failure" in str(error)
                assert error.__cause__ is primary
            else: raise AssertionError("combined hook/cleanup failure was not raised")
        finally:
            build_backend._clear_backend_byproducts = original_clear
    finally:
        build_backend.ROOT, build_backend.EGG_INFO, build_backend.BYTECODE = original_root, original_egg, original_bytecode

count = sum(isinstance(node, ast.Assert) for node in ast.walk(ast.parse(Path(__file__).read_text())))
print(f"distribution source contract: {count} assert statements passed")
