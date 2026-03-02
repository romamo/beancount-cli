from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CliConfig(BaseSettings):
    file: Path | None = Field(default=None, validation_alias="BEANCOUNT_FILE")
    path: Path | None = Field(default=None, validation_alias="BEANCOUNT_PATH")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def get_resolved_ledger(self, override: Path | None = None) -> Path | None:
        if override:
            return override
        if self.file:
            return self.file
        if self.path:
            p = self.path / "main.beancount"
            if p.exists():
                return p

        p = Path("main.beancount")
        if p.exists():
            return p

        return None  # Let the calling code handle missing path
