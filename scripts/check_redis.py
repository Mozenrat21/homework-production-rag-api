import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.rate_limiter import get_rate_limit_client


async def main() -> None:
    client = get_rate_limit_client()

    try:
        await client.set("lesson10:redis_check", "ok", ex=30)
        value = await client.get("lesson10:redis_check")

        print(f"Redis check value: {value}")

        if value != "ok":
            raise RuntimeError("Redis check failed")

        print("Redis connection OK")

    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())