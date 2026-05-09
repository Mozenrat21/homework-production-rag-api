import json
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from qdrant_client.http import models

from app.core.settings import settings
from app.services.vector_store import EMBEDDING_DIMENSION, get_qdrant_client


def make_cache_point_id(query: str) -> str:
    """
    Стабільний UUID для cache point.

    Якщо той самий query буде збережений повторно,
    він оновить існуючий запис.
    """
    normalized_query = query.strip().lower()
    return str(uuid5(NAMESPACE_URL, f"semantic-cache:{normalized_query}"))


def ensure_cache_collection() -> None:
    """
    Створює Qdrant collection для semantic cache, якщо її ще немає.
    """
    client = get_qdrant_client()
    collection_name = settings.qdrant_cache_collection

    if client.collection_exists(collection_name=collection_name):
        return

    client.create_collection(
        collection_name=collection_name,
        vectors_config=models.VectorParams(
            size=EMBEDDING_DIMENSION,
            distance=models.Distance.COSINE,
        ),
    )


def find_cached_answer(
    query_vector: list[float],
    threshold: float | None = None,
) -> dict | None:
    """
    Шукає найближчий cached query.

    Якщо similarity score >= threshold — повертаємо cached answer.
    """
    client = get_qdrant_client()
    collection_name = settings.qdrant_cache_collection
    threshold = threshold or settings.semantic_cache_threshold

    ensure_cache_collection()

    results = client.search(
        collection_name=collection_name,
        query_vector=query_vector,
        limit=1,
        with_payload=True,
    )

    if not results:
        return None

    best = results[0]
    payload = best.payload or {}

    if best.score < threshold:
        return None

    sources_json = payload.get("sources_json", "[]")

    try:
        sources = json.loads(sources_json)
    except json.JSONDecodeError:
        sources = []

    return {
        "answer": payload.get("answer", ""),
        "model": payload.get("model", "cache"),
        "sources": sources,
        "score": float(best.score),
        "original_query": payload.get("query", ""),
        "created_at_utc": payload.get("created_at_utc"),
    }


def save_cached_answer(
    query: str,
    query_vector: list[float],
    answer: str,
    model: str,
    sources: list[dict],
) -> None:
    """
    Зберігає відповідь у semantic cache.
    """
    client = get_qdrant_client()
    collection_name = settings.qdrant_cache_collection

    ensure_cache_collection()

    point_id = make_cache_point_id(query)

    payload = {
        "query": query,
        "answer": answer,
        "model": model,
        "sources_json": json.dumps(sources, ensure_ascii=False),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    client.upsert(
        collection_name=collection_name,
        points=[
            models.PointStruct(
                id=point_id,
                vector=query_vector,
                payload=payload,
            )
        ],
        wait=True,
    )