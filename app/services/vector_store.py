from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient
from qdrant_client.http import models

from app.core.settings import settings


EMBEDDING_DIMENSION = 384


def get_qdrant_client() -> QdrantClient:
    """
    Створює Qdrant client.

    Для слабкого ноуту використовуємо Qdrant Cloud:
    - локально не піднімаємо Docker;
    - не тримаємо vector DB у RAM;
    """
    if not settings.qdrant_url:
        raise RuntimeError("QDRANT_URL is not set in .env")

    if not settings.qdrant_api_key:
        raise RuntimeError("QDRANT_API_KEY is not set in .env")

    return QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        timeout=60,
    )


def make_point_id(chunk_id: str) -> str:
    """
    Qdrant приймає point id як int або UUID.
    Наші chunk_id типу chunk_0001 зберігаємо в payload,
    а для point id робимо стабільний UUID.
    """
    return str(uuid5(NAMESPACE_URL, chunk_id))


def recreate_chunks_collection() -> None:
    """
    Пересоздає collection для chunks.
    """
    client = get_qdrant_client()

    client.recreate_collection(
        collection_name=settings.qdrant_chunks_collection,
        vectors_config=models.VectorParams(
            size=EMBEDDING_DIMENSION,
            distance=models.Distance.COSINE,
        ),
    )


def upsert_chunks(records: list[dict], vectors: list[list[float]]) -> None:
    """
    Записує chunks + embeddings у Qdrant.
    """
    if len(records) != len(vectors):
        raise ValueError("records and vectors length mismatch")

    client = get_qdrant_client()

    points = []

    for record, vector in zip(records, vectors):
        points.append(
            models.PointStruct(
                id=make_point_id(record["chunk_id"]),
                vector=vector,
                payload={
                    "chunk_id": record["chunk_id"],
                    "source": record["source"],
                    "text": record["text"],
                    "token_count": record["token_count"],
                    "sha256": record["sha256"],
                },
            )
        )

    client.upsert(
        collection_name=settings.qdrant_chunks_collection,
        points=points,
        wait=True,
    )


def search_chunks(query_vector: list[float], limit: int = 3) -> list[dict]:
    """
    Шукає top-k релевантних chunks у Qdrant.

    Для ДЗ:
    - query embedding;
    - search у vector DB;
    - top-k=3;
    - повертаємо chunk_id/source/text/score для майбутнього sources.
    """
    client = get_qdrant_client()

    results = client.search(
        collection_name=settings.qdrant_chunks_collection,
        query_vector=query_vector,
        limit=limit,
        with_payload=True,
    )

    chunks = []

    for item in results:
        payload = item.payload or {}

        chunks.append(
            {
                "chunk_id": payload.get("chunk_id"),
                "source": payload.get("source"),
                "text": payload.get("text"),
                "token_count": payload.get("token_count"),
                "score": item.score,
            }
        )

    return chunks