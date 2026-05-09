import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.settings import settings
from app.services.vector_store import get_qdrant_client


def main() -> None:
    print("Loaded Qdrant settings:")
    print(f"QDRANT_URL: {settings.qdrant_url}")
    print(f"QDRANT_API_KEY exists: {bool(settings.qdrant_api_key)}")
    print(f"Chunks collection: {settings.qdrant_chunks_collection}")

    client = get_qdrant_client()

    print("\nTrying to connect to Qdrant...")
    collections = client.get_collections()

    print("Connection OK")
    print(collections)


if __name__ == "__main__":
    main()