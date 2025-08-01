"""Run both bot and server together."""
import subprocess
import sys
import time


def main() -> None:
    procs = [
        subprocess.Popen([sys.executable, "server.py"]),
        subprocess.Popen([sys.executable, "bot.py"]),
    ]
    try:
        while True:
            time.sleep(1)
            if any(p.poll() is not None for p in procs):
                break
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    main()
