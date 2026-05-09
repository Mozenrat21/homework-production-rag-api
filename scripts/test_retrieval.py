import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.embeddings import embed_text
from app.services.vector_store import search_chunks


def print_result(index: int, chunk: dict) -> None:
    print("=" * 80)
    print(f"Result #{index}")
    print(f"chunk_id: {chunk['chunk_id']}")
    print(f"source: {chunk['source']}")
    print(f"score: {chunk['score']:.4f}")
    print(f"token_count: {chunk['token_count']}")
    print("-" * 80)

    text = chunk["text"] or ""
    preview = text[:700].replace("\n", " ")

    print(preview)
    print()


def main() -> None:
    query = "What endpoints are required in this homework?"

    print(f"Query: {query}")
    print("Creating query embedding...")

    query_vector = embed_text(query)

    print(f"Query vector dimension: {len(query_vector)}")
    print("Searching top-3 chunks in Qdrant...")

    chunks = search_chunks(query_vector=query_vector, limit=3)

    print(f"Found chunks: {len(chunks)}")

    for index, chunk in enumerate(chunks, start=1):
        print_result(index, chunk)

    print("Retrieval test completed successfully")


if __name__ == "__main__":
    main()