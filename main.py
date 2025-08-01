"""Single entry point for TRIZ quiz app."""
import threading

from bot import run_bot
from server import run_server


def main():
    # Start web server in background thread
    threading.Thread(target=run_server, daemon=True).start()
    # Run Telegram bot (blocking)
    run_bot()


if __name__ == "__main__":
    main()
