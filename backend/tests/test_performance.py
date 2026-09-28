from time import perf_counter

import pytest

from services.file_models import SearchFilters


@pytest.mark.performance
def test_5000_file_refresh(file_stack):
    root, _, repository, indexer, search = file_stack
    for directory in range(50):
        folder = root / str(directory)
        folder.mkdir()
        for number in range(100):
            (folder / f"sample-{number}.txt").touch()
    started = perf_counter()
    first = indexer.index(root)
    second = indexer.index(root)
    results = search.search(SearchFilters(q="sample", limit=200))
    elapsed = perf_counter() - started
    assert first.created == 5000
    assert second.unchanged == 5000
    assert second.created == second.removed == 0
    assert results.total == 5000
    assert len(results.results) == 200
    print(f"5000 files: first={first.duration_ms}ms refresh={second.duration_ms}ms total+search={elapsed:.3f}s")
