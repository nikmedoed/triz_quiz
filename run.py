"""Convenience script to run the TRIZ quiz application."""

from pathlib import Path
import sys

# Ensure local src/ package directory is on the import path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from triz_quiz.main import main

if __name__ == "__main__":
    main()
