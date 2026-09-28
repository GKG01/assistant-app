import ctypes
import os
from pathlib import Path
from typing import Literal

from database.repositories.actions import ActionRepository
from services.file_models import FileActionResponse
from services.file_search import FileSearchService

OPEN_EXTENSIONS = frozenset({
    ".pdf", ".txt", ".csv", ".png", ".jpg", ".jpeg", ".gif", ".bmp",
    ".webp", ".docx", ".xlsx", ".pptx",
})


class WindowsFileLauncher:
    """Only two fixed OS capabilities; no command strings or subprocess interface."""

    def open_file(self, path: Path) -> None:
        if os.name != "nt":
            raise NotImplementedError("Open File requires the Windows-native backend.")
        os.startfile(str(path), "open")

    def show_in_folder(self, path: Path) -> None:
        if os.name != "nt":
            raise NotImplementedError("Show in Folder requires the Windows-native backend.")
        # A fully qualified PIDL with cidl=0 selects that item in its parent folder.
        from ctypes import wintypes

        ole32 = ctypes.WinDLL("ole32", use_last_error=True)
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        ole32.CoInitializeEx.restype = ctypes.c_long
        ole32.CoUninitialize.argtypes = []
        ole32.CoUninitialize.restype = None
        ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        ole32.CoTaskMemFree.restype = None
        shell32.SHParseDisplayName.argtypes = [
            wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
            wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
        ]
        shell32.SHParseDisplayName.restype = ctypes.c_long
        shell32.SHOpenFolderAndSelectItems.argtypes = [
            ctypes.c_void_p, wintypes.UINT, ctypes.c_void_p, wintypes.DWORD,
        ]
        shell32.SHOpenFolderAndSelectItems.restype = ctypes.c_long
        initialized = ole32.CoInitializeEx(None, 2)
        if initialized < 0:
            raise OSError("Windows Explorer initialization failed.")
        item = ctypes.c_void_p()
        attributes = wintypes.DWORD()
        try:
            if shell32.SHParseDisplayName(str(path), None, ctypes.byref(item), 0,
                                         ctypes.byref(attributes)) < 0:
                raise OSError("Windows could not resolve the selected file.")
            if shell32.SHOpenFolderAndSelectItems(item, 0, None, 0) < 0:
                raise OSError("Windows could not reveal the selected file.")
        finally:
            if item:
                ole32.CoTaskMemFree(item)
            ole32.CoUninitialize()


class FileActionService:
    def __init__(self, search: FileSearchService, actions: ActionRepository,
                 launcher: WindowsFileLauncher) -> None:
        self.search = search
        self.actions = actions
        self.launcher = launcher

    def perform(self, file_id: int, action: Literal["open_file", "show_in_folder"]) -> FileActionResponse:
        file = self.search.get_file_info(file_id)
        if action == "open_file" and Path(file.path).suffix.casefold() not in OPEN_EXTENSIONS:
            raise PermissionError("Opening this file type is disabled. Use Show in Folder instead.")
        # Record before invoking the OS; a failed audit write prevents the launch.
        self.actions.record(user_command="Explicit file button", tool=action,
                            arguments={"file_id": file_id}, result=None, status="requested")
        try:
            path = self.search.policy.validate(Path(file.path), must_exist=True)
            if action == "open_file":
                self.launcher.open_file(path)
            else:
                self.launcher.show_in_folder(path)
        except (OSError, NotImplementedError):
            self.actions.record(user_command="Explicit file button", tool=action,
                                arguments={"file_id": file_id}, result=None, status="failed")
            raise
        return FileActionResponse(file_id=file_id, action=action)
