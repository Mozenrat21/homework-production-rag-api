import asyncio
import sys
import traceback
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import require_api_key
from app.core.settings import settings


router = APIRouter()


def run_index_script() -> dict:
    """
    Запускає scripts/index.py напряму через import.

    Чому так:
    - на Windows subprocess в async endpoint може поводитися нестабільно;
    - asyncio.to_thread не блокує event loop FastAPI;
    - простіше отримати нормальну помилку, якщо rebuild впаде.
    """
    project_root = Path(__file__).resolve().parents[2]
    scripts_dir = project_root / "scripts"

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

    from scripts.index import main as index_main

    index_main()

    return {
        "status": "ok",
        "message": "Index rebuilt successfully",
    }


@router.post("/index/rebuild")
async def rebuild_index(
    api_key: str = Depends(require_api_key),
):
    """
    Admin endpoint для переіндексації документа.

    Для ДЗ:
    - POST /index/rebuild;
    - захищений X-API-Key;
    - перечитує data/source.md;
    - перебудовує chunks;
    - рахує embeddings;
    - перезаливає rag_chunks у Qdrant.
    """
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(run_index_script),
            timeout=settings.index_rebuild_timeout_seconds,
        )

        return result

    except asyncio.TimeoutError as error:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={
                "message": "Index rebuild timed out",
                "timeout_seconds": settings.index_rebuild_timeout_seconds,
            },
        ) from error

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "Index rebuild failed",
                "error": str(error),
                "traceback": traceback.format_exc()[-4000:],
            },
        ) from error