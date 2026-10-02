import os
import sqlite3
from pathlib import Path

import pytest

from services.file_models import SearchFilters


def test_recursive_metadata_without_content_reads(file_stack, monkeypatch):
    root, _, repository, indexer, _ = file_stack
    (root / "nested").mkdir()
    file = root / "nested" / "Resume.PDF"
    file.write_bytes(b"private content")
    with monkeypatch.context() as patch:
        patch.setattr(
            Path, "open", lambda *a, **k: pytest.fail("Indexer opened contents")
        )
        patch.setattr(
            "builtins.open", lambda *a, **k: pytest.fail("Indexer opened contents")
        )
        result = indexer.index(root)
    assert result.indexed == result.created == 1
    row = repository.get_file_by_path(str(file))
    assert row.name == "Resume.PDF"
    assert row.extension == ".pdf"
    assert row.size == 15
    assert row.modified_at.tzinfo is not None


def test_refresh_add_update_remove_and_stable_ids(file_stack):
    root, _, repository, indexer, search = file_stack
    first = root / "resume.pdf"
    deleted = root / "invoice.pdf"
    first.touch()
    deleted.touch()
    assert indexer.index(root).created == 2
    first_id = repository.get_file_by_path(str(first)).id
    assert indexer.index(root).unchanged == 2
    first.write_text("changed")
    deleted.unlink()
    (root / "report.pdf").touch()
    result = indexer.index(root)
    assert (result.created, result.updated, result.removed, result.indexed) == (
        1,
        1,
        1,
        2,
    )
    assert repository.get_file_by_path(str(first)).id == first_id
    assert {file.name for file in search.search(SearchFilters()).results} == {
        "resume.pdf",
        "report.pdf",
    }


def test_empty_root_and_deleted_ids_not_reused(file_stack):
    root, _, repository, indexer, _ = file_stack
    assert indexer.index(root).indexed == 0
    old = root / "old.txt"
    old.touch()
    indexer.index(root)
    old_id = repository.get_file_by_path(str(old)).id
    old.unlink()
    assert indexer.index(root).removed == 1
    (root / "new.txt").touch()
    indexer.index(root)
    assert repository.get_file_by_path(str(root / "new.txt")).id > old_id


def test_failed_subtree_preserves_metadata(file_stack, monkeypatch):
    root, _, repository, indexer, _ = file_stack
    blocked = root / "blocked"
    blocked.mkdir()
    (blocked / "keep.txt").touch()
    indexer.index(root)
    original = os.scandir

    def scandir(path):
        if Path(path) == blocked:
            raise PermissionError("inaccessible")
        return original(path)

    monkeypatch.setattr(os, "scandir", scandir)
    (root / "new.txt").touch()
    result = indexer.index(root)
    assert result.skipped == 1
    assert result.created == 1
    assert result.removed == 0
    assert repository.get_file_by_path(str(blocked / "keep.txt")) is not None


def test_failed_stat_preserves_entry(file_stack, monkeypatch):
    root, _, repository, indexer, _ = file_stack
    file = root / "keep.txt"
    file.touch()
    indexer.index(root)
    original = Path.lstat

    def lstat(path):
        if path == file:
            raise PermissionError("unreadable")
        return original(path)

    monkeypatch.setattr(Path, "lstat", lstat)
    result = indexer.index(root)
    assert result.skipped == 1
    assert result.removed == 0
    assert repository.get_file_by_path(str(file)) is not None


def test_symlinks_skipped_including_loops(file_stack, tmp_path):
    root, _, _, indexer, search = file_stack
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").touch()
    try:
        (root / "escape").symlink_to(outside, target_is_directory=True)
        (root / "loop").symlink_to(root, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink privileges unavailable")
    result = indexer.index(root)
    assert result.skipped == 2
    assert search.search(SearchFilters()).total == 0


def test_outside_and_system_directory_rejected(file_stack, tmp_path):
    root, _, _, indexer, _ = file_stack
    with pytest.raises(PermissionError):
        indexer.index(tmp_path)
    (root / "Windows").mkdir()
    (root / "Windows" / "system.txt").touch()
    assert indexer.index(root).skipped == 1


def test_database_failure_rolls_back_refresh(file_stack):
    root, database, repository, indexer, _ = file_stack
    original = root / "original.txt"
    original.touch()
    indexer.index(root)
    original.unlink()
    (root / "new.txt").touch()
    with database.connect() as connection:
        connection.execute(
            "CREATE TRIGGER fail_insert BEFORE INSERT ON files BEGIN SELECT RAISE(ABORT, 'test'); END"
        )
    with pytest.raises(sqlite3.DatabaseError):
        indexer.index(root)
    assert repository.get_file_by_path(str(original)) is not None
