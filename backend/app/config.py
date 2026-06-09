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
    test_database_url: str = "postgresql+psycopg://smistress:smistress@localhost:5432/smistress_test"
    falkordb_url: str = "redis://localhost:6379"
    graphiti_enabled: bool = False  # off -> NullMemoryStore; no FalkorDB/LLM needed
    heartbeat_ttl_seconds: int = 90  # online iff last heartbeat is fresher than this
    batch_task_target: int = 8  # top the task pool up to this many unconsumed items
    batch_task_low: int = 2  # at/below this, the reminder unit asks for a batch window
    batch_line_target: int = 24  # top the drone line bank up to this many lines
    batch_line_low: int = 6
    embedding_model: str = "nomic-embed-text"  # local default (Ollama); OpenAI: text-embedding-3-small
    embedding_dim: int = 768  # nomic-embed-text dim; text-embedding-3-small = 1536
    falkordb_host: str = "localhost"
    falkordb_port: int = 6379

    @property
    def vision_enabled(self) -> bool:
        return self.vision_model is not None
