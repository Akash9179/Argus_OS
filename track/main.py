"""Entry point for the world model server."""

from __future__ import annotations

import logging
import os

import uvicorn

from track.app import create_app

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
)

app = create_app()


def main() -> None:
    uvicorn.run(
        "track.main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        reload=bool(os.getenv("RELOAD")),
    )


if __name__ == "__main__":
    main()
