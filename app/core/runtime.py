import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from app.core.settings import settings


_stream_semaphore: asyncio.Semaphore | None = None
_metrics_lock = asyncio.Lock()

_active_streams = 0
_aborted_streams = 0


def get_stream_semaphore() -> asyncio.Semaphore:
    """
    Lazy init semaphore для обмеження одночасних streaming-запитів.
    """
    global _stream_semaphore

    if _stream_semaphore is None:
        _stream_semaphore = asyncio.Semaphore(settings.max_concurrent_streams)

    return _stream_semaphore


@asynccontextmanager
async def stream_runtime_slot() -> AsyncIterator[None]:
    """
    Захоплює слот для stream.

    Для ДЗ:
    - обмежуємо одночасні LLM/RAG streams;
    - рахуємо active_streams.
    """
    global _active_streams

    semaphore = get_stream_semaphore()

    await semaphore.acquire()

    async with _metrics_lock:
        _active_streams += 1

    try:
        yield

    finally:
        async with _metrics_lock:
            _active_streams = max(_active_streams - 1, 0)

        semaphore.release()


async def mark_aborted_stream() -> None:
    """
    Рахуємо обірвані клієнтом streams.
    """
    global _aborted_streams

    async with _metrics_lock:
        _aborted_streams += 1


async def get_runtime_metrics() -> dict:
    """
    Метрики для /health.
    """
    async with _metrics_lock:
        return {
            "active_streams": _active_streams,
            "aborted_streams": _aborted_streams,
            "max_concurrent_streams": settings.max_concurrent_streams,
        }