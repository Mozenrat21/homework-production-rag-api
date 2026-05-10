from openai import OpenAI

from app.core.settings import settings


_local_model = None
_openrouter_client: OpenAI | None = None


def normalize_text(text: str) -> str:
    """
    Embeddings API не приймає порожній input.
    Також прибираємо зайві переноси рядків.
    """
    cleaned = (text or "").replace("\n", " ").strip()

    if not cleaned:
        return " "

    return cleaned


def chunk_list(items: list[str], batch_size: int) -> list[list[str]]:
    """
    Ділить список текстів на batch-и.

    Це потрібно:
    - для сумісності зі старими smoke scripts;
    - щоб не відправляти занадто великий batch в remote embeddings API.
    """
    return [
        items[index:index + batch_size]
        for index in range(0, len(items), batch_size)
    ]


def get_local_model():
    """
    Lazy-load локальної sentence-transformers моделі.

    Важливо:
    - імпорт sentence_transformers тут, а не на рівні файлу;
    - Render з EMBEDDING_PROVIDER=openrouter не буде імпортувати torch.
    """
    global _local_model

    if _local_model is None:
        from sentence_transformers import SentenceTransformer

        _local_model = SentenceTransformer(settings.local_embedding_model)

    return _local_model


def get_openrouter_embedding_client() -> OpenAI:
    """
    OpenRouter embeddings client через OpenAI-compatible SDK.
    """
    global _openrouter_client

    if _openrouter_client is None:
        if not settings.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set")

        _openrouter_client = OpenAI(
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
            default_headers={
                "HTTP-Referer": settings.openrouter_site_url,
                "X-OpenRouter-Title": settings.openrouter_app_title,
            },
        )

    return _openrouter_client


def embed_text(text: str) -> list[float]:
    """
    Створює embedding для одного тексту.
    """
    return embed_texts([text])[0]


def embed_texts(
    texts: list[str],
    batch_size: int = 32,
) -> list[list[float]]:
    """
    Hybrid embeddings provider.

    EMBEDDING_PROVIDER=local:
        sentence-transformers/all-MiniLM-L6-v2

    EMBEDDING_PROVIDER=openrouter:
        OpenRouter embeddings API / openai/text-embedding-3-small

    batch_size залишаємо в сигнатурі, бо scripts/test_embeddings.py
    і scripts/index.py можуть передавати його явно.
    """
    provider = settings.embedding_provider.lower().strip()

    cleaned_texts = [
        normalize_text(text)
        for text in texts
    ]

    if not cleaned_texts:
        return []

    if provider == "local":
        model = get_local_model()

        embeddings = model.encode(
            cleaned_texts,
            batch_size=batch_size,
            normalize_embeddings=True,
        )

        return [
            embedding.tolist()
            for embedding in embeddings
        ]

    if provider == "openrouter":
        client = get_openrouter_embedding_client()
        all_vectors: list[list[float]] = []

        for batch in chunk_list(cleaned_texts, batch_size=batch_size):
            response = client.embeddings.create(
                model=settings.remote_embedding_model,
                input=batch,
                dimensions=settings.embedding_dimensions,
                encoding_format="float",
            )

            vectors_by_index = {
                item.index: item.embedding
                for item in response.data
            }

            batch_vectors = [
                vectors_by_index[index]
                for index in range(len(batch))
            ]

            all_vectors.extend(batch_vectors)

        return all_vectors

    raise ValueError(
        f"Unsupported EMBEDDING_PROVIDER={settings.embedding_provider}. "
        "Use 'local' or 'openrouter'."
    )