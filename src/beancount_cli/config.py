from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CliConfig(BaseSettings):
    beancount_file: Path | None = Field(
        default=None, alias="file", validation_alias="BEANCOUNT_FILE"
    )
    beancount_path: Path | None = Field(default=None, validation_alias="BEANCOUNT_PATH")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def get_resolved_ledger(self, override: Path | None = None) -> Path | None:
        if override:
            return override
        if self.beancount_file:
            return self.beancount_file
        if self.beancount_path:
            p = self.beancount_path / "main.beancount"
            if p.exists():
                return p

        p = Path("main.beancount")
        if p.exists():
            return p

        return None  # Let the calling code handle missing path
