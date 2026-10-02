import re
import secrets

from fastapi import HTTPException, Request


class DesktopSession:
    def __init__(self, token: str | None) -> None:
        if token is not None and re.fullmatch(r"[0-9a-f]{64}", token) is None:
            raise ValueError("Invalid desktop session credential.")
        self._token = token

    def authorize(self, authorization: str | None) -> None:
        expected = self._token
        supplied = authorization or ""
        # Check format before compare_digest; non-ASCII header values fail closed.
        if (
            expected is None
            or not supplied.startswith("Bearer ")
            or re.fullmatch(r"[0-9a-f]{64}", supplied[7:]) is None
            or not secrets.compare_digest(expected, supplied[7:])
        ):
            raise HTTPException(
                401,
                "A valid Nova desktop session is required.",
                headers={"WWW-Authenticate": "Bearer"},
            )


def require_desktop_session(request: Request) -> None:
    request.app.state.desktop_session.authorize(request.headers.get("Authorization"))
