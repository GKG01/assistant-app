from starlette.concurrency import run_in_threadpool

from agent.schemas import AgentRequest, AgentResponse, ExecutionRecord
from agent.grounding import grounded_message
from agent.tool_execution import encode
from agent.prompts import SYSTEM_PROMPT
from agent.tool_execution import AgentToolExecutor
from services.llm.base import LLMError, LLMProvider, LLMToolResultMessage, LLMToolTurn

MAX_AGENT_ITERATIONS = 5
MAX_TOOL_CALLS = 10
MAX_CALLS_PER_RESPONSE = 4
LIMIT_MESSAGE = "Nova stopped at its execution limit. The request may be only partially completed. Please narrow your request."


class Agent:
    def __init__(
        self, provider: LLMProvider, tools: AgentToolExecutor | None = None
    ) -> None:
        self._provider = provider
        self._tools = tools

    async def respond(
        self, request: AgentRequest, *, file_access: bool = False
    ) -> AgentResponse:
        records: list[ExecutionRecord] = []
        turns: list[LLMToolTurn] = []
        seen_ids: set[str] = set()
        definitions = (
            self._tools.definitions(file_access=file_access) if self._tools else []
        )
        try:
            for iteration in range(MAX_AGENT_ITERATIONS):
                reply = await self._provider.generate_with_tools(
                    request.message,
                    system_prompt=SYSTEM_PROMPT,
                    tools=definitions,
                    turns=list(turns),
                )
                if reply.tool_call is not None:
                    raise LLMError("invalid_response")
                if not reply.tool_calls:
                    if not reply.text or not reply.text.strip():
                        raise LLMError("invalid_response")
                    return AgentResponse(
                        message=grounded_message(reply.text.strip(), records)
                    )
                ids = [call.id for call in reply.tool_calls]
                if len(set(ids)) != len(ids) or seen_ids.intersection(ids):
                    raise LLMError("invalid_response")
                if (
                    len(ids) > MAX_CALLS_PER_RESPONSE
                    or len(seen_ids) + len(ids) > MAX_TOOL_CALLS
                    or iteration == MAX_AGENT_ITERATIONS - 1
                ):
                    return AgentResponse(message=LIMIT_MESSAGE)
                if self._tools is None:
                    raise LLMError("invalid_response")
                seen_ids.update(ids)
                results = []
                for call in reply.tool_calls:
                    record = await run_in_threadpool(
                        self._tools.execute_record,
                        call,
                        file_access=file_access,
                        history=records,
                    )
                    records.append(record)
                    output = encode(record.result)
                    results.append(LLMToolResultMessage(call_id=call.id, output=output))
                turns.append(LLMToolTurn(reply=reply, results=results))
            return AgentResponse(message=LIMIT_MESSAGE)
        except LLMError:
            raise
        except Exception:
            raise LLMError("provider") from None
