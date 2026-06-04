from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="SMISTRESS_", extra="ignore"
    )

    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "not-needed"
    chat_model: str = "llama3.1"
    vision_model: str | None = None
    database_url: str = "postgresql+psycopg://smistress:smistress@localhost:5432/smistress"
    falkordb_url: str = "redis://localhost:6379"

    @property
    def vision_enabled(self) -> bool:
        return self.vision_model is not None
