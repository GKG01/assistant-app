from datetime import datetime, timezone
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator


class FileMetadata(BaseModel):
    name: str
    extension: str
    path: str
    size: int
    created_at: datetime
    modified_at: datetime
    indexed_at: datetime

    @field_serializer("created_at", "modified_at", "indexed_at")
    def serialize_date(self, value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


class IndexedFile(FileMetadata):
    id: int


class SearchFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    q: str = Field(default="", max_length=500)
    extension: str | None = Field(default=None, max_length=30)
    directory: str | None = Field(default=None, max_length=4096)
    modified_after: datetime | None = None
    modified_before: datetime | None = None
    min_size: int | None = Field(default=None, ge=0, le=2**63 - 1)
    max_size: int | None = Field(default=None, ge=0, le=2**63 - 1)
    sort: Literal["name_asc", "name_desc", "modified_asc", "modified_desc",
                  "size_asc", "size_desc"] = "modified_desc"
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0, le=1_000_000)

    @field_validator("extension")
    @classmethod
    def normalize_extension(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip().casefold().lstrip(".")
        if not value.isalnum():
            raise ValueError("Extension must contain only letters and numbers.")
        return "." + value

    @field_validator("modified_after", "modified_before")
    @classmethod
    def normalize_date(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def ordered_ranges(self) -> Self:
        if self.min_size is not None and self.max_size is not None and self.min_size > self.max_size:
            raise ValueError("min_size must not exceed max_size.")
        if self.modified_after and self.modified_before and self.modified_after > self.modified_before:
            raise ValueError("modified_after must not exceed modified_before.")
        return self


class SearchResponse(BaseModel):
    results: list[IndexedFile]
    total: int
    limit: int
    offset: int


class IndexStats(BaseModel):
    indexed: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0
    skipped: int = 0
    duration_ms: int = 0
    roots_indexed: int = 0
    roots_failed: int = 0
    warnings: list[str] = Field(default_factory=list)


class FileIdInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_id: int = Field(gt=0)


class FileActionResponse(BaseModel):
    status: Literal["requested"] = "requested"
    file_id: int
    action: Literal["open_file", "show_in_folder"]
