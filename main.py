#!/usr/bin/env python
"""Application entry point."""
import logging

import uvicorn

from app.app_factory import create_app
from app.settings import settings

logging.basicConfig(level=logging.INFO)

app = create_app()

if __name__ == "__main__":
    logging.info("Reset link: http://localhost:%s/reset", settings.APP_PORT)
    try:
        uvicorn.run(app, host=settings.APP_HOST, port=settings.APP_PORT)
    except OSError as exc:
        logging.error("Server failed to start: %s", exc)
        raise
