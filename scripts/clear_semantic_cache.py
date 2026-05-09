import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.settings import settings
from app.services.semantic_cache import ensure_cache_collection
from app.services.vector_store import get_qdrant_client


def main() -> None:
    client = get_qdrant_client()
    collection_name = settings.qdrant_cache_collection

    if client.collection_exists(collection_name=collection_name):
        client.delete_collection(collection_name=collection_name)
        print(f"Deleted cache collection: {collection_name}")

    ensure_cache_collection()
    print(f"Created empty cache collection: {collection_name}")


if __name__ == "__main__":
    main()