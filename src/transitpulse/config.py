"""Settings read from the environment (prefix ``TP_``) or a local ``.env``."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from transitpulse.lake import Lake, make_lake


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TP_", env_file=".env", extra="ignore")

    lake_backend: Literal["local", "azure"] = "local"
    data_dir: Path = Path("./data")  # root of the local lake (raw/ and state/ live inside)
    adls_account_url: str = ""  # https://<account>.blob.core.windows.net
    lake_container: str = "lake"
    user_agent: str = "transitpulse-de/0.1 (portfolio project; https://github.com/Parsaka)"
    log_format: Literal["json", "text"] = "text"
    alert_webhook: str = ""
    http_timeout_s: float = 20.0
    # {"vbb": "http://host/vbb_sample.pb"}: replay a saved feed or point a smoke test at a fixture
    feed_urls: dict[str, str] = {}
    http_retries: int = 3
    # Databricks Volume as a second sink (Free Edition cannot read the Azure lake). Empty = off.
    databricks_host: str = ""  # https://dbc-....cloud.databricks.com
    databricks_token: str = ""  # personal access token, from Key Vault in the Function
    volume_path: str = "/Volumes/workspace/tp_landing/raw"
    weather_past_days: int = 2
    weather_forecast_days: int = 2

    def lake(self) -> Lake:
        primary = make_lake(
            self.lake_backend,
            data_dir=self.data_dir,
            account_url=self.adls_account_url,
            container=self.lake_container,
        )
        if self.databricks_host and self.databricks_token and self.databricks_token != "none":
            from transitpulse.volume import MultiLake, VolumeLake

            return MultiLake(
                primary, VolumeLake(self.databricks_host, self.databricks_token, self.volume_path)
            )
        return primary


def get_settings() -> Settings:
    return Settings()
