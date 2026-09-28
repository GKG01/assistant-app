"""Fixed Tauri child entry point. Receives a credential through its private stdin pipe."""
import json
import os
import socket
import sys
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from main import create_app
from permissions.session import DesktopSession


def read_token() -> str:
    payload = json.loads(sys.stdin.readline(256))
    token = payload.get("token") if isinstance(payload, dict) else None
    if not isinstance(token, str):
        raise ValueError("Missing desktop session.")
    DesktopSession(token)
    return token


def run() -> None:
    try:
        token = read_token()
        application = create_app(session_token=token)
        original_lifespan = application.router.lifespan_context

        @asynccontextmanager
        async def lifespan(app: FastAPI) -> AsyncIterator[None]:
            async with original_lifespan(app):
                # Only the parent reads stdout. Never include the credential here.
                print('{"status":"ready"}', flush=True)
                yield

        application.router.lifespan_context = lifespan
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Windows exclusive binding prevents a second listener sharing this port.
        if os.name == "nt":
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        port = int(os.environ.get("NOVA_BACKEND_PORT", "8000"))
        listener.bind(("127.0.0.1", port))
        listener.listen(128)
        server = uvicorn.Server(uvicorn.Config(
            application, host="127.0.0.1", port=port, access_log=False,
            log_level="warning", timeout_graceful_shutdown=3,
        ))

        def watch_parent() -> None:
            # Parent keeps stdin open. EOF means the desktop exited or crashed.
            sys.stdin.read()
            server.should_exit = True
            # Bound orphan lifetime even if a worker is stuck in a file scan.
            force_exit = threading.Timer(5, lambda: os._exit(0))
            force_exit.daemon = True
            force_exit.start()

        threading.Thread(target=watch_parent, daemon=True).start()
        try:
            server.run(sockets=[listener])
        finally:
            listener.close()
    except Exception:
        # No exception payloads/tracebacks: malformed bootstrap data may contain secrets.
        print('{"status":"error"}', flush=True)
        raise SystemExit(1) from None


if __name__ == "__main__":
    run()
