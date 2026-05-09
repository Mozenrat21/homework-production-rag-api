from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI as OpenAIAsyncOpenAI

from app.core.settings import settings
from app.services.observability import setup_langfuse_env

try:
    from langfuse.openai import AsyncOpenAI as LangfuseAsyncOpenAI
except Exception:
    LangfuseAsyncOpenAI = None


SYSTEM_PROMPT = """
You are a RAG assistant for a homework document.

Rules:
- Answer only using the provided context.
- If the context is not enough, say that the document does not contain enough information.
- Be concise and practical.
- Answer in the same language as the user's question.
- Do not invent facts outside the context.
""".strip()


def get_model_chain() -> list[str]:
    """
    Повертає fallback chain для OpenRouter.

    Поточна стратегія:
    1. openrouter/free
    2. meta-llama/...:free
    3. openai/gpt-4o-mini
    """
    return [
        settings.openrouter_model_primary,
        settings.openrouter_model_fallback_1,
        settings.openrouter_model_fallback_2,
    ]


def get_openrouter_client() -> OpenAIAsyncOpenAI:
    """
    Повертає OpenRouter client.

    Якщо Langfuse налаштований:
    - використовуємо Langfuse OpenAI wrapper;
    - LLM calls автоматично потрапляють у Langfuse.

    Якщо ні:
    - використовуємо звичайний OpenAI AsyncOpenAI;
    - API продовжує працювати.
    """
    if not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set in .env")

    langfuse_ready = setup_langfuse_env()

    client_class: Any = OpenAIAsyncOpenAI

    if langfuse_ready and LangfuseAsyncOpenAI is not None:
        client_class = LangfuseAsyncOpenAI

    return client_class(
        base_url=settings.openrouter_base_url,
        api_key=settings.openrouter_api_key,
        default_headers={
            "HTTP-Referer": settings.openrouter_site_url,
            "X-OpenRouter-Title": settings.openrouter_app_title,
        },
    )


def build_context(chunks: list[dict]) -> str:
    """
    Готуємо RAG context з top-k chunks.
    """
    context_parts = []

    for index, chunk in enumerate(chunks, start=1):
        chunk_id = chunk.get("chunk_id")
        text = chunk.get("text") or ""

        context_parts.append(
            f"[Source {index}: {chunk_id}]\n{text}"
        )

    return "\n\n---\n\n".join(context_parts)


def build_messages(user_message: str, chunks: list[dict]) -> list[dict]:
    """
    Формуємо prompt:
    system правила → context → питання користувача.
    """
    context = build_context(chunks)

    return [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": (
                "Context:\n"
                f"{context}\n\n"
                "Question:\n"
                f"{user_message}"
            ),
        },
    ]


async def stream_single_model(
    client: OpenAIAsyncOpenAI,
    model: str,
    user_message: str,
    chunks: list[dict],
) -> AsyncIterator[str]:
    """
    Стрімить відповідь однієї конкретної моделі.

    Тут НЕ передаємо extra_body={"models": ...},
    бо fallback контролюємо вручну.
    """
    create_kwargs = {
        "model": model,
        "messages": build_messages(
            user_message=user_message,
            chunks=chunks,
        ),
        "temperature": 0.1,
        "max_tokens": 700,
        "stream": True,
    }

    if settings.langfuse_enabled:
        create_kwargs["name"] = "rag-chat-completion"
        create_kwargs["metadata"] = {
            "app": "lesson-10-production-rag-api",
            "model_chain": get_model_chain(),
            "top_k": 3,
            "source_chunk_ids": [
                chunk.get("chunk_id")
                for chunk in chunks
            ],
        }

    stream = await client.chat.completions.create(**create_kwargs)

    async for chunk in stream:
        if not chunk.choices:
            continue

        delta = chunk.choices[0].delta

        if delta and delta.content:
            yield delta.content


async def stream_llm_events(
    user_message: str,
    chunks: list[dict],
) -> AsyncIterator[dict]:
    """
    Ручний fallback для LLM.

    Логіка:
    1. Пробуємо першу модель.
    2. Якщо модель впала або повернула 0 токенів — пробуємо наступну.
    3. Якщо модель дала хоча б 1 токен — вважаємо її успішною.
    4. Якщо всі моделі впали — кидаємо помилку.

    Повертає події:
    - {"type": "model_attempt", "model": "..."}
    - {"type": "model_failed", "model": "...", "reason": "..."}
    - {"type": "model", "model": "..."}
    - {"type": "token", "text": "..."}
    """
    client = get_openrouter_client()
    models = get_model_chain()

    last_error: Exception | None = None

    for model in models:
        token_count = 0
        model_selected_sent = False

        yield {
            "type": "model_attempt",
            "model": model,
        }

        try:
            async for token in stream_single_model(
                client=client,
                model=model,
                user_message=user_message,
                chunks=chunks,
            ):
                if not token:
                    continue

                token_count += 1

                if not model_selected_sent:
                    model_selected_sent = True

                    yield {
                        "type": "model",
                        "model": model,
                    }

                yield {
                    "type": "token",
                    "text": token,
                }

            if token_count > 0:
                return

            last_error = RuntimeError(
                f"Model {model} returned zero tokens"
            )

            yield {
                "type": "model_failed",
                "model": model,
                "reason": "zero_tokens",
            }

        except Exception as error:
            last_error = error

            if token_count == 0:
                yield {
                    "type": "model_failed",
                    "model": model,
                    "reason": str(error),
                }

                continue

            raise RuntimeError(
                f"Model {model} failed after streaming started: {error}"
            ) from error

    raise RuntimeError(
        f"All models failed. Last error: {last_error}"
    )