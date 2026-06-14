from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str = ""
    clearbit_api_key: str = ""

    host: str = "0.0.0.0"
    port: int = 8009
    debug: bool = False

    max_html_size_bytes: int = 5 * 1024 * 1024
    max_screenshot_size_bytes: int = 10 * 1024 * 1024
    max_csv_size_bytes: int = 200 * 1024 * 1024
    max_input_zip_size_bytes: int = 2 * 1024 * 1024 * 1024
    max_techniques_per_request: int = 25

    screenshot_enabled: bool = True
    screenshot_timeout_ms: int = 15000
    screenshot_viewport_width: int = 1366
    screenshot_viewport_height: int = 768
    screenshot_browser_recycle_after: int = 100

    data_dir: str = "/data"
    bulk_default_concurrency: int = 8
    bulk_max_concurrency: int = 32
    crawl_default_concurrency: int = 8
    crawl_max_concurrency: int = 32
    crawl_unreachable_timeout_s: float = 10.0
    crawl_partial_timeout_s: float = 25.0
    bulk_max_entries: int = 12000
    bulk_entry_timeout_s: float = 120.0
    bulk_max_zip_uncompressed_bytes: int = 10 * 1024 * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_settings_sync() -> Settings:
    """Non-cached version for use inside technique apply() calls."""
    return Settings()
