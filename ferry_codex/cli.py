"""The intentionally small public Ferry console seam."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .build_identity import FULL_VERSION
from .integration import IntegrationError, setup, status, uninstall


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ferry", description="Reconcile Ferry's installed Codex plugin integration.")
    parser.add_argument("--version", action="version", version=FULL_VERSION)
    parser.add_argument("--ferry-home", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--codex", help=argparse.SUPPRESS)
    subcommands = parser.add_subparsers(dest="command", required=True)
    for name in ("setup", "status", "uninstall"):
        subcommands.add_parser(name)
    args = parser.parse_args(argv)
    try:
        {"setup": setup, "status": status, "uninstall": uninstall}[args.command](ferry_home=args.ferry_home, codex=args.codex)
    except IntegrationError as exc:
        print(f"ferry: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ferry: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
