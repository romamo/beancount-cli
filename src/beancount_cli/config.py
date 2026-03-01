from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class CliConfig(BaseSettings):
    file: Path | None = None
    path: Path | None = None

    model_config = SettingsConfigDict(env_prefix="BEANCOUNT_", env_file=".env", extra="ignore")

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
