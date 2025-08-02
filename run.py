"""Convenience script to run the TRIZ quiz application."""

import sys
import threading
from pathlib import Path

# Ensure local src/ directory is on the import path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from bot import run_bot
from server import run_server


def main() -> None:
    threading.Thread(target=run_server, daemon=True).start()
    run_bot()


if __name__ == "__main__":
    main()
