"""Non-overwriting single-object mutations. No model or HTTP authorization here."""

import ctypes
import os
import re
import stat
import sys
from threading import Lock
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from permissions.windows_handles import WindowsHandles
from services.file_search import FileSearchService


class MutationError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def component(value: str) -> str:
    if (
        not value
        or len(value.encode("utf-16-le")) > 240
        or value in {".", ".."}
        or value.endswith((".", " "))
        or any(ord(c) < 32 or c in '/\\:*?"<>|' for c in value)
        or re.fullmatch(
            r"(?i)(CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³])(?:\..*)?",
            value,
        )
    ):
        raise ValueError(
            "Use a single valid Windows filename (at most 120 UTF-16 units)."
        )
    return value


def identity(path: Path, *, directory: bool = False) -> tuple[int, ...]:
    info = path.lstat()
    if (
        stat.S_ISLNK(info.st_mode)
        or getattr(info, "st_file_attributes", 0) & 0x400
        or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
    ):
        raise PermissionError("Unsupported filesystem object.")
    if not info.st_ino or (not directory and info.st_nlink != 1):
        raise PermissionError("Stable single-link identity is required.")
    return (
        (info.st_dev, info.st_ino)
        if directory
        else (
            info.st_dev,
            info.st_ino,
            info.st_size,
            info.st_mtime_ns,
            info.st_ctime_ns,
        )
    )


@dataclass(frozen=True)
class MutationPlan:
    tool: str
    source: Path | None
    destination: Path
    file_id: int | None
    source_identity: tuple[int, ...] | None
    parent_identity: tuple[int, ...]
    source_parent_identity: tuple[int, ...] | None


class FileMutationService:
    def __init__(self, search: FileSearchService, *, lock=None):
        self.search = search
        self._lock = lock if lock is not None else Lock()

    def prepare(
        self, tool: str, arguments: dict, directories: dict[str, Path]
    ) -> MutationPlan:
        policy = self.search.policy
        source = None
        file_id = arguments.get("file_id")
        if file_id is not None:
            row = self.search.get_file_info(file_id)
            source = policy.validate(Path(row.path), must_exist=True)
            info = source.stat()
            if (
                info.st_size != row.size
                or abs(info.st_mtime - row.modified_at.timestamp()) > 0.000002
            ):
                raise MutationError(
                    "STALE_SOURCE",
                    "Indexed metadata changed. Refresh the index and request again.",
                )
        if tool == "rename_file":
            parent = source.parent
            name = component(arguments["new_name"])
        else:
            key = arguments[
                "parent_directory_id"
                if tool == "create_folder"
                else "destination_directory_id"
            ]
            if key not in directories:
                raise PermissionError("Directory reference unavailable.")
            parent = policy.validate_root(directories[key])
            name = component(
                arguments["folder_name"] if source is None else source.name
            )
        destination = policy.validate(parent / name)
        if len(str(destination)) >= 240:
            raise MutationError(
                "UNSUPPORTED_PATH", "Long mutation paths are not supported."
            )
        plan = MutationPlan(
            tool,
            source,
            destination,
            file_id,
            identity(source) if source else None,
            identity(parent, directory=True),
            identity(source.parent, directory=True) if source else None,
        )
        self.revalidate(plan)
        return plan

    def revalidate(self, plan: MutationPlan) -> None:
        policy = self.search.policy
        parent = policy.validate_root(plan.destination.parent)
        policy.validate(plan.destination)
        if identity(parent, directory=True) != plan.parent_identity:
            raise MutationError(
                "STALE_DESTINATION",
                "Destination directory changed. Request a new action.",
            )
        if any(
            p.name.casefold() == plan.destination.name.casefold()
            for p in parent.iterdir()
        ):
            raise MutationError(
                "DESTINATION_EXISTS",
                "The destination already exists. Nothing was overwritten.",
            )
        if plan.source:
            row = self.search.get_file_info(plan.file_id)
            if (
                Path(row.path) != plan.source
                or identity(plan.source) != plan.source_identity
                or identity(plan.source.parent, directory=True)
                != plan.source_parent_identity
            ):
                raise MutationError(
                    "STALE_SOURCE",
                    "The source changed. Refresh the index and request again.",
                )
            if plan.source_identity[0] != plan.parent_identity[0]:
                raise MutationError(
                    "CROSS_VOLUME", "Cross-volume moves are not supported."
                )

    @contextmanager
    def pinned(self, plan: MutationPlan) -> Iterator[tuple[object, dict[Path, int]]]:
        paths = [plan.destination.parent] + ([plan.source] if plan.source else [])
        components = sorted(
            {p for path in paths for p in (*path.parents, path)},
            key=lambda p: len(p.parts),
        )
        with ExitStack() as stack:
            handles = {}
            if os.name == "nt":
                native = WindowsHandles()
                for path in components:
                    handle = native.open(
                        path,
                        pin_name=any(
                            path.is_relative_to(r) for r in self.search.policy.roots
                        ),
                    )
                    stack.callback(native.close, handle)
                    final, attributes = native.inspect(handle)
                    if (
                        final != path
                        or attributes & 0x400
                        or bool(attributes & 0x10) != (path != plan.source)
                    ):
                        raise PermissionError("Path changed while pinning.")
                    handles[path] = handle
            elif sys.platform == "linux":
                native = None
                for path in components:
                    if path == plan.source:
                        continue
                    parent_fd = handles.get(path.parent)
                    fd = os.open(
                        path.name if parent_fd is not None else str(path),
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=parent_fd,
                    )
                    stack.callback(os.close, fd)
                    handles[path] = fd
            else:
                raise NotImplementedError(
                    "Safe mutations are unsupported on this platform."
                )
            self.revalidate(plan)
            for path, handle in handles.items():
                if os.name != "nt" and (
                    os.fstat(handle).st_dev,
                    os.fstat(handle).st_ino,
                ) != identity(path, directory=True):
                    raise PermissionError("Pinned directory changed.")
            yield native, handles

    def execute(self, plan: MutationPlan) -> dict:
        if not self._lock.acquire(blocking=False):
            raise MutationError(
                "FILESYSTEM_BUSY",
                "An index refresh or mutation is running. Request a new action later.",
            )
        try:
            return self._execute(plan)
        finally:
            self._lock.release()

    def _execute(self, plan: MutationPlan) -> dict:
        with self.pinned(plan) as (native, handles):
            if plan.source is None:
                if os.name == "nt":
                    plan.destination.mkdir()
                else:
                    os.mkdir(
                        plan.destination.name, dir_fd=handles[plan.destination.parent]
                    )
            elif os.name == "nt":
                windows_rename(native, handles[plan.source], plan.destination)
            else:
                linux_rename(
                    handles[plan.source.parent],
                    plan.source.name,
                    handles[plan.destination.parent],
                    plan.destination.name,
                )
        # Never undo an already successful filesystem operation to repair the index.
        try:
            if plan.file_id is not None:
                self.search.repository.relocate(
                    plan.file_id, plan.source, plan.destination, self.search.policy
                )
        except Exception:  # Mutation already succeeded; never report it as unexecuted.
            return {
                "filesystem_succeeded": True,
                "index_synchronized": False,
                "message": "Filesystem operation completed, but index synchronization failed. Refresh the file index before using search results.",
            }
        return {
            "filesystem_succeeded": True,
            "index_synchronized": True,
            "message": "Filesystem operation completed and index synchronized.",
        }


def linux_rename(
    source_fd: int, source: str, destination_fd: int, destination: str
) -> None:
    api = ctypes.CDLL(None, use_errno=True)
    rename = getattr(api, "renameat2", None)
    if rename is None:
        raise NotImplementedError("No no-replace rename primitive.")
    rename.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    rename.restype = ctypes.c_int
    if rename(
        source_fd, os.fsencode(source), destination_fd, os.fsencode(destination), 1
    ):
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code))


def windows_rename(native: WindowsHandles, source: int, destination: Path) -> None:
    from ctypes import wintypes

    class RenameInfo(ctypes.Structure):
        _fields_ = [
            ("flags", wintypes.DWORD),
            ("root", wintypes.HANDLE),
            ("length", wintypes.DWORD),
            ("name", wintypes.WCHAR * 1),
        ]

    encoded = str(destination).encode("utf-16-le")
    buffer = ctypes.create_string_buffer(
        max(ctypes.sizeof(RenameInfo), RenameInfo.name.offset + len(encoded) + 2)
    )
    info = RenameInfo.from_buffer(buffer)
    info.flags = 0  # ReplaceIfExists FALSE; never fall back to copy/delete.
    info.root = None
    info.length = len(encoded)
    ctypes.memmove(
        ctypes.addressof(buffer) + RenameInfo.name.offset, encoded, len(encoded)
    )
    rename = native.api.SetFileInformationByHandle
    rename.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    rename.restype = wintypes.BOOL
    if not rename(source, 3, buffer, len(buffer)):
        raise ctypes.WinError(ctypes.get_last_error())
