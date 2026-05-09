from fastapi import APIRouter, Depends

from app.core.security import require_api_key
from app.db.usage import get_usage_breakdown, get_usage_today


router = APIRouter()


@router.get("/usage/today")
async def usage_today(
    api_key: str = Depends(require_api_key),
):
    """
    Повертає usage summary за сьогодні.

    Для ДЗ:
    - GET /usage/today;
    - витрати за сьогодні;
    - tokens;
    - estimated cost;
    - latency;
    - cache hit rate.
    """
    return get_usage_today()


@router.get("/usage/breakdown")
async def usage_breakdown(
    api_key: str = Depends(require_api_key),
):
    """
    Повертає usage breakdown по моделях.

    Для ДЗ:
    - GET /usage/breakdown;
    - розбивка по моделях;
    - hit rate;
    - latency.
    """
    return get_usage_breakdown()