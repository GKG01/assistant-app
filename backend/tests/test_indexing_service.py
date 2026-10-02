from indexer.file_indexer import FileIndexer
from permissions.paths import PathPolicy
from services.file_indexing import FileIndexingService
from services.file_models import SearchFilters


def test_multiple_overlapping_and_missing_roots(file_stack, tmp_path):
    root, _, repository, _, search = file_stack
    child = root / "child"
    child.mkdir()
    (child / "one.txt").touch()
    other = tmp_path / "other"
    other.mkdir()
    (other / "two.txt").touch()
    policy = PathPolicy([root, child, other, tmp_path / "missing"])
    service = FileIndexingService(FileIndexer(policy, repository))
    first = service.refresh()
    assert first.indexed == first.created == 2
    assert first.roots_indexed == 2
    assert first.roots_failed == first.skipped == 1
    assert service.refresh().unchanged == 2


def test_refresh_uses_one_database_connection(file_stack, monkeypatch):
    root, database, _, indexer, _ = file_stack
    for i in range(100):
        (root / f"{i}.txt").touch()
    original = database.connect
    count = 0

    def connect():
        nonlocal count
        count += 1
        return original()

    monkeypatch.setattr(database, "connect", connect)
    indexer.index(root)
    assert count == 1


def test_root_ownership_change_does_not_duplicate(file_stack):
    root, _, repository, _, search = file_stack
    child = root / "child"
    child.mkdir()
    (child / "one.txt").touch()
    FileIndexer(PathPolicy([child]), repository).index(child)
    result = FileIndexer(PathPolicy([root]), repository).index(root)
    assert result.unchanged == 1
    assert result.created == 0
    assert search.search(SearchFilters()).total == 1
