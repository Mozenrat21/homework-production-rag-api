import os

from app.core.settings import settings


def setup_langfuse_env() -> bool:
    """
    Налаштовує Langfuse env-змінні для SDK.

    Якщо Langfuse вимкнений або ключів немає —
    повертаємо False, але API не падає.
    """
    if not settings.langfuse_enabled:
        return False

    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return False

    os.environ["LANGFUSE_PUBLIC_KEY"] = settings.langfuse_public_key
    os.environ["LANGFUSE_SECRET_KEY"] = settings.langfuse_secret_key
    os.environ["LANGFUSE_BASE_URL"] = settings.langfuse_base_url
    os.environ["LANGFUSE_TRACING_ENVIRONMENT"] = settings.langfuse_tracing_environment

    return True


def flush_langfuse() -> None:
    """
    Примусово відправляє накопичені traces перед shutdown.

    Якщо Langfuse не встановлений або не налаштований —
    просто мовчки пропускаємо.
    """
    try:
        from langfuse import get_client

        langfuse = get_client()
        langfuse.flush()
    except Exception:
        pass