from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request
from pydantic import BaseModel, ConfigDict

from agent.schemas import ToolCall, ToolResult
from services.file_models import (
    FileActionResponse,
    IndexedFile,
    IndexStats,
    SearchFilters,
    SearchResponse,
)
from permissions.session import require_desktop_session

TRUSTED_ORIGINS = frozenset(
    {
        "http://localhost:1420",
        "http://127.0.0.1:1420",
        "http://tauri.localhost",
        "https://tauri.localhost",
        "tauri://localhost",
    }
)


def require_file_client(request: Request) -> None:
    require_desktop_session(request)
    # Custom header forces browser preflight; CORS alone does not stop side effects.
    if request.headers.get("X-Nova-Request") != "1":
        raise HTTPException(403, "Nova request header is required.")
    origin = request.headers.get("origin")
    if origin is not None and origin not in TRUSTED_ORIGINS:
        raise HTTPException(403, "Request origin is not allowed.")
    if request.headers.get("sec-fetch-site") == "cross-site" and origin is None:
        raise HTTPException(403, "Cross-site requests are not allowed.")


router = APIRouter(
    prefix="/files", tags=["files"], dependencies=[Depends(require_file_client)]
)


class IndexRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


def dispatch(
    request: Request, tool: str, arguments: dict[str, Any], *, interactive: bool = False
) -> dict[str, Any]:
    result = request.app.state.permissions.dispatch(
        ToolCall(tool=tool, arguments=arguments),
        user_initiated=interactive,
    )
    if not isinstance(result, ToolResult) or result.status != "completed":
        raise HTTPException(
            400, getattr(result, "message", None) or "Action requires confirmation."
        )
    return result.data


@router.get("/search", response_model=SearchResponse)
def search(
    request: Request, filters: Annotated[SearchFilters, Query()]
) -> dict[str, Any]:
    return dispatch(request, "search_files", filters.model_dump(mode="json"))


@router.post("/index", response_model=IndexStats)
def index(
    request: Request, body: Annotated[IndexRequest | None, Body()] = None
) -> IndexStats:
    result = request.app.state.indexing.refresh()
    if result.roots_failed and not result.roots_indexed:
        raise HTTPException(
            503,
            {
                "message": "No configured directory could be indexed.",
                "statistics": result.model_dump(),
            },
        )
    return result


@router.get("/{file_id}", response_model=IndexedFile)
def info(request: Request, file_id: Annotated[int, Path(gt=0)]) -> dict[str, Any]:
    return dispatch(request, "get_file_info", {"file_id": file_id})


@router.post("/{file_id}/open", response_model=FileActionResponse)
def open_file(request: Request, file_id: Annotated[int, Path(gt=0)]) -> dict[str, Any]:
    return dispatch(request, "open_file", {"file_id": file_id}, interactive=True)


@router.post("/{file_id}/reveal", response_model=FileActionResponse)
def reveal(request: Request, file_id: Annotated[int, Path(gt=0)]) -> dict[str, Any]:
    return dispatch(request, "show_in_folder", {"file_id": file_id}, interactive=True)
