from abc import ABC, abstractmethod

from pydantic import BaseModel


class Transcription(BaseModel):
    text: str
    language: str | None = None


class SpeechToTextProvider(ABC):
    @abstractmethod
    async def transcribe(self, audio: bytes, media_type: str) -> Transcription:
        raise NotImplementedError
