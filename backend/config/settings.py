from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    nova_env: str = "development"
    nova_database_path: Path = ROOT / "data" / "nova.db"
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = Field(
        default="gpt-4.1-mini", min_length=1, max_length=200, pattern=r"^\S+$"
    )
    openai_timeout_seconds: float = Field(default=30, gt=0, le=120)
    openai_max_output_tokens: int = Field(default=1024, ge=16, le=16384)
    # JSON array of absolute paths. Empty means no filesystem access.
    nova_allowed_directories: list[Path] = []

    @property
    def database_path(self) -> Path:
        path = self.nova_database_path
        return path if path.is_absolute() else ROOT / path
