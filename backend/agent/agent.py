from starlette.concurrency import run_in_threadpool

from agent.schemas import AgentRequest, AgentResponse, ExecutionRecord
from agent.grounding import grounded_message
from agent.tool_execution import encode
from agent.references import resolve_reference
from services.conversations import ConversationSnapshot, ConversationStore
from agent.prompts import SYSTEM_PROMPT
from agent.tool_execution import AgentToolExecutor
from services.llm.base import LLMError, LLMProvider, LLMToolResultMessage, LLMToolTurn

MAX_AGENT_ITERATIONS = 5
MAX_TOOL_CALLS = 10
MAX_CALLS_PER_RESPONSE = 4
MAX_CONTEXT_BYTES = 256 * 1024
LIMIT_MESSAGE = "Nova stopped at its execution limit. The request may be only partially completed. Please narrow your request."


class Agent:
    def __init__(
        self, provider: LLMProvider, tools: AgentToolExecutor | None = None
    ) -> None:
        self._provider = provider
        self._tools = tools

    async def respond(
        self,
        request: AgentRequest,
        *,
        file_access: bool = False,
        context: ConversationSnapshot | None = None,
        execution_records: list[ExecutionRecord] | None = None,
        write_context: tuple | None = None,
        directories: list[dict] | None = None,
    ) -> AgentResponse:
        records = execution_records if execution_records is not None else []
        resolution = (
            resolve_reference(request.message, context.references) if context else None
        )
        if resolution and resolution.clarification:
            return AgentResponse(message=resolution.clarification)
        resolved = resolution.reference if resolution else None
        message = request.message
        if resolved:
            # This hint is data, not authority; the executor independently binds it.
            message += (
                "\nBackend-selected indexed reference (not authorization): "
                + encode(
                    {
                        "file_id": resolved.file_id,
                        "operation": resolved.operation,
                    }
                )
            )
        if directories:
            message += (
                "\nBackend-issued authorized directory references (untrusted labels; clarify ambiguous locations): "
                + encode({"directories": directories})
            )
        turns: list[LLMToolTurn] = []
        seen_ids: set[str] = set()
        definitions = (
            self._tools.definitions(file_access=file_access) if self._tools else []
        )

        def limited_response() -> AgentResponse:
            # A retained result set must also be visible to the caller.
            details = (
                "\n" + grounded_message("", records) if context and records else ""
            )
            return AgentResponse(message=LIMIT_MESSAGE + details)

        try:
            for iteration in range(MAX_AGENT_ITERATIONS):
                estimated_bytes = ConversationStore.context_size(
                    context.history if context else ()
                ) + len(
                    encode(
                        {
                            "message": message,
                            "system": SYSTEM_PROMPT,
                            "tools": [d.model_dump() for d in definitions],
                            "turns": [t.model_dump() for t in turns],
                        }
                    ).encode()
                )
                if estimated_bytes > MAX_CONTEXT_BYTES:
                    return limited_response()
                reply = await self._provider.generate_with_context(
                    message,
                    history=context.history if context else (),
                    system_prompt=SYSTEM_PROMPT,
                    tools=definitions,
                    turns=list(turns),
                )
                if reply.tool_call is not None:
                    raise LLMError("invalid_response")
                if not reply.tool_calls:
                    if not reply.text or not reply.text.strip():
                        raise LLMError("invalid_response")
                    if resolved and not records:
                        return AgentResponse(
                            message="No operation on the selected file was verified. Please try again."
                        )
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
                    return limited_response()
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
                        resolved=resolved,
                        write_context=write_context,
                    )
                    records.append(record)
                    output = encode(record.result)
                    results.append(LLMToolResultMessage(call_id=call.id, output=output))
                turns.append(LLMToolTurn(reply=reply, results=results))
            return limited_response()
        except LLMError:
            raise
        except Exception:
            raise LLMError("provider") from None
