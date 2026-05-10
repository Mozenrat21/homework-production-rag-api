# Lesson 10 — Production-Ready RAG API

Мінімальний production-style RAG API для домашнього завдання **Lesson 10 — API Layer for AI Systems**.

Сервіс відповідає на питання по документу `data/source.md`: створює embedding для запиту, шукає релевантні chunks у Qdrant, передає контекст у LLM через OpenRouter і повертає відповідь через **SSE streaming**.

---

## 1. Public Deploy

Public URL:

```text
https://homework-production-rag-api.onrender.com
```

Корисні адреси:

```text
GET  https://homework-production-rag-api.onrender.com/health
POST https://homework-production-rag-api.onrender.com/chat/stream
GET  https://homework-production-rag-api.onrender.com/usage/today
GET  https://homework-production-rag-api.onrender.com/usage/breakdown
POST https://homework-production-rag-api.onrender.com/index/rebuild
```

> Render Free може засинати після неактивності, тому перший запит після паузи може бути повільним.

---

## 2. Що реалізовано

- FastAPI backend.
- SSE streaming endpoint `POST /chat/stream`.
- RAG retrieval через Qdrant Cloud.
- Semantic cache в окремій Qdrant collection.
- Hybrid embeddings provider:
  - локально: `sentence-transformers/all-MiniLM-L6-v2`;
  - Render: `openai/text-embedding-3-small` через OpenRouter embeddings API.
- OpenRouter LLM integration.
- Multi-model fallback chain.
- API key authentication через `X-API-Key`.
- Redis / Upstash rate limiting.
- SQLite usage / cost tracking.
- Prompt injection defense.
- Concurrency control через `asyncio.Semaphore`.
- Runtime metrics у `/health`.
- Langfuse observability.
- Admin endpoint для переіндексації документа.
- Dockerfile.
- Public deploy через Render Web Service.

---

## 3. Архітектура

```text
User
  ↓
FastAPI
  ↓
Auth: X-API-Key
  ↓
Rate limit: Upstash Redis
  ↓
Prompt Injection Guard
  ↓
Concurrency Slot
  ↓
Embeddings Provider
  ↓
Semantic Cache: Qdrant
  ↓
Vector Search: Qdrant top-k
  ↓
LLM: OpenRouter with fallback
  ↓
SSE Streaming Response
  ↓
Cost Tracking: SQLite
  ↓
Observability: Langfuse
```

Основний workflow `/chat/stream`:

```text
auth
→ rate limit
→ prompt injection check
→ embed query
→ semantic cache check
→ vector search
→ LLM call with fallback
→ stream tokens
→ log usage
→ return sources
```

---

## 4. Структура проєкту

```text
lesson-10-production-rag-api/
├── app/
│   ├── api/
│   │   ├── chat.py
│   │   ├── index.py
│   │   └── usage.py
│   ├── core/
│   │   ├── runtime.py
│   │   ├── security.py
│   │   └── settings.py
│   ├── db/
│   │   └── usage.py
│   ├── schemas/
│   │   └── chat.py
│   ├── services/
│   │   ├── embeddings.py
│   │   ├── llm.py
│   │   ├── observability.py
│   │   ├── rate_limiter.py
│   │   ├── security_guard.py
│   │   ├── semantic_cache.py
│   │   ├── token_counter.py
│   │   └── vector_store.py
│   └── main.py
├── data/
│   └── source.md
├── scripts/
│   ├── check_qdrant.py
│   ├── check_redis.py
│   ├── clear_semantic_cache.py
│   ├── index.py
│   ├── test_embeddings.py
│   ├── test_openrouter.py
│   └── test_retrieval.py
├── Dockerfile
├── requirements.txt
├── requirements-local.txt
├── .env.example
└── README.md
```

Generated/local files не комітяться:

```text
.env
.venv/
data/chunks.jsonl
data/usage.db
logs/*.log
__pycache__/
body.json
```

---

## 5. Environment variables

Створи `.env` на основі `.env.example`.

Основні змінні:

```env
APP_API_KEY=your_api_key_here

QDRANT_URL=your_qdrant_cloud_url_here
QDRANT_API_KEY=your_qdrant_api_key_here
QDRANT_CHUNKS_COLLECTION=rag_chunks
QDRANT_CACHE_COLLECTION=rag_cache

OPENROUTER_API_KEY=your_openrouter_api_key_here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL_PRIMARY=openrouter/free
OPENROUTER_MODEL_FALLBACK_1=meta-llama/llama-3.2-3b-instruct:free
OPENROUTER_MODEL_FALLBACK_2=openai/gpt-4o-mini
OPENROUTER_SITE_URL=http://localhost:8000
OPENROUTER_APP_TITLE=Lesson 10 Production RAG API

EMBEDDING_PROVIDER=local
LOCAL_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
REMOTE_EMBEDDING_MODEL=openai/text-embedding-3-small
EMBEDDING_DIMENSIONS=384

SQLITE_DB_PATH=./data/usage.db
SEMANTIC_CACHE_THRESHOLD=0.92

REDIS_URL=your_upstash_redis_connection_string_here
RATE_LIMIT_REQUESTS_PER_MINUTE=3
RATE_LIMIT_WINDOW_SECONDS=60

MAX_CONCURRENT_STREAMS=3
INDEX_REBUILD_TIMEOUT_SECONDS=180

LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=your_langfuse_public_key_here
LANGFUSE_SECRET_KEY=your_langfuse_secret_key_here
LANGFUSE_BASE_URL=https://cloud.langfuse.com
LANGFUSE_TRACING_ENVIRONMENT=local
```

Для Render використовуються такі відмінності:

```env
EMBEDDING_PROVIDER=openrouter
QDRANT_CHUNKS_COLLECTION=rag_chunks_openrouter
QDRANT_CACHE_COLLECTION=rag_cache_openrouter
OPENROUTER_SITE_URL=https://homework-production-rag-api.onrender.com
RATE_LIMIT_REQUESTS_PER_MINUTE=10
LANGFUSE_TRACING_ENVIRONMENT=render
```

`.env` не комітиться. Секрети для Render додані через Render Environment Variables.

---

## 6. Локальний запуск

### 6.1. Встановлення

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-local.txt
```

`requirements-local.txt` встановлює базові залежності плюс `sentence-transformers` для локального embeddings-provider.

### 6.2. Створити індекс

```powershell
python scripts/index.py
```

Очікувано:

```text
Created embeddings: 16
Embedding dimension: 384
Qdrant indexing completed successfully
```

### 6.3. Запустити API

```powershell
uvicorn app.main:app --reload --port 8000
```

### 6.4. Перевірити локально

```powershell
curl.exe http://127.0.0.1:8000/health
```

---

## 7. Docker

```powershell
docker build -t lesson-10-rag-api .
docker run --rm -p 8000:8000 --env-file .env lesson-10-rag-api
```

Перевірка:

```powershell
curl.exe http://127.0.0.1:8000/health
```

---

## 8. Public API usage

### 8.1. Health

```powershell
$baseUrl = "https://homework-production-rag-api.onrender.com"

curl.exe -i "$baseUrl/health"
```

Очікувано:

```json
{"status":"ok","active_streams":0,"aborted_streams":0,"max_concurrent_streams":3}
```

### 8.2. Chat streaming

```powershell
$baseUrl = "https://homework-production-rag-api.onrender.com"
$apiKey = "your_api_key_here"
$body = '{"message":"What endpoints are required in this homework?"}'

curl.exe -i -N -X POST "$baseUrl/chat/stream" `
  -H "Content-Type: application/json" `
  -H "X-API-Key: $apiKey" `
  --data-raw $body
```

Очікувано:

```text
HTTP/1.1 200 OK
Content-Type: text/event-stream

event: status
data: {"step":"received",...}

event: status
data: {"step":"retrieval",...}

event: token
data: {"text":"..."}

event: done
data: {"sources":[...],"cache_hit":false,"model":"...","usage":{...}}
```

### 8.3. Usage today

```powershell
curl.exe -i -X GET "$baseUrl/usage/today" `
  -H "X-API-Key: $apiKey"
```

### 8.4. Usage breakdown

```powershell
curl.exe -i -X GET "$baseUrl/usage/breakdown" `
  -H "X-API-Key: $apiKey"
```

### 8.5. Rebuild index

```powershell
curl.exe -i -X POST "$baseUrl/index/rebuild" `
  -H "X-API-Key: $apiKey"
```

---

## 9. Smoke scripts

```powershell
python scripts/check_qdrant.py
python scripts/check_redis.py
python scripts/test_embeddings.py
python scripts/test_retrieval.py
python scripts/test_openrouter.py
```

---

## 10. Security

Реалізовано:

- `X-API-Key` authentication.
- Prompt injection rule-based guard.
- Redis rate limiting.
- Hash для API key у Redis key.
- `.env` не комітиться.
- Secrets для Render зберігаються у Render Environment Variables.

---

## 11. Known limitations

- Semantic cache реалізований через Qdrant, а не Redis Vector.
- Cache TTL не реалізований як native TTL.
- SQLite `usage.db` на Render Free не є persistent storage.
- Render Free може засинати після неактивності.
- Cost tracking приблизний, бо streaming responses не завжди повертають usage metadata.
- Prompt injection defense rule-based, не ML-based.
- Для production бажано додати unit/integration tests і structured logging.

---

## 12. Acceptance checklist

| Requirement | Status |
|---|---|
| RAG basic layer | Done |
| Streaming API | Done |
| Auth | Done |
| Semantic cache | Done |
| Multi-model fallback | Done |
| Cost tracking | Done |
| `/usage/today` | Done |
| `/usage/breakdown` | Done |
| Rate limiting | Done |
| Prompt injection defense | Done |
| Async / concurrency control | Done |
| `/health` | Done |
| `/index/rebuild` | Done |
| Langfuse observability | Done |
| Dockerfile | Done |
| Docker local run | Done |
| Public deploy | Done via Render |
| Render `/chat/stream` | Done |

---

## 13. Final status

Проєкт реалізує production-style RAG API з публічним deploy.

Public URL:

```text
https://homework-production-rag-api.onrender.com
```

Main endpoint:

```text
POST /chat/stream
```
