from pathlib import Path
import hashlib
import json
import re
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import tiktoken

from app.services.embeddings import embed_texts
from app.services.vector_store import recreate_chunks_collection, upsert_chunks


DATA_DIR = Path("data")
SOURCE_PATH = DATA_DIR / "source.md"
CHUNKS_PATH = DATA_DIR / "chunks.jsonl"

CHUNK_TOKENS = 500
OVERLAP_TOKENS = 50
ENCODING_NAME = "cl100k_base"


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def count_tokens(text: str, encoding) -> int:
    return len(encoding.encode(text))


def split_long_text_by_tokens(
    text: str,
    encoding,
    chunk_tokens: int = CHUNK_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[str]:
    token_ids = encoding.encode(text)
    chunks = []

    step = chunk_tokens - overlap_tokens

    for start in range(0, len(token_ids), step):
        end = start + chunk_tokens
        chunk_token_ids = token_ids[start:end]
        chunk_text = encoding.decode(chunk_token_ids).strip()

        if chunk_text:
            chunks.append(chunk_text)

        if end >= len(token_ids):
            break

    return chunks


def split_text_to_chunks(
    text: str,
    chunk_tokens: int = CHUNK_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[str]:
    encoding = tiktoken.get_encoding(ENCODING_NAME)
    text = normalize_text(text)

    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n", text)
        if paragraph.strip()
    ]

    chunks = []
    current_chunk = ""

    for paragraph in paragraphs:
        paragraph_token_count = count_tokens(paragraph, encoding)

        if paragraph_token_count > chunk_tokens:
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""

            chunks.extend(
                split_long_text_by_tokens(
                    paragraph,
                    encoding,
                    chunk_tokens=chunk_tokens,
                    overlap_tokens=overlap_tokens,
                )
            )
            continue

        candidate = f"{current_chunk}\n\n{paragraph}".strip()

        if count_tokens(candidate, encoding) <= chunk_tokens:
            current_chunk = candidate
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())

            previous_tokens = encoding.encode(current_chunk)
            overlap_text = encoding.decode(previous_tokens[-overlap_tokens:]).strip()

            if overlap_text:
                current_chunk = f"{overlap_text}\n\n{paragraph}".strip()
            else:
                current_chunk = paragraph

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks


def make_chunk_record(chunk_id: str, text: str, source: str, encoding) -> dict:
    return {
        "chunk_id": chunk_id,
        "source": source,
        "text": text,
        "token_count": count_tokens(text, encoding),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def write_chunks_jsonl(records: list[dict]) -> None:
    DATA_DIR.mkdir(exist_ok=True)

    with CHUNKS_PATH.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> None:
    if not SOURCE_PATH.exists():
        raise FileNotFoundError(
            f"Не знайдено {SOURCE_PATH}. Спочатку створи data/source.md"
        )

    encoding = tiktoken.get_encoding(ENCODING_NAME)

    source_text = SOURCE_PATH.read_text(encoding="utf-8")
    chunks = split_text_to_chunks(source_text)

    records = []

    for index, chunk_text in enumerate(chunks, start=1):
        chunk_id = f"chunk_{index:04d}"

        record = make_chunk_record(
            chunk_id=chunk_id,
            text=chunk_text,
            source=str(SOURCE_PATH),
            encoding=encoding,
        )

        records.append(record)

    write_chunks_jsonl(records)

    total_tokens = sum(record["token_count"] for record in records)

    print("Index preparation completed")
    print(f"Source file: {SOURCE_PATH}")
    print(f"Chunks file: {CHUNKS_PATH}")
    print(f"Total chunks: {len(records)}")
    print(f"Total tokens in chunks: {total_tokens}")

    print("\nCreating embeddings...")
    texts = [record["text"] for record in records]
    vectors = embed_texts(texts, batch_size=4)

    print(f"Created embeddings: {len(vectors)}")
    print(f"Embedding dimension: {len(vectors[0]) if vectors else 0}")

    print("\nRecreating Qdrant collection...")
    recreate_chunks_collection()

    print("Uploading chunks to Qdrant...")
    upsert_chunks(records=records, vectors=vectors)

    print("\nQdrant indexing completed successfully")

    if records:
        print("\nFirst chunk preview:")
        print("-" * 80)
        print(records[0]["text"][:1000])
        print("-" * 80)


if __name__ == "__main__":
    main()