"""Typed configuration via pydantic-settings.

Single source of truth for runtime settings. Reads from environment
variables and an optional .env file.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "geospatial-risk-mapper"
    log_level: str = "INFO"
    data_dir: str = "./data"
    models_dir: str = "./models"
    region: str = "Italy"  # Geographic region
    target_crs: str = "EPSG:4326"  # WGS84
    random_state: int = 42


settings = Settings()
