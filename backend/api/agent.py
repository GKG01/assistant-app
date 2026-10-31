from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.middleware.body_limit import RequestBodyLimitMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from agent.agent import Agent
from agent.schemas import AgentRequest, AgentResponse
from api.files import TRUSTED_ORIGINS, require_file_client
from services.llm.base import LLMError

# Enough for 10,000 JSON-escaped Unicode characters, but bound bytes before parsing.
MAX_AGENT_BODY_BYTES = 128 * 1024


class AgentBodyLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.limited = RequestBodyLimitMiddleware(app, MAX_AGENT_BODY_BYTES)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        app = (
            self.limited
            if scope.get("path", "").rstrip("/") == "/agent/message"
            else self.app
        )
        await app(scope, receive, send)


def get_agent(request: Request) -> Agent:
    origin = request.headers.get("origin")
    if (origin is not None and origin not in TRUSTED_ORIGINS) or (
        origin is None and request.headers.get("sec-fetch-site") == "cross-site"
    ):
        raise HTTPException(403, "Request origin is not allowed.")
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        raise HTTPException(415, "Agent requests require application/json.")
    return request.app.state.agent


ERROR_RESPONSES = {
    "configuration": (503, "Nova's AI provider is not configured."),
    "authentication": (
        503,
        "Nova's AI provider could not authenticate. Check backend configuration.",
    ),
    "rate_limit": (429, "Nova's AI provider is rate limited. Try again later."),
    "timeout": (504, "Nova's AI provider timed out. Try again later."),
    "connection": (503, "Nova couldn't reach the AI provider."),
    "invalid_response": (
        502,
        "Nova's AI provider returned an invalid or empty response.",
    ),
    "provider": (502, "Nova's AI provider could not complete the request."),
}

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/message", response_model=AgentResponse)
async def message(
    request: AgentRequest,
    http_request: Request,
    agent: Annotated[Agent, Depends(get_agent)],
) -> AgentResponse:
    file_access = False
    try:
        require_file_client(http_request)
        file_access = True
    except HTTPException:
        pass  # Text and arithmetic retain standalone access; file tools fail closed.
    try:
        return await agent.respond(request, file_access=file_access)
    except LLMError as exc:
        status, detail = ERROR_RESPONSES[exc.category]
        raise HTTPException(status, detail) from None
