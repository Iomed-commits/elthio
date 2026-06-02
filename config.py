import os
from pydantic import BaseModel, Field


class BrowserSettings(BaseModel):
    """Configuration for Playwright browser (viewport, timeout, headless)."""

    browser_type: str = Field(default="chromium")
    headless: bool = Field(default=True)
    viewport_width: int = Field(default=1280)
    viewport_height: int = Field(default=720)
    page_timeout_ms: int = Field(default=30000)


class AppConfig(BaseModel):
    """Top-level application configuration."""

    openai_api_key: str = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    model_name: str = Field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))

    browser: BrowserSettings = Field(default_factory=BrowserSettings)


def get_config() -> AppConfig:
    """
    Load configuration from environment variables.

    This keeps all config in one place and makes it easy
    to extend in the future (e.g. NIH DSLD endpoints).
    """

    cfg = AppConfig()

    if not cfg.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Please set it in your environment before running the app."
        )

    return cfg

