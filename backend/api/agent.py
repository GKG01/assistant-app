from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.middleware.body_limit import RequestBodyLimitMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from agent.agent import Agent
from agent.schemas import (
    AgentRequest,
    AgentResponse,
    ClearConversationRequest,
    ExecutionRecord,
)
from agent.grounding import grounded_message
from services.conversations import ConversationError
from api.files import TRUSTED_ORIGINS, require_file_client
from services.llm.base import LLMError

# Enough for 10,000 JSON-escaped Unicode characters, but bound bytes before parsing.
MAX_AGENT_BODY_BYTES = 128 * 1024


class AgentBodyLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.limited = RequestBodyLimitMiddleware(app, MAX_AGENT_BODY_BYTES)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        app = self.limited if scope.get("path", "").startswith("/agent/") else self.app
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
    owner, file_access = conversation_owner(http_request)
    store = http_request.app.state.conversations
    try:
        with store.turn(request.conversation_id, owner) as context:
            records: list[ExecutionRecord] = []
            try:
                response = await agent.respond(
                    request,
                    file_access=file_access,
                    context=context,
                    execution_records=records,
                )
            except LLMError as exc:
                status, detail = ERROR_RESPONSES[exc.category]
                headers = None
                if records:
                    # Preserve verified outcomes even if the next provider call fails.
                    # No unfinished provider protocol or unexecuted calls are stored.
                    detail += "\n" + grounded_message("", records)
                    store.commit(context, request.message, detail, records)
                    headers = {"X-Nova-Conversation-ID": context.conversation_id}
                raise HTTPException(status, detail, headers=headers) from None
            store.commit(context, request.message, response.message, records)
            return response.model_copy(
                update={"conversation_id": context.conversation_id}
            )
    except ConversationError as exc:
        raise HTTPException(exc.status, exc.detail) from None


def conversation_owner(request: Request) -> tuple[object, bool]:
    try:
        require_file_client(request)
    except HTTPException:
        # Authenticated context cannot be downgraded to standalone by omitting a
        # header. Owner identity is process-local and never supplied by the model.
        return request.app.state.standalone_conversation_owner, False
    return request.app.state.desktop_session, True


@router.post("/conversation/clear")
async def clear_conversation(
    body: ClearConversationRequest,
    request: Request,
    agent: Annotated[Agent, Depends(get_agent)],
) -> dict[str, str]:
    owner, _ = conversation_owner(request)
    try:
        request.app.state.conversations.clear(body.conversation_id, owner)
    except ConversationError as exc:
        raise HTTPException(exc.status, exc.detail) from None
    return {"status": "cleared"}
