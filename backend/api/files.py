from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix="/files", tags=["files"])


class IndexRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    directory: str = Field(min_length=1)


@router.get("/search")
def search(q: str = Query(min_length=1, max_length=500)) -> None:
    raise HTTPException(501, "File search is not implemented.")


@router.post("/index")
def index(request: IndexRequest) -> None:
    raise HTTPException(501, "File indexing is not implemented.")
