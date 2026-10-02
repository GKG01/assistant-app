"""Pin local path components during Windows shell dispatch; never read contents."""

import ctypes
from contextlib import contextmanager, ExitStack
from pathlib import Path
from collections.abc import Iterator
from ctypes import wintypes

from permissions.paths import PathPolicy


class AttributeTag(ctypes.Structure):
    _fields_ = [("attributes", wintypes.DWORD), ("tag", wintypes.DWORD)]


class WindowsHandles:
    def __init__(self) -> None:
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreateFileW": (
                [
                    wintypes.LPCWSTR,
                    wintypes.DWORD,
                    wintypes.DWORD,
                    ctypes.c_void_p,
                    wintypes.DWORD,
                    wintypes.DWORD,
                    wintypes.HANDLE,
                ],
                wintypes.HANDLE,
            ),
            "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
            "GetFileInformationByHandleEx": (
                [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD],
                wintypes.BOOL,
            ),
            "GetFinalPathNameByHandleW": (
                [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD],
                wintypes.DWORD,
            ),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(self.api, name)
            function.argtypes, function.restype = arguments, result

    def open(self, path: Path) -> int:
        # READ_ATTRIBUTES, SHARE_READ only, OPEN_EXISTING, BACKUP_SEMANTICS |
        # OPEN_REPARSE_POINT. Denying write/delete sharing pins each component
        # and fails safely if a conflicting writer already holds it open.
        handle = self.api.CreateFileW(str(path), 0x80, 1, None, 3, 0x02200000, None)
        if handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        return handle

    def close(self, handle: int) -> None:
        self.api.CloseHandle(handle)

    def inspect(self, handle: int) -> tuple[Path, int]:
        info = AttributeTag()
        if not self.api.GetFileInformationByHandleEx(
            handle, 9, ctypes.byref(info), ctypes.sizeof(info)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        buffer = ctypes.create_unicode_buffer(32768)
        length = self.api.GetFinalPathNameByHandleW(handle, buffer, len(buffer), 0)
        if not length or length >= len(buffer):
            raise OSError("Windows could not verify the file handle path.")
        raw = buffer.value
        # Only normalize the documented DOS-device prefix on a local drive.
        if not (raw.startswith("\\\\?\\") and len(raw) > 6 and raw[5:7] == ":\\"):
            raise PermissionError("The handle does not refer to a local drive path.")
        return Path(raw[4:]), info.attributes


@contextmanager
def pinned_file(
    policy: PathPolicy, path: Path, *, handles: WindowsHandles | None = None
) -> Iterator[Path]:
    safe = policy.validate(path, must_exist=True)
    native = handles if handles is not None else WindowsHandles()
    with ExitStack() as stack:
        # Root first: OPEN_REPARSE_POINT alone does not protect intermediate folders.
        for component in (*reversed(safe.parents), safe):
            handle = native.open(component)
            stack.callback(native.close, handle)
            final, attributes = native.inspect(handle)
            if attributes & 0x400 or final != component:
                raise PermissionError(
                    "The file path changed or contains a reparse point."
                )
            if bool(attributes & 0x10) != (component != safe):
                raise PermissionError("The file path has an unexpected object type.")
        # Repeat allowlist validation while every component remains pinned.
        yield policy.validate(safe, must_exist=True)
