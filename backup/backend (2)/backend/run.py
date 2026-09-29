"""Local dev server launcher.

On Windows, uvicorn creates a ProactorEventLoop before importing the app, which
psycopg-async cannot use. We set the *selector* loop policy first, then run the
server with ``loop="none"`` so uvicorn uses our already-running loop instead of
installing its own (Proactor) one.

Usage:  python run.py            # serves app.main:app on http://127.0.0.1:8000
        python run.py 8001       # optional port override
"""

from __future__ import annotations

import asyncio
import sys

import uvicorn

HOST = "127.0.0.1"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000


def main() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    config = uvicorn.Config("app.main:app", host=HOST, port=PORT, loop="none", log_level="info")
    asyncio.run(uvicorn.Server(config).serve())


if __name__ == "__main__":
    main()
