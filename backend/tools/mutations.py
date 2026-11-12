"""Write proposals only; execution is available solely through PermissionManager."""

from typing import Annotated, Any
from pydantic import BaseModel, ConfigDict, Field, AfterValidator
from permissions.policies import RiskLevel
from services.file_mutations import component
from tools.base import Tool

Name = Annotated[str, Field(min_length=1, max_length=120), AfterValidator(component)]
DirectoryId = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]


class WriteInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CreateFolderInput(WriteInput):
    parent_directory_id: DirectoryId
    folder_name: Name


class RenameFileInput(WriteInput):
    file_id: int = Field(gt=0, le=2**63 - 1)
    new_name: Name


class MoveFileInput(WriteInput):
    file_id: int = Field(gt=0, le=2**63 - 1)
    destination_directory_id: DirectoryId


class CreateFolderTool(Tool[WriteInput]):
    name = "create_folder"
    description = "Propose creating one folder using a backend-issued directory ID. Requires explicit confirmation."
    risk = RiskLevel.WRITE
    input_schema = CreateFolderInput

    def execute(self, arguments: WriteInput) -> dict[str, Any]:
        raise PermissionError(
            "Write execution requires a stored, explicitly confirmed action."
        )


class RenameFileTool(CreateFolderTool):
    name = "rename_file"
    description = "Propose renaming one indexed file to a single filename. Never overwrites; requires confirmation."
    input_schema = RenameFileInput


class MoveFileTool(CreateFolderTool):
    name = "move_file"
    description = "Propose moving one indexed file into a backend-issued directory ID. Never overwrites; requires confirmation."
    input_schema = MoveFileInput


WRITE_TOOLS = {"create_folder", "rename_file", "move_file"}
