"""Release-only build identity guard around the standards-based setuptools backend."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = ROOT / "ferry_codex" / "build_identity.py"
EGG_INFO = ROOT / "ferry_codex.egg-info"
BYTECODE = ROOT / "ferry_codex" / "__pycache__"
EGG_INFO_FILES = {"PKG-INFO", "SOURCES.txt", "dependency_links.txt", "entry_points.txt", "requires.txt", "top_level.txt"}


def _clear_backend_byproducts() -> None:
    """Remove only the exact, regular setuptools/Python byproducts this backend creates."""
    if EGG_INFO.exists() or EGG_INFO.is_symlink():
        if EGG_INFO.is_symlink() or not EGG_INFO.is_dir():
            raise RuntimeError(f"refusing unexpected generated path: {EGG_INFO}")
        entries = list(EGG_INFO.rglob("*"))
        files = {item.relative_to(EGG_INFO).as_posix() for item in entries if item.is_file()}
        if any(item.is_symlink() or item.is_dir() or not item.is_file() for item in entries) or files - EGG_INFO_FILES:
            raise RuntimeError(f"refusing unexpected setuptools byproduct contents: {EGG_INFO}")
        shutil.rmtree(EGG_INFO)
    if BYTECODE.exists() or BYTECODE.is_symlink():
        if BYTECODE.is_symlink() or not BYTECODE.is_dir():
            raise RuntimeError(f"refusing unexpected generated path: {BYTECODE}")
        modules = {item.stem for item in (ROOT / "ferry_codex").glob("*.py")}
        for item in BYTECODE.rglob("*"):
            if item.is_symlink() or item.is_dir() or not item.is_file():
                raise RuntimeError(f"refusing unexpected Python bytecode byproduct: {BYTECODE}")
            match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\.cpython-\d+(?:\.opt-\d+)?\.pyc", item.name)
            if match is None or match.group(1) not in modules:
                raise RuntimeError(f"refusing unexpected Python bytecode byproduct: {BYTECODE}")
        shutil.rmtree(BYTECODE)


def _run_hook(action):
    """Run one PEP 517 hook without allowing cleanup to erase its original cause."""
    try:
        result = action()
    except BaseException as primary:
        try:
            _clear_backend_byproducts()
        except BaseException as cleanup:
            raise RuntimeError(f"PEP 517 hook failed: {primary}; cleanup failed: {cleanup}") from primary
        raise
    _clear_backend_byproducts()
    return result


def _release_commit() -> str:
    _clear_backend_byproducts()
    requested = os.environ.get("FERRY_BUILD_COMMIT")
    if not requested or not re.fullmatch(r"[0-9a-f]{40}", requested):
        raise RuntimeError("set FERRY_BUILD_COMMIT to the exact lowercase 40-character release commit")
    observed = subprocess.run(("git", "-C", str(ROOT), "rev-parse", "HEAD"), check=True, text=True, stdout=subprocess.PIPE).stdout.strip()
    dirty = subprocess.run(("git", "-C", str(ROOT), "status", "--porcelain"), check=True, text=True, stdout=subprocess.PIPE).stdout
    if observed != requested or dirty:
        raise RuntimeError("release artifacts require a clean checkout at FERRY_BUILD_COMMIT")
    return requested


def _source_sdist_commit() -> str | None:
    """Only an unpacked sdist may reuse its immutable embedded source commit."""
    if (ROOT / ".git").exists() or not (ROOT / "PKG-INFO").is_file():
        return None
    match = re.search(r'SOURCE_COMMIT = "([0-9a-f]{40})"', IDENTITY.read_text(encoding="utf-8"))
    return match.group(1) if match else None


@contextmanager
def _embedded_identity() -> Iterator[None]:
    commit = _release_commit()
    original = IDENTITY.read_text(encoding="utf-8")
    replacement = re.sub(r'SOURCE_COMMIT = ".*"', f'SOURCE_COMMIT = "{commit}"', original)
    IDENTITY.write_text(replacement, encoding="utf-8")
    try:
        yield
    finally:
        IDENTITY.write_text(original, encoding="utf-8")


def build_wheel(wheel_directory: str, config_settings=None, metadata_directory=None) -> str:
    from setuptools import build_meta as backend
    # A wheel directly from a checkout must bind to that clean checkout.  A wheel
    # from an sdist instead reuses the immutable identity already embedded there.
    def action():
        if _source_sdist_commit() is not None:
            return backend.build_wheel(wheel_directory, config_settings, metadata_directory)
        with _embedded_identity():
            return backend.build_wheel(wheel_directory, config_settings, metadata_directory)
    return _run_hook(action)


def build_sdist(sdist_directory: str, config_settings=None) -> str:
    from setuptools import build_meta as backend
    def action():
        with _embedded_identity():
            return backend.build_sdist(sdist_directory, config_settings)
    return _run_hook(action)


def prepare_metadata_for_build_wheel(metadata_directory: str, config_settings=None) -> str:
    from setuptools import build_meta as backend
    return _run_hook(lambda: backend.prepare_metadata_for_build_wheel(metadata_directory, config_settings))


def get_requires_for_build_wheel(config_settings=None):
    from setuptools import build_meta as backend
    return _run_hook(lambda: backend.get_requires_for_build_wheel(config_settings))


def get_requires_for_build_sdist(config_settings=None):
    from setuptools import build_meta as backend
    return _run_hook(lambda: backend.get_requires_for_build_sdist(config_settings))
