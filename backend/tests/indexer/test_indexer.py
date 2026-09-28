import pytest

from indexer.file_indexer import FileIndexer


def test_indexer_is_explicit_stub(tmp_path):
    with pytest.raises(NotImplementedError):
        FileIndexer([tmp_path]).index(tmp_path)


def test_indexer_denies_unconfigured_path(tmp_path):
    with pytest.raises(PermissionError):
        FileIndexer([]).index(tmp_path)
