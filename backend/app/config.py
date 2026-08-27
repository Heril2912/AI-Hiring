from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_PATH = REPO_ROOT / ".env"


class Settings(BaseSettings):
    database_url: str
    max_resume_upload_bytes: int = 10485760
    max_resume_pages: int = 5
    max_docx_expanded_bytes: int = 52428800
    max_docx_archive_entries: int = 1000
    max_docx_compression_ratio: int = 100
    resume_intake_directory: str = "backend/runtime/resume_intake"
    resume_quarantine_directory: str = "backend/runtime/quarantine"
    min_pdf_direct_text_chars: int = 30
    max_pdf_extracted_chars: int = 500000
    max_docx_extracted_chars: int = 500000

    model_config = SettingsConfigDict(
        env_file=ENV_PATH,
        extra="ignore",
    )

    def get_intake_path(self) -> Path:
        raw_path = Path(self.resume_intake_directory)
        if raw_path.is_absolute():
            return raw_path.resolve()
        return (REPO_ROOT / raw_path).resolve()

    def get_quarantine_path(self) -> Path:
        raw_path = Path(self.resume_quarantine_directory)
        if raw_path.is_absolute():
            return raw_path.resolve()
        return (REPO_ROOT / raw_path).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
