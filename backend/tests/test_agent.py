import asyncio
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from agent.agent import Agent
from agent.prompts import SYSTEM_PROMPT
from agent.schemas import AgentRequest, ToolCall
from config.settings import Settings
from main import create_app
from services.llm.base import LLMError, LLMProvider, LLMReply


class FakeProvider(LLMProvider):
    def __init__(self, reply=None, error=None):
        self.reply = reply if reply is not None else LLMReply(text="Nova online")
        self.error = error
        self.calls = []
        self.closed = False

    async def generate(self, message, *, system_prompt):
        self.calls.append((message, system_prompt))
        if self.error:
            raise self.error
        return self.reply

    async def close(self):
        self.closed = True


def test_agent_sends_prompt_returns_text_without_history():
    provider = FakeProvider()
    agent = Agent(provider)
    for message in ("Hello Nova", "Open my resume"):
        reply = asyncio.run(agent.respond(AgentRequest(message=message)))
        assert reply.message == "Nova online"
        assert reply.result is reply.pending_action is None
    assert provider.calls == [
        ("Hello Nova", SYSTEM_PROMPT),
        ("Open my resume", SYSTEM_PROMPT),
    ]
    assert "search_files" in SYSTEM_PROMPT
    assert "Do not claim" in SYSTEM_PROMPT


@pytest.mark.parametrize(
    "reply",
    [
        LLMReply(),
        LLMReply(text="  "),
        LLMReply(text="ok", tool_call=ToolCall(tool="open_file")),
    ],
)
def test_agent_rejects_empty_and_tool_proposals(reply):
    with pytest.raises(LLMError, match="invalid_response"):
        asyncio.run(
            Agent(FakeProvider(reply=reply)).respond(AgentRequest(message="Open it"))
        )


def test_agent_preserves_known_errors_sanitizes_unknown_errors():
    for error, category in [
        (LLMError("connection"), "connection"),
        (RuntimeError("secret-value"), "provider"),
    ]:
        with pytest.raises(LLMError) as caught:
            asyncio.run(
                Agent(FakeProvider(error=error)).respond(AgentRequest(message="hi"))
            )
        assert str(caught.value) == category


def test_api_success_no_dispatch_and_provider_cleanup(tmp_path, monkeypatch):
    provider = FakeProvider(
        reply=LLMReply(text='{"tool":"open_file","arguments":{"file_id":1}}')
    )
    settings = Settings(
        _env_file=None,
        nova_database_path=tmp_path / "test.db",
        openai_api_key="test-secret",
    )
    with TestClient(create_app(settings, llm_provider=provider)) as client:
        dispatch = Mock(side_effect=AssertionError("Agent must not dispatch tools"))
        monkeypatch.setattr(client.app.state.permissions, "dispatch", dispatch)
        response = client.post("/agent/message", json={"message": "Open my resume"})
        assert response.status_code == 200
        assert response.json() == {
            "message": "No local operation was verified. Nova's current AI tools support indexed file search, file information, arithmetic and confirmation-required file interactions.",
            "result": None,
            "pending_action": None,
        }
        assert "test-secret" not in response.text
        dispatch.assert_not_called()
    assert provider.closed


@pytest.mark.parametrize(
    "body",
    [
        {"message": ""},
        {"message": " \n\t "},
        {"message": "x" * 10001},
        {"message": 1},
        {},
        {"message": "hi", "tools": []},
    ],
)
def test_api_invalid_message(client, body):
    assert client.post("/agent/message", json=body).status_code == 422


def test_message_limit_and_whitespace():
    assert AgentRequest(message="x" * 10000).message == "x" * 10000
    assert AgentRequest(message=" hi ").message == "hi"


def test_api_bounds_raw_body(client):
    assert (
        client.post(
            "/agent/message",
            content=b" " * (128 * 1024 + 1),
            headers={"Content-Type": "application/json"},
        ).status_code
        == 413
    )


@pytest.mark.parametrize(
    ("category", "status"),
    [
        ("configuration", 503),
        ("authentication", 503),
        ("rate_limit", 429),
        ("timeout", 504),
        ("connection", 503),
        ("invalid_response", 502),
        ("provider", 502),
    ],
)
def test_api_provider_errors(client, category, status):
    client.app.state.agent = Agent(FakeProvider(error=LLMError(category)))
    response = client.post("/agent/message", json={"message": "Hello"})
    assert response.status_code == status
    assert response.json()["detail"].startswith("Nova")


def test_api_unexpected_error_does_not_leak(client):
    client.app.state.agent = Agent(FakeProvider(error=RuntimeError("test-secret")))
    response = client.post("/agent/message", json={"message": "Hello"})
    assert response.status_code == 502
    assert "test-secret" not in response.text


def test_no_key_only_disables_ai(file_client):
    client, root = file_client
    (root / "resume.txt").touch()
    response = client.post("/agent/message", json={"message": "Hello Nova"})
    assert response.status_code == 503
    assert response.json() == {"detail": "Nova's AI provider is not configured."}
    assert client.get("/health").status_code == 200
    assert client.post("/files/index").json()["created"] == 1
    result = client.get("/files/search", params={"q": "resume"}).json()
    assert result["total"] == 1
    assert client.get(f"/files/{result['results'][0]['id']}").status_code == 200


def test_standalone_starts_without_key(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = Settings(_env_file=None, nova_database_path=tmp_path / "test.db")
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200
        assert client.post("/agent/message", json={"message": "Hi"}).status_code == 503


@pytest.mark.parametrize(
    "headers", [{"Origin": "https://evil.example"}, {"Sec-Fetch-Site": "cross-site"}]
)
def test_agent_rejects_cross_site_requests(client, headers):
    assert (
        client.post(
            "/agent/message", json={"message": "Hi"}, headers=headers
        ).status_code
        == 403
    )


def test_agent_requires_json(client):
    assert client.post("/agent/message", content='{"message":"Hi"}').status_code == 415


def test_settings_environment(monkeypatch):
    for name, value in {
        "OPENAI_API_KEY": "test-secret",
        "OPENAI_MODEL": "configured-model",
        "OPENAI_TIMEOUT_SECONDS": "15",
        "OPENAI_MAX_OUTPUT_TOKENS": "128",
    }.items():
        monkeypatch.setenv(name, value)
    settings = Settings(_env_file=None)
    assert settings.openai_model == "configured-model"
    assert settings.openai_timeout_seconds == 15
    assert settings.openai_max_output_tokens == 128
    assert "test-secret" not in repr(settings)
    assert "test-secret" not in settings.model_dump_json()


@pytest.mark.parametrize(
    "values",
    [
        {"openai_timeout_seconds": 0},
        {"openai_timeout_seconds": float("inf")},
        {"openai_max_output_tokens": 0},
        {"openai_model": " "},
    ],
)
def test_invalid_provider_settings(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_body_limit_without_content_length():
    from api.agent import AgentBodyLimitMiddleware, MAX_AGENT_BODY_BYTES

    async def check():
        async def consume(scope, receive, send):
            while True:
                message = await receive()
                if not message.get("more_body", False):
                    break
            pytest.fail("Oversized streamed body reached the application")

        chunks = iter(
            [
                {
                    "type": "http.request",
                    "body": b" " * MAX_AGENT_BODY_BYTES,
                    "more_body": True,
                },
                {"type": "http.request", "body": b" ", "more_body": False},
            ]
        )
        sent = []

        async def receive():
            return next(chunks)

        async def send(message):
            sent.append(message)

        await AgentBodyLimitMiddleware(consume)(
            {"type": "http", "path": "/agent/message", "headers": []}, receive, send
        )
        assert sent[0]["status"] == 413

    asyncio.run(check())
