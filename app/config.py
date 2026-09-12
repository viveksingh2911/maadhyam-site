"""Application configuration, loaded from environment / .env file."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent

load_dotenv(PROJECT_DIR / ".env")


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    """Runtime settings. Values that editors change live in the Setting table."""

    APP_NAME: str = os.getenv("APP_NAME", "Maadhyam International")
    ENV: str = os.getenv("ENV", "development")
    DEBUG: bool = _bool("DEBUG", True)

    # Absolute origin used for canonical URLs, sitemaps and OG tags.
    SITE_URL: str = os.getenv("SITE_URL", "http://127.0.0.1:8000").rstrip("/")

    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", f"sqlite:///{(PROJECT_DIR / 'data' / 'site.db').as_posix()}"
    )

    SECRET_KEY: str = os.getenv("SECRET_KEY") or secrets.token_urlsafe(48)
    SESSION_COOKIE: str = "mi_session"
    SESSION_MAX_AGE: int = int(os.getenv("SESSION_MAX_AGE", 60 * 60 * 12))
    COOKIE_SECURE: bool = _bool("COOKIE_SECURE", False)

    UPLOAD_DIR: Path = BASE_DIR / "static" / "uploads"
    MAX_UPLOAD_BYTES: int = int(os.getenv("MAX_UPLOAD_MB", "12")) * 1024 * 1024
    ALLOWED_UPLOAD_EXT: set[str] = {
        ".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".avif",
        ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx",
    }
    IMAGE_EXT: set[str] = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".avif"}

    ITEMS_PER_PAGE: int = 9

    # First-run bootstrap account. The password has no default on purpose: a
    # built-in one ships a publicly known credential. Unset, development
    # generates a random password and prints it once; production refuses to
    # start. See bootstrap() in main.py.
    BOOTSTRAP_ADMIN_EMAIL: str = os.getenv("BOOTSTRAP_ADMIN_EMAIL", "admin@maadhyam.local")
    BOOTSTRAP_ADMIN_PASSWORD: str = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
    BOOTSTRAP_ADMIN_NAME: str = os.getenv("BOOTSTRAP_ADMIN_NAME", "Site Administrator")

    @property
    def IS_PRODUCTION(self) -> bool:
        return self.ENV.strip().lower() in {"production", "prod", "live"}


settings = Settings()
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
(PROJECT_DIR / "data").mkdir(parents=True, exist_ok=True)
