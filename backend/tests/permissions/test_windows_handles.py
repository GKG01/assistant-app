import os
from pathlib import Path

import pytest

from permissions.paths import PathPolicy
from permissions.windows_handles import pinned_file


class FakeHandles:
    def __init__(self, target, bad=None, failure=None):
        self.target, self.bad, self.failure = target, bad, failure
        self.active = []
        self.closed = []
        self.name_pins = []

    def open(self, path, *, pin_name=False):
        if path == self.failure:
            raise PermissionError("Sharing violation")
        self.active.append(path)
        if pin_name:
            self.name_pins.append(path)
        return path

    def close(self, handle):
        self.active.remove(handle)
        self.closed.append(handle)

    def inspect(self, handle):
        return handle, (0 if handle == self.target else 0x10) | (
            0x400 if handle == self.bad else 0
        )


def test_pins_all_components_until_dispatch_returns(tmp_path):
    target = tmp_path / "file.txt"
    target.touch()
    native = FakeHandles(target)
    with pinned_file(PathPolicy([tmp_path]), target, handles=native) as safe:
        assert safe == target
        assert native.active == [*reversed(target.parents), target]
        assert native.name_pins == [tmp_path, target]
    assert native.active == []
    assert native.closed == [target, *target.parents]


@pytest.mark.parametrize("failure", ["reparse", "sharing", "redirect", "dispatch"])
def test_failure_closes_handles_and_denies_dispatch(tmp_path, failure):
    target = tmp_path / "file.txt"
    target.touch()
    native = FakeHandles(
        target,
        bad=tmp_path if failure == "reparse" else None,
        failure=target if failure == "sharing" else None,
    )
    if failure == "redirect":
        native.inspect = lambda handle: (Path("/outside"), 0x10)
    with pytest.raises((PermissionError, RuntimeError)):
        with pinned_file(PathPolicy([tmp_path]), target, handles=native):
            assert failure == "dispatch"
            raise RuntimeError("dispatch failed")
    assert not native.active


@pytest.mark.skipif(os.name != "nt", reason="Requires real Windows file handles")
def test_native_handles_block_rename_and_release(tmp_path):
    target = tmp_path / "file.txt"
    target.touch()
    with pinned_file(PathPolicy([tmp_path]), target):
        with pytest.raises(OSError):
            target.rename(tmp_path / "renamed.txt")
        with pytest.raises(OSError):
            target.open("wb")
    target.rename(tmp_path / "renamed.txt")
