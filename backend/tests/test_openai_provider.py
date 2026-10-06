import asyncio
import json
import logging
from unittest.mock import patch

import httpx2
import pytest
from openai import AsyncOpenAI

from config.settings import Settings
from services.llm.base import LLMError
from services.llm.openai_provider import OpenAIProvider


def response_body(text="Nova online", status="completed"):
    return {
        "id": "resp_test",
        "object": "response",
        "created_at": 1,
        "model": "test-model",
        "status": status,
        "error": None,
        "output": [
            {
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            }
        ],
    }


async def run_provider(handler, *, timeout=1):
    settings = Settings(
        _env_file=None,
        openai_api_key="test-secret",
        openai_model="test-model",
        openai_timeout_seconds=timeout,
        openai_max_output_tokens=128,
    )
    provider = OpenAIProvider(settings)
    client = AsyncOpenAI(
        api_key="test-secret",
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    )
    with patch(
        "services.llm.openai_provider.AsyncOpenAI", return_value=client
    ) as factory:
        try:
            reply = await provider.generate(
                "private prompt", system_prompt="system prompt"
            )
            await provider.generate("second prompt", system_prompt="system prompt")
            factory.assert_called_once_with(
                api_key="test-secret",
                base_url="https://api.openai.com/v1",
                timeout=timeout,
                max_retries=0,
            )
            return reply
        finally:
            await provider.close()
            assert client.is_closed()


def test_sdk_payload_text_only_and_client_reuse(caplog):
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx2.Response(200, json=response_body())

    caplog.set_level(logging.INFO)
    assert asyncio.run(run_provider(handler)).text == "Nova online"
    assert requests == [
        {
            "model": "test-model",
            "instructions": "system prompt",
            "input": message,
            "max_output_tokens": 128,
            "store": False,
        }
        for message in ("private prompt", "second prompt")
    ]
    assert "request completed" in caplog.text
    assert "private prompt" not in caplog.text
    assert "test-secret" not in caplog.text


@pytest.mark.parametrize(
    ("status", "category"),
    [
        (401, "authentication"),
        (403, "authentication"),
        (429, "rate_limit"),
        (500, "provider"),
        (400, "provider"),
    ],
)
def test_sdk_http_errors_sanitized_no_retries(status, category, caplog):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx2.Response(
            status,
            json={"error": {"message": "test-secret private prompt", "type": "test"}},
        )

    with pytest.raises(LLMError, match=category) as caught:
        asyncio.run(run_provider(handler))
    assert len(calls) == 1
    assert "test-secret" not in str(caught.value) + caplog.text
    assert "private prompt" not in caplog.text
    assert f"category={category}" in caplog.text


@pytest.mark.parametrize(
    ("error_type", "category"),
    [(httpx2.ConnectError, "connection"), (httpx2.ReadTimeout, "timeout")],
)
def test_transport_failures(error_type, category):
    def handler(request):
        raise error_type("test-secret")

    with pytest.raises(LLMError, match=category):
        asyncio.run(run_provider(handler))


@pytest.mark.parametrize(
    "body",
    [
        response_body(""),
        response_body("  "),
        response_body(status="incomplete"),
        response_body(status="failed"),
        {},
        {
            **response_body(),
            "output": [
                {
                    "type": "function_call",
                    "name": "open_file",
                    "arguments": "{}",
                    "call_id": "call_test",
                    "id": "fc_test",
                }
            ],
        },
        {**response_body(), "output": None},
    ],
)
def test_empty_malformed_incomplete_and_tool_output_rejected(body):
    with pytest.raises(LLMError, match="invalid_response"):
        asyncio.run(run_provider(lambda request: httpx2.Response(200, json=body)))


def test_non_json_response_rejected():
    with pytest.raises(LLMError, match="invalid_response"):
        asyncio.run(
            run_provider(
                lambda request: httpx2.Response(
                    200, text="not json", headers={"content-type": "application/json"}
                )
            )
        )


def test_total_deadline():
    async def handler(request):
        await asyncio.sleep(1)
        return httpx2.Response(200, json=response_body())

    with pytest.raises(LLMError, match="timeout"):
        asyncio.run(run_provider(handler, timeout=0.01))


def test_missing_key_never_constructs_client():
    async def check():
        provider = OpenAIProvider(Settings(_env_file=None, openai_api_key=" "))
        with patch("services.llm.openai_provider.AsyncOpenAI") as factory:
            with pytest.raises(LLMError, match="configuration"):
                await provider.generate("hi", system_prompt="system")
            factory.assert_not_called()
        await provider.close()

    asyncio.run(check())


def test_unexpected_sdk_error_sanitized(caplog):
    from unittest.mock import AsyncMock

    async def check():
        provider = OpenAIProvider(
            Settings(_env_file=None, openai_api_key="test-secret")
        )
        client = AsyncMock()
        client.responses.create.side_effect = RuntimeError("test-secret")
        with patch("services.llm.openai_provider.AsyncOpenAI", return_value=client):
            with pytest.raises(LLMError, match="provider"):
                await provider.generate("hi", system_prompt="system")
            await provider.close()
        client.close.assert_awaited_once()

    asyncio.run(check())
    assert "test-secret" not in caplog.text
