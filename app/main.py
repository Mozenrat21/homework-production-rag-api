from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.chat import router as chat_router
from app.api.index import router as index_router
from app.api.usage import router as usage_router
from app.core.runtime import get_runtime_metrics
from app.db.usage import init_usage_db
from app.services.observability import flush_langfuse, setup_langfuse_env
from app.services.semantic_cache import ensure_cache_collection


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_usage_db()
    ensure_cache_collection()
    setup_langfuse_env()

    yield

    flush_langfuse()


app = FastAPI(
    title="Production RAG API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(chat_router)
app.include_router(usage_router)
app.include_router(index_router)


@app.get("/health")
async def health():
    metrics = await get_runtime_metrics()

    return {
        "status": "ok",
        **metrics,
    }