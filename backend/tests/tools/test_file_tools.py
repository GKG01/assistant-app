from unittest.mock import Mock
import sqlite3

import pytest

from agent.schemas import PendingAction, ToolCall
from agent.tool_registry import ToolRegistry
from database.repositories.actions import ActionRepository
from permissions.manager import PermissionManager
from services.file_actions import FileActionService, WindowsFileLauncher
from services.file_models import FileIdInput, SearchFilters
from tools.files import GetFileInfoTool, OpenFileTool, SearchFilesTool, ShowInFolderTool


def test_tools_share_index_and_enforce_paths(file_stack, monkeypatch, tmp_path):
    root, _, repository, indexer, search = file_stack
    file = root / "resume.txt"
    file.touch()
    indexer.index(root)
    monkeypatch.setattr(
        "os.scandir", lambda *a: pytest.fail("Search scanned filesystem")
    )
    response = SearchFilesTool(search).execute(SearchFilters(q="resume"))
    file_id = response["results"][0]["id"]
    assert (
        GetFileInfoTool(search).execute(FileIdInput(file_id=file_id))["name"]
        == "resume.txt"
    )
    with pytest.raises(FileNotFoundError):
        GetFileInfoTool(search).execute(FileIdInput(file_id=99999))
    search.policy.roots = ()
    with pytest.raises(PermissionError):
        GetFileInfoTool(search).execute(FileIdInput(file_id=file_id))


def test_interactive_tools_need_user_context(file_stack):
    root, database, repository, indexer, search = file_stack
    file = root / "resume.pdf"
    file.touch()
    indexer.index(root)
    launcher = Mock(spec=WindowsFileLauncher)
    actions = FileActionService(search, ActionRepository(database), launcher)
    registry = ToolRegistry()
    registry.register(OpenFileTool(actions))
    registry.register(ShowInFolderTool(actions))
    manager = PermissionManager(registry)
    file_id = repository.get_file_by_path(str(file)).id
    for name in ("open_file", "show_in_folder"):
        call = ToolCall(tool=name, arguments={"file_id": file_id})
        assert isinstance(manager.dispatch(call), PendingAction)
        assert manager.dispatch(call, user_initiated=True).status == "completed"
    launcher.open_file.assert_called_once_with(file)
    launcher.show_in_folder.assert_called_once_with(file)


def test_deleted_file_never_launched(file_stack):
    root, database, repository, indexer, search = file_stack
    file = root / "resume.pdf"
    file.touch()
    indexer.index(root)
    file_id = repository.get_file_by_path(str(file)).id
    file.unlink()
    launcher = Mock(spec=WindowsFileLauncher)
    service = FileActionService(search, ActionRepository(database), launcher)
    with pytest.raises(FileNotFoundError):
        service.perform(file_id, "open_file")
    launcher.open_file.assert_not_called()


def test_audit_failure_prevents_launch(file_stack, monkeypatch):
    root, database, repository, indexer, search = file_stack
    file = root / "resume.pdf"
    file.touch()
    indexer.index(root)
    launcher = Mock(spec=WindowsFileLauncher)
    actions = ActionRepository(database)

    def fail(**kwargs):
        raise sqlite3.OperationalError("database unavailable")

    monkeypatch.setattr(actions, "record", fail)
    service = FileActionService(search, actions, launcher)
    with pytest.raises(sqlite3.OperationalError):
        service.perform(repository.get_file_by_path(str(file)).id, "open_file")
    launcher.open_file.assert_not_called()
