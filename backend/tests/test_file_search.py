import os
from datetime import datetime, timezone

import pytest

from services.file_models import SearchFilters


@pytest.fixture
def populated(file_stack):
    root, _, _, indexer, search = file_stack
    for name, size, timestamp in [
        ("Resume.PDF", 10, 1700000000),
        ("résumé.docx", 20, 1700000100),
        ("photo.jpg", 30, 1700000200),
        ("other.pdf", 40, 1700000300),
    ]:
        file = root / name
        file.write_bytes(b"x" * size)
        os.utime(file, (timestamp, timestamp))
    indexer.index(root)
    return file_stack


@pytest.mark.parametrize(("filters", "names"), [
    ({"q": "RESUME"}, ["Resume.PDF"]),
    ({"q": "RÉSUMÉ"}, ["résumé.docx"]),
    ({"extension": "PDF", "sort": "name_asc"}, ["other.pdf", "Resume.PDF"]),
    ({"extension": ".pdf", "min_size": 11}, ["other.pdf"]),
    ({"min_size": 20, "max_size": 30, "sort": "size_asc"}, ["résumé.docx", "photo.jpg"]),
    ({"q": "%"}, []),
    ({"q": "' OR 1=1 --"}, []),
    ({"q": "missing"}, []),
    ({"modified_after": datetime.fromtimestamp(1700000100, timezone.utc),
      "modified_before": datetime.fromtimestamp(1700000200, timezone.utc),
      "sort": "modified_asc"}, ["résumé.docx", "photo.jpg"]),
])
def test_filters(populated, filters, names):
    response = populated[-1].search(SearchFilters(**filters))
    assert [file.name for file in response.results] == names
    assert response.total == len(names)


@pytest.mark.parametrize(("sort", "expected"), [
    ("name_asc", ["other.pdf", "photo.jpg", "Resume.PDF", "résumé.docx"]),
    ("name_desc", ["résumé.docx", "Resume.PDF", "photo.jpg", "other.pdf"]),
    ("size_asc", ["Resume.PDF", "résumé.docx", "photo.jpg", "other.pdf"]),
    ("size_desc", ["other.pdf", "photo.jpg", "résumé.docx", "Resume.PDF"]),
    ("modified_asc", ["Resume.PDF", "résumé.docx", "photo.jpg", "other.pdf"]),
    ("modified_desc", ["other.pdf", "photo.jpg", "résumé.docx", "Resume.PDF"]),
])
def test_sorting(populated, sort, expected):
    result = populated[-1].search(SearchFilters(sort=sort))
    assert [file.name for file in result.results] == expected


def test_pagination(populated):
    response = populated[-1].search(SearchFilters(sort="size_asc", limit=2, offset=1))
    assert (response.total, response.limit, response.offset) == (4, 2, 1)
    assert [file.size for file in response.results] == [20, 30]


def test_directory_filter_and_revoked_root(populated, tmp_path):
    root, _, _, indexer, search = populated
    child = root / "child"
    child.mkdir()
    (child / "nested.txt").touch()
    indexer.index(root)
    assert search.search(SearchFilters(directory=str(child))).total == 1
    with pytest.raises(PermissionError):
        search.search(SearchFilters(directory=str(tmp_path)))
    search.policy.roots = ()
    assert search.search(SearchFilters()).total == 0


def test_replaced_directory_link_does_not_leak(populated, tmp_path):
    root, _, _, indexer, search = populated
    folder = root / "child"
    folder.mkdir()
    (folder / "secret-name.txt").touch()
    indexer.index(root)
    folder.rename(root / "old")
    try:
        folder.symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink privileges unavailable")
    assert search.search(SearchFilters(q="secret-name")).total == 0
