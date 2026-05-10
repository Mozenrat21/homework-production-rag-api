from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_api_key: str = ""

    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_chunks_collection: str = "rag_chunks"
    qdrant_cache_collection: str = "rag_cache"

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    openrouter_model_primary: str = "openrouter/free"
    openrouter_model_fallback_1: str = "meta-llama/llama-3.2-3b-instruct:free"
    openrouter_model_fallback_2: str = "openai/gpt-4o-mini"

    openrouter_site_url: str = "http://localhost:8000"
    openrouter_app_title: str = "Lesson 10 Production RAG API"

    embedding_provider: str = "local"
    local_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    remote_embedding_model: str = "openai/text-embedding-3-small"
    embedding_dimensions: int = 384

    sqlite_db_path: str = "./data/usage.db"

    semantic_cache_threshold: float = 0.92

    redis_url: str = ""
    rate_limit_requests_per_minute: int = 3
    rate_limit_window_seconds: int = 60

    max_concurrent_streams: int = 3
    index_rebuild_timeout_seconds: int = 180

    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_base_url: str = "https://cloud.langfuse.com"
    langfuse_tracing_environment: str = "local"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()