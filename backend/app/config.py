from functools import lru_cache
from pathlib import Path
from pydantic import field_validator, model_validator
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
    # Authentication and Session Configuration
    session_cookie_name: str = "ai_hiring_session"
    session_cookie_secure: bool = False
    session_cookie_samesite: str = "lax"
    session_idle_lifetime_seconds: int = 1800
    session_absolute_lifetime_seconds: int = 43200
    login_failure_threshold: int = 5
    login_cooldown_seconds: int = 900
    frontend_origin: str = "http://localhost:5173"
    scrypt_n: int = 16384
    scrypt_r: int = 8
    scrypt_p: int = 1
    scrypt_dklen: int = 32

    model_config = SettingsConfigDict(
        env_file=ENV_PATH,
        extra="ignore",
    )

    @field_validator("frontend_origin")
    @classmethod
    def validate_frontend_origin(cls, v: str) -> str:
        origin = v.strip()
        if not origin:
            raise ValueError("frontend_origin cannot be empty.")
        if origin == "*":
            raise ValueError("Wildcard frontend_origin ('*') is not allowed when credentials/sessions are enabled.")
        return origin

    @field_validator("session_cookie_samesite")
    @classmethod
    def validate_samesite(cls, v: str) -> str:
        val = v.strip().lower()
        if val not in {"lax", "strict", "none"}:
            raise ValueError("session_cookie_samesite must be one of 'lax', 'strict', or 'none'.")
        return val

    @field_validator(
        "session_idle_lifetime_seconds",
        "session_absolute_lifetime_seconds",
        "login_failure_threshold",
        "login_cooldown_seconds",
        "scrypt_n",
        "scrypt_r",
        "scrypt_p",
        "scrypt_dklen",
    )
    @classmethod
    def validate_positive_ints(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Configuration values must be positive integers.")
        return v

    @model_validator(mode="after")
    def validate_session_expiry_lifetimes(self) -> "Settings":
        if self.session_idle_lifetime_seconds > self.session_absolute_lifetime_seconds:
            raise ValueError("session_idle_lifetime_seconds cannot exceed session_absolute_lifetime_seconds.")
        return self

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
