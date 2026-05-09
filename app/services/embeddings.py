from functools import lru_cache

from sentence_transformers import SentenceTransformer


DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    """
    Завантажуємо embedding model один раз і кешуємо в памʼяті.

    Для ДЗ:
    - використовуємо sentence-transformers;
    - модель all-MiniLM-L6-v2 легка;
    - dimension = 384.
    """
    return SentenceTransformer(DEFAULT_EMBEDDING_MODEL)


def embed_text(text: str) -> list[float]:
    """
    Створює embedding для одного тексту.
    """
    model = get_embedding_model()

    vector = model.encode(
        text,
        normalize_embeddings=True,
        show_progress_bar=False,
    )

    return vector.tolist()


def embed_texts(texts: list[str], batch_size: int = 4) -> list[list[float]]:
    """
    Створює embeddings для списку текстів.

    batch_size=4 — спеціально обережно для слабкого ноуту.
    Краще повільніше, ніж щоб ноут сказав: "я втомився, я мухожук".
    """
    model = get_embedding_model()

    vectors = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=True,
    )

    return vectors.tolist()