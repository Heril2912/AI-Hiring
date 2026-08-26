from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_PATH = REPO_ROOT / ".env"


class Settings(BaseSettings):
    database_url: str
    max_resume_upload_bytes: int = 10485760
    resume_intake_directory: str = "backend/runtime/resume_intake"

    model_config = SettingsConfigDict(
        env_file=ENV_PATH,
        extra="ignore",
    )

    def get_intake_path(self) -> Path:
        raw_path = Path(self.resume_intake_directory)
        if raw_path.is_absolute():
            return raw_path.resolve()
        return (REPO_ROOT / raw_path).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
