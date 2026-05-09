import json
import sys
from pathlib import Path

# Додаємо корінь проєкту в Python path,
# щоб скрипт бачив папку app/
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.embeddings import embed_text, embed_texts


CHUNKS_PATH = Path("data/chunks.jsonl")


def load_first_chunks(limit: int = 3) -> list[dict]:
    """
    Читаємо кілька перших chunks для тесту.
    Не ганяємо одразу все, щоб не мучити ноут.
    """
    chunks = []

    with CHUNKS_PATH.open("r", encoding="utf-8") as file:
        for line in file:
            if len(chunks) >= limit:
                break

            chunks.append(json.loads(line))

    return chunks


def main() -> None:
    if not CHUNKS_PATH.exists():
        raise FileNotFoundError(
            "Не знайдено data/chunks.jsonl. Спочатку запусти python scripts/index.py"
        )

    print("Loading first chunks...")
    chunks = load_first_chunks(limit=3)

    texts = [chunk["text"] for chunk in chunks]

    print(f"Loaded chunks: {len(texts)}")
    print("Creating test embedding for one query...")

    query_vector = embed_text("What should be built in this homework?")

    print(f"Query embedding dimension: {len(query_vector)}")
    print(f"First 5 values: {query_vector[:5]}")

    print("\nCreating embeddings for first 3 chunks...")
    chunk_vectors = embed_texts(texts, batch_size=2)

    print(f"Created chunk embeddings: {len(chunk_vectors)}")

    for index, vector in enumerate(chunk_vectors, start=1):
        print(f"Chunk {index}: dimension = {len(vector)}")

    print("\nEmbeddings smoke test completed successfully")


if __name__ == "__main__":
    main()