"""Bounded process-local conversation state. No execution or authorization cache."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
import json
from threading import RLock
from time import monotonic
from uuid import uuid4

from agent.schemas import ExecutionRecord
from services.llm.base import ConversationTurn


class ConversationError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        self.status = status
        self.detail = detail
        super().__init__(detail)


@dataclass(frozen=True)
class FileReference:
    file_id: int
    name: str


@dataclass(frozen=True)
class ReferenceSet:
    files: tuple[FileReference, ...]
    total: int
    source: str
    turn: int
    timestamp: float


@dataclass(frozen=True)
class ConversationSnapshot:
    conversation_id: str
    history: tuple[ConversationTurn, ...]
    references: ReferenceSet | None


@dataclass
class _Session:
    owner: object
    created_at: float
    updated_at: float
    turns: list[tuple[int, ConversationTurn]] = field(default_factory=list)
    references: ReferenceSet | None = None
    sequence: int = 0
    busy: bool = False


class ConversationStore:
    def __init__(
        self,
        *,
        timeout: float = 1800,
        max_sessions: int = 32,
        max_messages: int = 20,
        max_message_chars: int = 10000,
        max_context_bytes: int = 65536,
        max_references: int = 50,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if (
            min(
                timeout,
                max_sessions,
                max_message_chars,
                max_context_bytes,
                max_references,
            )
            <= 0
            or max_messages < 2
        ):
            raise ValueError("Conversation limits must be positive and allow a turn.")
        self.timeout = timeout
        self.max_sessions = max_sessions
        self.max_messages = max_messages
        self.max_message_chars = max_message_chars
        self.max_context_bytes = max_context_bytes
        self.max_references = max_references
        self._clock = clock
        self._sessions: dict[str, _Session] = {}
        self._lock = RLock()

    def _expire(self) -> None:
        now = self._clock()
        for key, session in list(self._sessions.items()):
            if not session.busy and now - session.updated_at >= self.timeout:
                del self._sessions[key]

    def _lookup(self, conversation_id: str, owner: object) -> _Session:
        session = self._sessions.get(conversation_id)
        if session is None or session.owner is not owner:
            # Same response for absent, expired, cleared and unauthorized IDs.
            raise ConversationError(
                404,
                "Conversation unavailable. Start a new conversation and search again.",
            )
        if session.busy:
            raise ConversationError(
                409, "A conversation request is already in progress."
            )
        return session

    @contextmanager
    def turn(
        self, conversation_id: str | None, owner: object
    ) -> Iterator[ConversationSnapshot]:
        with self._lock:
            self._expire()
            if conversation_id is None:
                if len(self._sessions) >= self.max_sessions:
                    # Do not let unauthenticated callers evict managed conversations.
                    candidates = [
                        (s.updated_at, key)
                        for key, s in self._sessions.items()
                        if not s.busy and s.owner is owner
                    ]
                    if not candidates:
                        raise ConversationError(
                            503, "Conversation capacity reached. Try again later."
                        )
                    del self._sessions[min(candidates)[1]]
                conversation_id = str(uuid4())
                now = self._clock()
                self._sessions[conversation_id] = _Session(owner, now, now)
            session = self._lookup(conversation_id, owner)
            session.busy = True
            snapshot = ConversationSnapshot(
                conversation_id, tuple(t for _, t in session.turns), session.references
            )
        try:
            yield snapshot
        finally:
            with self._lock:
                session.busy = False
                session.updated_at = self._clock()
                # Failed first requests without verified outcomes need no storage.
                if session.sequence == 0:
                    self._sessions.pop(conversation_id, None)

    def commit(
        self,
        snapshot: ConversationSnapshot,
        user: str,
        assistant: str,
        records: list[ExecutionRecord],
    ) -> None:
        """Called under the per-session busy lease, including verified failures."""
        with self._lock:
            session = self._sessions[snapshot.conversation_id]
            if not session.busy:
                raise RuntimeError("A conversation turn lease is required.")
            if len(user) > self.max_message_chars:
                raise ConversationError(422, "Conversation message is too long.")
            session.sequence += 1
            sequence = session.sequence
            # Never slice JSON, a filename or a tool sequence into partial data.
            if len(assistant) > self.max_message_chars:
                assistant = "Previous response omitted because it exceeded the stored message limit."
                # Keep compact verified outcomes, especially side effects, without
                # slicing result JSON or retaining large path metadata.
                if records:
                    assistant += " Verified outcomes (untrusted data): " + json.dumps(
                        [
                            {
                                "tool": r.tool_name,
                                "status": r.result.get("status"),
                                "file_id": (r.result.get("data") or {}).get("file_id"),
                            }
                            for r in records
                        ]
                    )
            if len(assistant) > self.max_message_chars:
                assistant = "Response omitted; search again."[: self.max_message_chars]
            session.turns.append((sequence, ConversationTurn(user, assistant)))
            for record in records:
                if record.tool_name not in {"search_files", "get_file_info"}:
                    continue
                # Even failed/empty newer lookups invalidate the older selection.
                session.references = None
                if not (
                    record.executed
                    and record.state == "completed"
                    and record.result.get("success")
                ):
                    continue
                data = record.result["data"]
                rows = data["results"] if record.tool_name == "search_files" else [data]
                if (
                    not rows
                    or len(rows) > self.max_references
                    or not all(
                        isinstance(r, dict)
                        and type(r.get("id")) is int
                        and 0 < r["id"] <= 2**63 - 1
                        and isinstance(r.get("name"), str)
                        for r in rows
                    )
                ):
                    continue
                session.references = ReferenceSet(
                    tuple(FileReference(r["id"], r["name"]) for r in rows),
                    data["total"] if record.tool_name == "search_files" else 1,
                    record.tool_name,
                    sequence,
                    self._clock(),
                )
            while session.turns and (
                len(session.turns) * 2 > self.max_messages
                or self.context_size(tuple(t for _, t in session.turns))
                > self.max_context_bytes
            ):
                session.turns.pop(0)
            if session.references and session.references.turn not in {
                n for n, _ in session.turns
            }:
                session.references = None

    @staticmethod
    def context_size(history: tuple[ConversationTurn, ...]) -> int:
        return len(
            json.dumps(
                [{"user": t.user, "assistant": t.assistant} for t in history],
                ensure_ascii=True,
            ).encode()
        )

    def clear(self, conversation_id: str, owner: object) -> None:
        with self._lock:
            self._expire()
            self._lookup(conversation_id, owner)
            del self._sessions[conversation_id]
