"""Run the plugin's source module from the selected isolated Python environment."""

from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))
from ferry_mcp.server import main

main()
