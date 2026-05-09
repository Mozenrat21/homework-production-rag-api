import hashlib
import time

import redis.asyncio as redis
from fastapi import Depends, HTTPException, status

from app.core.security import require_api_key
from app.core.settings import settings


_redis_client: redis.Redis | None = None


def get_rate_limit_client() -> redis.Redis:
    """
    Повертає Redis client для rate limiting.

    Для ДЗ:
    - Redis / Upstash;
    - не зберігаємо raw API key у Redis;
    - використовуємо hash ключа.
    """
    global _redis_client

    if not settings.redis_url:
        raise RuntimeError("REDIS_URL is not configured")

    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )

    return _redis_client


def hash_api_key(api_key: str) -> str:
    """
    Хешуємо API key, щоб не класти секрет у Redis key.
    """
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]


async def check_rate_limit(
    api_key: str,
    route_name: str,
) -> dict:
    """
    Fixed window rate limiter.

    Логіка:
    - window = 60 секунд;
    - для кожного API key + route ведемо лічильник;
    - якщо count > limit — повертаємо 429.
    """
    client = get_rate_limit_client()

    now = int(time.time())
    window_seconds = settings.rate_limit_window_seconds
    limit = settings.rate_limit_requests_per_minute

    bucket = now // window_seconds
    api_key_hash = hash_api_key(api_key)

    redis_key = f"rate_limit:{route_name}:{api_key_hash}:{bucket}"

    current_count = await client.incr(redis_key)

    if current_count == 1:
        await client.expire(redis_key, window_seconds + 5)

    remaining = max(limit - current_count, 0)
    reset_in_seconds = ((bucket + 1) * window_seconds) - now

    if current_count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "message": "Rate limit exceeded",
                "limit": limit,
                "window_seconds": window_seconds,
                "retry_after_seconds": reset_in_seconds,
            },
            headers={
                "Retry-After": str(reset_in_seconds),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset_in_seconds),
            },
        )

    return {
        "limit": limit,
        "remaining": remaining,
        "reset_in_seconds": reset_in_seconds,
    }


async def require_rate_limit(
    api_key: str = Depends(require_api_key),
) -> str:
    """
    FastAPI dependency:
    auth → rate limit.

    Якщо auth не пройшла — сюди не дійдемо.
    """
    try:
        await check_rate_limit(
            api_key=api_key,
            route_name="chat_stream",
        )
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Rate limiter unavailable: {error}",
        ) from error

    return api_key