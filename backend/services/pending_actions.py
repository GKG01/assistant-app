"""Volatile bounded proposals; a conversation lease is required for every decision."""

from dataclasses import dataclass
from collections.abc import Callable
from typing import Any
from itertools import islice
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from time import time
from uuid import uuid4

from services.file_mutations import FileMutationService, MutationPlan, MutationError
from services.conversations import ConversationError


@dataclass
class StoredAction:
    action_id: str
    conversation_id: str
    owner: object
    arguments: dict[str, Any]
    plan: MutationPlan
    created: float
    expires: float
    status: str = "pending"

    def view(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "conversation_id": self.conversation_id,
            "tool_name": self.plan.tool,
            "status": self.status,
            "created_at": datetime.fromtimestamp(
                self.created, timezone.utc
            ).isoformat(),
            "expires_at": datetime.fromtimestamp(
                self.expires, timezone.utc
            ).isoformat(),
            "source_name": self.plan.source.name if self.plan.source else None,
            "destination_name": self.plan.destination.name,
            "directory_name": self.plan.destination.parent.name,
            # Frozen canonical paths, never model prose or a fresh index lookup.
            # Full roots are necessary when approved directories share a name.
            "source_path": str(self.plan.source) if self.plan.source else None,
            "destination_path": str(self.plan.destination),
            "file_id": self.plan.file_id,
        }


class PendingActionStore:
    def __init__(
        self,
        service: FileMutationService,
        *,
        ttl: float = 120,
        capacity: int = 128,
        clock: Callable[[], float] = time,
    ) -> None:
        if ttl <= 0 or capacity <= 0:
            raise ValueError("Pending-action limits must be positive.")
        self.service, self.ttl, self.capacity, self.clock = (
            service,
            ttl,
            capacity,
            clock,
        )
        self._actions: dict[str, StoredAction] = {}
        self._directories: dict[str, tuple[object, float, dict[str, Path]]] = {}
        self._lock = RLock()

    def _cleanup(self) -> None:
        now = self.clock()
        for action in self._actions.values():
            if action.status == "pending" and now >= action.expires:
                action.status = "expired"
        self._actions = {
            k: a for k, a in self._actions.items() if now < a.expires + self.ttl
        }
        self._directories = {k: v for k, v in self._directories.items() if now < v[1]}

    def directories(self, cid: str, owner: object) -> list[dict]:
        with self._lock:
            self._cleanup()
            if cid not in self._directories and len(self._directories) >= 32:
                raise ConversationError(
                    503, "Directory reference capacity reached. Try later."
                )
            old = self._directories.get(cid)
            if old and old[0] is not owner:
                raise ConversationError(404, "Directory references unavailable.")
            paths = {}
            for root in self.service.search.policy.roots:
                try:
                    root = self.service.search.policy.validate_root(root)
                    paths[root] = str(root)
                    for child in islice(root.iterdir(), 256):
                        if len(paths) >= 64:
                            break
                        try:
                            child = self.service.search.policy.validate_root(child)
                            paths[child] = str(child)
                        except (OSError, ValueError):
                            continue
                except (OSError, ValueError):
                    continue
                if len(paths) >= 64:
                    break
            previous = {p: key for key, p in old[2].items()} if old else {}
            references = {previous.get(p, uuid4().hex): p for p in paths}
            self._directories[cid] = (owner, self.clock() + self.ttl, references)
            return [
                {"directory_id": key, "label": paths[p]}
                for key, p in references.items()
            ]

    def prepare(self, tool: str, arguments: dict, cid: str, owner: object) -> dict:
        with self._lock:
            self._cleanup()
            if len(self._actions) >= self.capacity:
                raise MutationError(
                    "ACTION_LIMIT",
                    "Pending action capacity reached. Wait for expiration.",
                )
            # One outstanding write per conversation: no batch mutation workflows.
            if any(
                a.conversation_id == cid and a.status == "pending"
                for a in self._actions.values()
            ):
                raise MutationError(
                    "ACTION_PENDING", "Confirm or cancel the existing action first."
                )
            catalog = self._directories.get(cid)
            if not catalog or catalog[0] is not owner:
                raise PermissionError("Directory context unavailable.")
            plan = self.service.prepare(tool, arguments, catalog[2])
            now = self.clock()
            action = StoredAction(
                str(uuid4()), cid, owner, dict(arguments), plan, now, now + self.ttl
            )
            self._actions[action.action_id] = action
            return action.view()

    def consume(
        self, action_id: str, cid: str, owner: object, *, cancel: bool
    ) -> StoredAction:
        with self._lock:
            self._cleanup()
            action = self._actions.get(action_id)
            if not action or action.owner is not owner or action.conversation_id != cid:
                raise ConversationError(404, "Action unavailable.")
            if action.status != "pending":
                failure = ConversationError(
                    409, "Action is " + action.status + "; it cannot execute again."
                )
                failure.action_status = action.status
                raise failure
            action.status = "cancelled" if cancel else "executing"
            return action

    def invalidate(self, cid: str) -> None:
        with self._lock:
            for action in self._actions.values():
                if action.conversation_id == cid and action.status == "pending":
                    action.status = "cancelled"
            self._directories.pop(cid, None)
