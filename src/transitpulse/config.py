"""Settings read from the environment (prefix ``TP_``) or a local ``.env``."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TP_", env_file=".env", extra="ignore")

    data_dir: Path = Path("./data")
    state_dir: Path = Path("./state")
    user_agent: str = "transitpulse-de/0.1 (portfolio project; https://github.com/Parsaka)"
    log_format: Literal["json", "text"] = "text"
    alert_webhook: str = ""
    http_timeout_s: float = 20.0
    http_retries: int = 3


def get_settings() -> Settings:
    return Settings()
