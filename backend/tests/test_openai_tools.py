import asyncio
import json

import httpx2
import pytest
from openai import AsyncOpenAI

from config.settings import Settings
from services.llm.base import (
    LLMError,
    LLMToolDefinition,
    LLMToolResultMessage,
    LLMToolTurn,
)
from services.llm.openai_provider import OpenAIProvider
from tests.test_openai_provider import response_body


def function_item(**overrides):
    return {
        "type": "function_call",
        "id": "fc_1",
        "call_id": "call_1",
        "name": "calculate",
        "arguments": '{"expression":"1+2"}',
        "status": "completed",
        **overrides,
    }


async def structured(handler, continuation=False):
    provider = OpenAIProvider(Settings(_env_file=None, openai_api_key="test-key"))
    provider._client = AsyncOpenAI(
        api_key="test-key",
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    )
    try:
        tools = [
            LLMToolDefinition(
                name="calculate",
                description="Arithmetic",
                parameters={
                    "type": "object",
                    "properties": {"expression": {"type": "string"}},
                    "required": ["expression"],
                    "additionalProperties": False,
                },
            )
        ]
        reply = await provider.generate_with_tools(
            "compute", system_prompt="system", tools=tools, turns=[]
        )
        if continuation:
            return await provider.generate_with_tools(
                "compute",
                system_prompt="system",
                tools=tools,
                turns=[
                    LLMToolTurn(
                        reply=reply,
                        results=[
                            LLMToolResultMessage(
                                call_id=c.id,
                                output='{"success":true,"data":{"value":3}}',
                            )
                            for c in reply.tool_calls
                        ],
                    )
                ],
            )
        return reply
    finally:
        await provider.close()


def test_sdk_multiple_calls_replayed_with_reasoning_and_results():
    requests = []
    output = [
        {
            "type": "reasoning",
            "id": "rs_1",
            "summary": [],
            "encrypted_content": "opaque",
        },
        function_item(),
        function_item(id="fc_2", call_id="call_2"),
    ]

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx2.Response(
            200,
            json={**response_body(), "output": output}
            if len(requests) == 1
            else response_body("3"),
        )

    result = asyncio.run(structured(handler, True))
    assert result.text == "3"
    assert requests[0]["tools"][0]["type"] == "function"
    assert requests[0]["tools"][0]["strict"] is False
    assert requests[0]["store"] is False
    assert requests[0]["include"] == ["reasoning.encrypted_content"]
    replay = requests[1]["input"]
    assert replay[1:4] == output
    assert [(i["type"], i["call_id"]) for i in replay[4:]] == [
        ("function_call_output", "call_1"),
        ("function_call_output", "call_2"),
    ]
    assert json.loads(replay[4]["output"])["data"]["value"] == 3


@pytest.mark.parametrize(
    "items",
    [
        [function_item(call_id=None)],
        [function_item(call_id="")],
        [function_item(name=None)],
        [function_item(arguments={})],
        [function_item(status="incomplete")],
        [function_item(namespace="other")],
        [function_item(), function_item()],
        [{"type": "web_search_call", "id": "web", "status": "completed"}],
    ],
)
def test_invalid_structured_provider_output(items):
    with pytest.raises(LLMError, match="invalid_response"):
        asyncio.run(
            structured(
                lambda request: httpx2.Response(
                    200, json={**response_body(), "output": items}
                )
            )
        )


def test_malformed_argument_json_preserved_for_backend_validation():
    result = asyncio.run(
        structured(
            lambda request: httpx2.Response(
                200,
                json={**response_body(), "output": [function_item(arguments="{bad")]},
            )
        )
    )
    assert result.tool_calls[0].arguments == "{bad"
