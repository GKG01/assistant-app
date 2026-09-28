import ctypes
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from services import file_actions
from services.file_actions import WindowsFileLauncher


def test_windows_open_has_fixed_verb_no_arguments(tmp_path, monkeypatch):
    startfile = Mock()
    monkeypatch.setattr(file_actions, "os", SimpleNamespace(name="nt", startfile=startfile))
    file = tmp_path / "resume.txt"
    WindowsFileLauncher().open_file(file)
    startfile.assert_called_once_with(str(file), "open")


def test_windows_reveal_uses_pidl_and_frees_it(tmp_path, monkeypatch):
    ole32 = SimpleNamespace(CoInitializeEx=Mock(return_value=0), CoUninitialize=Mock(),
                            CoTaskMemFree=Mock())
    def parse(name, context, output, flags, attributes):
        output._obj.value = 1234
        return 0
    shell32 = SimpleNamespace(SHParseDisplayName=Mock(side_effect=parse),
                              SHOpenFolderAndSelectItems=Mock(return_value=0))
    def library(name, **kwargs):
        return {"ole32": ole32, "shell32": shell32}[name]
    monkeypatch.setattr(file_actions, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(ctypes, "WinDLL", library, raising=False)
    file = tmp_path / "resume.txt"
    WindowsFileLauncher().show_in_folder(file)
    assert shell32.SHParseDisplayName.call_args.args[0] == str(file)
    assert shell32.SHOpenFolderAndSelectItems.call_args.args[0].value == 1234
    assert shell32.SHOpenFolderAndSelectItems.call_args.args[1:] == (0, None, 0)
    ole32.CoTaskMemFree.assert_called_once()
    ole32.CoUninitialize.assert_called_once()


def test_non_windows_actions_report_unsupported(tmp_path, monkeypatch):
    monkeypatch.setattr(file_actions, "os", SimpleNamespace(name="posix"))
    launcher = WindowsFileLauncher()
    with pytest.raises(NotImplementedError):
        launcher.open_file(tmp_path / "file.txt")
    with pytest.raises(NotImplementedError):
        launcher.show_in_folder(tmp_path / "file.txt")
