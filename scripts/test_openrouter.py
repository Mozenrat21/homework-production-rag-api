import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from openai import AsyncOpenAI

from app.core.settings import settings


def get_model_chain() -> list[str]:
    return [
        settings.openrouter_model_primary,
        settings.openrouter_model_fallback_1,
        settings.openrouter_model_fallback_2,
    ]


def get_client() -> AsyncOpenAI:
    if not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set in .env")

    return AsyncOpenAI(
        base_url=settings.openrouter_base_url,
        api_key=settings.openrouter_api_key,
        default_headers={
            "HTTP-Referer": settings.openrouter_site_url,
            "X-OpenRouter-Title": settings.openrouter_app_title,
        },
    )


async def test_non_stream(client: AsyncOpenAI) -> None:
    print("\n=== Non-stream fallback test ===")

    models = get_model_chain()
    print(f"Fallback chain: {models}")

    response = await client.chat.completions.create(
        model=models[0],
        extra_body={
            "models": models[1:],
        },
        messages=[
            {
                "role": "user",
                "content": "Reply exactly with this sentence: OpenRouter fallback works.",
            }
        ],
        temperature=0,
        max_tokens=80,
        stream=False,
    )

    print(f"Actual response model: {response.model}")
    print(f"Choices count: {len(response.choices)}")

    if not response.choices:
        print("No choices returned")
        return

    message = response.choices[0].message
    print(f"Finish reason: {response.choices[0].finish_reason}")
    print(f"Content: {message.content!r}")


async def test_stream(client: AsyncOpenAI) -> None:
    print("\n=== Stream fallback test ===")

    models = get_model_chain()
    print(f"Fallback chain: {models}")

    stream = await client.chat.completions.create(
        model=models[0],
        extra_body={
            "models": models[1:],
        },
        messages=[
            {
                "role": "user",
                "content": "Reply exactly with this sentence: Streaming fallback works.",
            }
        ],
        temperature=0,
        max_tokens=80,
        stream=True,
    )

    received_tokens = 0

    async for chunk in stream:
        if not chunk.choices:
            continue

        delta = chunk.choices[0].delta

        if delta and delta.content:
            received_tokens += 1
            print(delta.content, end="", flush=True)

    print(f"\nStream tokens received: {received_tokens}")


async def main() -> None:
    print("Loaded OpenRouter settings:")
    print(f"OPENROUTER_BASE_URL: {settings.openrouter_base_url}")
    print(f"OPENROUTER_API_KEY exists: {bool(settings.openrouter_api_key)}")
    print(f"OPENROUTER_MODEL_PRIMARY: {settings.openrouter_model_primary}")
    print(f"OPENROUTER_MODEL_FALLBACK_1: {settings.openrouter_model_fallback_1}")
    print(f"OPENROUTER_MODEL_FALLBACK_2: {settings.openrouter_model_fallback_2}")

    client = get_client()

    await test_non_stream(client)
    await test_stream(client)

    print("\nOpenRouter fallback diagnostic completed")


if __name__ == "__main__":
    asyncio.run(main())