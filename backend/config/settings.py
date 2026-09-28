from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    nova_env: str = "development"
    nova_database_path: Path = ROOT / "data" / "nova.db"
    openai_api_key: SecretStr = SecretStr("")
    # JSON array of absolute paths. Empty means no filesystem access.
    nova_allowed_directories: list[Path] = []

    @property
    def database_path(self) -> Path:
        path = self.nova_database_path
        return path if path.is_absolute() else ROOT / path
