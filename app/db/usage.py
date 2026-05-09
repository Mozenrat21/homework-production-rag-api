import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.settings import settings


def get_connection() -> sqlite3.Connection:
    """
    Повертає SQLite connection.
    """
    db_path = Path(settings.sqlite_db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row

    return connection


def init_usage_db() -> None:
    """
    Створює таблицю usage_logs, якщо її ще немає.
    """
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS usage_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at_utc TEXT NOT NULL,
                model TEXT NOT NULL,
                input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                estimated_cost_usd REAL NOT NULL,
                latency_ms INTEGER NOT NULL,
                cache_hit INTEGER NOT NULL,
                status TEXT NOT NULL,
                error_message TEXT,
                user_message TEXT,
                sources_json TEXT
            )
            """
        )

        connection.commit()


def estimate_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """
    Дуже проста оцінка вартості.

    Для free-моделей повертаємо 0.
    Для gpt-4o-mini використовуємо приблизну оцінку:
    input:  $0.15 / 1M tokens
    output: $0.60 / 1M tokens

    Для інших моделей поки 0, щоб не вигадувати ціни.
    """
    model_lower = model.lower()

    if ":free" in model_lower or "openrouter/free" in model_lower:
        return 0.0

    if "gpt-4o-mini" in model_lower:
        input_cost = input_tokens * 0.15 / 1_000_000
        output_cost = output_tokens * 0.60 / 1_000_000
        return round(input_cost + output_cost, 8)

    return 0.0


def log_usage(
    model: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    cache_hit: bool,
    status: str,
    user_message: str,
    sources_json: str,
    error_message: str | None = None,
) -> None:
    """
    Записує usage log одного запиту.
    """
    estimated_cost_usd = estimate_cost_usd(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )

    created_at_utc = datetime.now(timezone.utc).isoformat()

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO usage_logs (
                created_at_utc,
                model,
                input_tokens,
                output_tokens,
                estimated_cost_usd,
                latency_ms,
                cache_hit,
                status,
                error_message,
                user_message,
                sources_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                created_at_utc,
                model,
                input_tokens,
                output_tokens,
                estimated_cost_usd,
                latency_ms,
                int(cache_hit),
                status,
                error_message,
                user_message,
                sources_json,
            ),
        )

        connection.commit()


def get_usage_today() -> dict[str, Any]:
    """
    Повертає usage summary за поточну UTC-добу.
    """
    today_utc = datetime.now(timezone.utc).date().isoformat()

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                COUNT(*) AS total_requests,
                COALESCE(SUM(input_tokens), 0) AS input_tokens,
                COALESCE(SUM(output_tokens), 0) AS output_tokens,
                COALESCE(SUM(estimated_cost_usd), 0) AS estimated_cost_usd,
                COALESCE(AVG(latency_ms), 0) AS avg_latency_ms,
                COALESCE(SUM(cache_hit), 0) AS cache_hits
            FROM usage_logs
            WHERE substr(created_at_utc, 1, 10) = ?
            """,
            (today_utc,),
        ).fetchone()

    total_requests = int(row["total_requests"] or 0)
    cache_hits = int(row["cache_hits"] or 0)

    cache_hit_rate = (
        round(cache_hits / total_requests, 4)
        if total_requests > 0
        else 0.0
    )

    return {
        "date_utc": today_utc,
        "total_requests": total_requests,
        "input_tokens": int(row["input_tokens"] or 0),
        "output_tokens": int(row["output_tokens"] or 0),
        "estimated_cost_usd": round(float(row["estimated_cost_usd"] or 0), 8),
        "avg_latency_ms": round(float(row["avg_latency_ms"] or 0), 2),
        "cache_hits": cache_hits,
        "cache_hit_rate": cache_hit_rate,
    }


def get_usage_breakdown() -> dict[str, Any]:
    """
    Повертає usage breakdown по моделях за поточну UTC-добу.

    Для ДЗ:
    - breakdown по моделях;
    - hit rate;
    - latency;
    - tokens;
    - estimated cost.
    """
    today_utc = datetime.now(timezone.utc).date().isoformat()

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                model,
                COUNT(*) AS total_requests,
                COALESCE(SUM(input_tokens), 0) AS input_tokens,
                COALESCE(SUM(output_tokens), 0) AS output_tokens,
                COALESCE(SUM(estimated_cost_usd), 0) AS estimated_cost_usd,
                COALESCE(AVG(latency_ms), 0) AS avg_latency_ms,
                COALESCE(MIN(latency_ms), 0) AS min_latency_ms,
                COALESCE(MAX(latency_ms), 0) AS max_latency_ms,
                COALESCE(SUM(cache_hit), 0) AS cache_hits
            FROM usage_logs
            WHERE substr(created_at_utc, 1, 10) = ?
            GROUP BY model
            ORDER BY total_requests DESC, model
            """,
            (today_utc,),
        ).fetchall()

    models = []

    total_requests_all = 0
    total_input_tokens = 0
    total_output_tokens = 0
    total_estimated_cost = 0.0
    total_cache_hits = 0

    for row in rows:
        total_requests = int(row["total_requests"] or 0)
        cache_hits = int(row["cache_hits"] or 0)

        cache_hit_rate = (
            round(cache_hits / total_requests, 4)
            if total_requests > 0
            else 0.0
        )

        input_tokens = int(row["input_tokens"] or 0)
        output_tokens = int(row["output_tokens"] or 0)
        estimated_cost = float(row["estimated_cost_usd"] or 0)

        total_requests_all += total_requests
        total_input_tokens += input_tokens
        total_output_tokens += output_tokens
        total_estimated_cost += estimated_cost
        total_cache_hits += cache_hits

        models.append(
            {
                "model": row["model"],
                "total_requests": total_requests,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "estimated_cost_usd": round(estimated_cost, 8),
                "avg_latency_ms": round(float(row["avg_latency_ms"] or 0), 2),
                "min_latency_ms": int(row["min_latency_ms"] or 0),
                "max_latency_ms": int(row["max_latency_ms"] or 0),
                "cache_hits": cache_hits,
                "cache_hit_rate": cache_hit_rate,
            }
        )

    overall_cache_hit_rate = (
        round(total_cache_hits / total_requests_all, 4)
        if total_requests_all > 0
        else 0.0
    )

    return {
        "date_utc": today_utc,
        "summary": {
            "total_requests": total_requests_all,
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "estimated_cost_usd": round(total_estimated_cost, 8),
            "cache_hits": total_cache_hits,
            "cache_hit_rate": overall_cache_hit_rate,
        },
        "models": models,
    }