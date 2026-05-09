import asyncio
import json
import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.core.runtime import mark_aborted_stream, stream_runtime_slot
from app.core.settings import settings
from app.db.usage import log_usage
from app.schemas.chat import ChatRequest
from app.services.embeddings import embed_text
from app.services.llm import build_context, get_model_chain, stream_llm_events
from app.services.rate_limiter import require_rate_limit
from app.services.security_guard import find_suspicious_pattern, log_suspicious_request
from app.services.semantic_cache import find_cached_answer, save_cached_answer
from app.services.token_counter import count_tokens
from app.services.vector_store import search_chunks


router = APIRouter()


def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat/stream")
async def chat_stream(
    payload: ChatRequest,
    http_request: Request,
    api_key: str = Depends(require_rate_limit),
):
    """
    Основний RAG endpoint.

    Workflow:
    auth
    → rate limit
    → prompt injection check
    → concurrency slot
    → query embedding
    → semantic cache check
    → якщо HIT: stream cached answer
    → якщо MISS: Qdrant top-k=3 → OpenRouter LLM streaming → save cache
    → cost tracking
    → done + sources + usage
    """
    if not settings.openrouter_api_key:
        raise HTTPException(
            status_code=500,
            detail="OPENROUTER_API_KEY is not configured",
        )

    suspicious_pattern = find_suspicious_pattern(payload.message)

    if suspicious_pattern:
        log_suspicious_request(
            message=payload.message,
            reason=f"prompt_injection_pattern:{suspicious_pattern}",
        )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Suspicious input detected",
                "type": "PromptInjectionRejected",
                "matched_pattern": suspicious_pattern,
            },
        )

    async def event_generator():
        started_at = time.perf_counter()

        actual_model = settings.openrouter_model_primary
        model_chain = get_model_chain()

        chunks = []
        output_parts = []

        try:
            async with stream_runtime_slot():
                yield sse_event(
                    "status",
                    {
                        "step": "received",
                        "message": "Request received",
                    },
                )

                yield sse_event(
                    "status",
                    {
                        "step": "embedding",
                        "message": "Creating query embedding",
                    },
                )

                query_vector = embed_text(payload.message)

                yield sse_event(
                    "status",
                    {
                        "step": "cache_check",
                        "message": "Checking semantic cache",
                        "threshold": settings.semantic_cache_threshold,
                    },
                )

                cached = find_cached_answer(query_vector=query_vector)

                if cached:
                    cached_answer = cached["answer"]
                    actual_model = cached["model"]
                    sources = cached["sources"]

                    yield sse_event(
                        "status",
                        {
                            "step": "cache_hit",
                            "score": round(cached["score"], 4),
                            "original_query": cached["original_query"],
                        },
                    )

                    # Стрімимо cached answer як токени.
                    # Це імітація streaming без виклику LLM.
                    for word in cached_answer.split(" "):
                        if await http_request.is_disconnected():
                            await mark_aborted_stream()
                            return

                        token = word + " "
                        output_parts.append(token)

                        yield sse_event(
                            "token",
                            {
                                "text": token,
                            },
                        )

                    latency_ms = int((time.perf_counter() - started_at) * 1000)

                    input_tokens = count_tokens(payload.message)
                    output_text = "".join(output_parts)
                    output_tokens = count_tokens(output_text)

                    log_usage(
                        model=actual_model,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        latency_ms=latency_ms,
                        cache_hit=True,
                        status="success",
                        user_message=payload.message,
                        sources_json=json.dumps(sources, ensure_ascii=False),
                    )

                    yield sse_event(
                        "done",
                        {
                            "sources": sources,
                            "cache_hit": True,
                            "cache_score": round(cached["score"], 4),
                            "model": actual_model,
                            "model_chain": model_chain,
                            "usage": {
                                "input_tokens": input_tokens,
                                "output_tokens": output_tokens,
                                "latency_ms": latency_ms,
                            },
                        },
                    )

                    return

                yield sse_event(
                    "status",
                    {
                        "step": "cache_miss",
                        "message": "No semantic cache hit",
                    },
                )

                yield sse_event(
                    "status",
                    {
                        "step": "retrieval",
                        "message": "Searching top-3 chunks in Qdrant",
                    },
                )

                chunks = search_chunks(
                    query_vector=query_vector,
                    limit=3,
                )

                yield sse_event(
                    "status",
                    {
                        "step": "llm",
                        "message": "Streaming answer from OpenRouter",
                        "model_chain": model_chain,
                    },
                )

                async for llm_event in stream_llm_events(
                    user_message=payload.message,
                    chunks=chunks,
                ):
                    if await http_request.is_disconnected():
                        await mark_aborted_stream()
                        return

                    if llm_event["type"] == "model_attempt":
                        yield sse_event(
                            "status",
                            {
                                "step": "llm_model_attempt",
                                "model": llm_event["model"],
                            },
                        )

                    elif llm_event["type"] == "model_failed":
                        yield sse_event(
                            "status",
                            {
                                "step": "llm_model_failed",
                                "model": llm_event["model"],
                                "reason": llm_event["reason"],
                            },
                        )

                    elif llm_event["type"] == "model":
                        actual_model = llm_event["model"]

                        yield sse_event(
                            "status",
                            {
                                "step": "llm_model_selected",
                                "model": actual_model,
                            },
                        )

                    elif llm_event["type"] == "token":
                        output_parts.append(llm_event["text"])

                        yield sse_event(
                            "token",
                            {
                                "text": llm_event["text"],
                            },
                        )

                sources = [
                    {
                        "chunk_id": chunk.get("chunk_id"),
                        "source": chunk.get("source"),
                        "score": round(float(chunk.get("score") or 0), 4),
                    }
                    for chunk in chunks
                ]

                latency_ms = int((time.perf_counter() - started_at) * 1000)

                context_text = build_context(chunks)
                input_text = f"{context_text}\n\nQuestion:\n{payload.message}"
                output_text = "".join(output_parts)

                input_tokens = count_tokens(input_text)
                output_tokens = count_tokens(output_text)

                if output_text.strip():
                    save_cached_answer(
                        query=payload.message,
                        query_vector=query_vector,
                        answer=output_text,
                        model=actual_model,
                        sources=sources,
                    )
                else:
                    yield sse_event(
                        "status",
                        {
                            "step": "cache_skip",
                            "reason": "empty_llm_response",
                        },
                    )

                log_usage(
                    model=actual_model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_ms=latency_ms,
                    cache_hit=False,
                    status="success",
                    user_message=payload.message,
                    sources_json=json.dumps(sources, ensure_ascii=False),
                )

                yield sse_event(
                    "done",
                    {
                        "sources": sources,
                        "cache_hit": False,
                        "model": actual_model,
                        "model_chain": model_chain,
                        "usage": {
                            "input_tokens": input_tokens,
                            "output_tokens": output_tokens,
                            "latency_ms": latency_ms,
                        },
                    },
                )

        except asyncio.CancelledError:
            await mark_aborted_stream()
            return

        except Exception as error:
            latency_ms = int((time.perf_counter() - started_at) * 1000)

            try:
                context_text = build_context(chunks) if chunks else ""
                input_text = f"{context_text}\n\nQuestion:\n{payload.message}"
                output_text = "".join(output_parts)

                log_usage(
                    model=actual_model,
                    input_tokens=count_tokens(input_text),
                    output_tokens=count_tokens(output_text),
                    latency_ms=latency_ms,
                    cache_hit=False,
                    status="error",
                    error_message=str(error),
                    user_message=payload.message,
                    sources_json="[]",
                )
            except Exception:
                pass

            yield sse_event(
                "error",
                {
                    "message": str(error),
                    "type": error.__class__.__name__,
                    "model_chain": model_chain,
                },
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )