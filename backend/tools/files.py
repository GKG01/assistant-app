from typing import Any

from permissions.policies import RiskLevel
from services.file_actions import FileActionService
from services.file_models import FileIdInput, SearchFilters
from services.file_search import FileSearchService
from tools.base import Tool


class SearchFilesTool(Tool[SearchFilters]):
    name = "search_files"
    description = "Search allowed indexed filenames and metadata, without scanning files."
    risk = RiskLevel.READ
    input_schema = SearchFilters

    def __init__(self, service: FileSearchService) -> None:
        self.service = service

    def execute(self, arguments: SearchFilters) -> dict[str, Any]:
        return self.service.search(arguments).model_dump(mode="json")


class GetFileInfoTool(Tool[FileIdInput]):
    name = "get_file_info"
    description = "Return indexed metadata for an allowed, existing file ID."
    risk = RiskLevel.READ
    input_schema = FileIdInput

    def __init__(self, service: FileSearchService) -> None:
        self.service = service

    def execute(self, arguments: FileIdInput) -> dict[str, Any]:
        return self.service.get_file_info(arguments.file_id).model_dump(mode="json")


class OpenFileTool(Tool[FileIdInput]):
    name = "open_file"
    description = "Open a supported indexed document via an explicit user action."
    risk = RiskLevel.INTERACTIVE
    input_schema = FileIdInput

    def __init__(self, service: FileActionService) -> None:
        self.service = service

    def execute(self, arguments: FileIdInput) -> dict[str, Any]:
        return self.service.perform(arguments.file_id, "open_file").model_dump(mode="json")


class ShowInFolderTool(OpenFileTool):
    name = "show_in_folder"
    description = "Reveal an indexed file in Explorer via an explicit user action."

    def execute(self, arguments: FileIdInput) -> dict[str, Any]:
        return self.service.perform(arguments.file_id, "show_in_folder").model_dump(mode="json")
