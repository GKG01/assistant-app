from pathlib import Path

from database.repositories.files import FileRepository
from permissions.paths import PathPolicy
from services.file_models import IndexedFile, SearchFilters, SearchResponse


class FileSearchService:
    def __init__(self, repository: FileRepository, policy: PathPolicy) -> None:
        self.repository = repository
        self.policy = policy

    def search(self, filters: SearchFilters) -> SearchResponse:
        directory = (
            str(self.policy.validate(Path(filters.directory)))
            if filters.directory
            else None
        )
        return self.repository.search_files(filters, self.policy.permits, directory)

    def get_file_info(self, file_id: int) -> IndexedFile:
        file = self.repository.get_file_by_id(file_id)
        if file is None:
            raise FileNotFoundError("Indexed file was not found.")
        safe = self.policy.validate(Path(file.path), must_exist=True)
        if not safe.is_file():
            raise FileNotFoundError("Indexed file is no longer a regular file.")
        return file
