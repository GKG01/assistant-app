from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/transcribe")
def transcribe() -> None:
    raise HTTPException(501, "Speech transcription is not implemented.")
