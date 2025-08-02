"""Convenience script to run the TRIZ quiz application."""

from threading import Thread

from src.bot import run_bot
from src.server import run_server


def main() -> None:
    Thread(target=run_server, daemon=True).start()
    run_bot()


if __name__ == "__main__":
    main()
