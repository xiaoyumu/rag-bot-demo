# rag_bot_demo

FastAPI-based RAG chatbot backend using LangChain, Weaviate, DeepSeek API, and Ollama embeddings.

## 1. Create virtual environment

On Windows:

```powershell
D:\Python\Python312\python.exe -m venv .venv
```

## 2. Install dependencies

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 3. Configure environment

```powershell
Copy-Item .env.example .env
```

Fill required values in `.env`, especially:
- `DEEPSEEK_API_KEY`
- `WEAVIATE_URL`
- `WEAVIATE_GRPC_HOST` / `WEAVIATE_GRPC_PORT` (v4 client, default `localhost:50051`)
- `OLLAMA_BASE_URL`

## 4. Run development server

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 5. Check service

- Debug UI: `http://127.0.0.1:8000/`
- Health: `http://127.0.0.1:8000/api/health`
- Swagger: `http://127.0.0.1:8000/docs`

## 6. API quick examples

Ingest local files:

```powershell
curl -X POST "http://127.0.0.1:8000/api/ingest/files" `
  -F "files=@D:\path\to\kb.md" `
  -F "files=@D:\path\to\manual.pdf"
```

Ask question:

```powershell
curl -X POST "http://127.0.0.1:8000/api/chat" `
  -H "Content-Type: application/json" `
  -d "{\"question\":\"请总结该知识库的核心内容\",\"enable_rewrite\":true,\"enable_rerank\":true}"
```

## 7. Run tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## 8. FlashRank offline model preload

The project is configured to run FlashRank in offline-only mode by default.

- Model name: `ms-marco-MiniLM-L-12-v2`
- Cache directory: `.cache/flashrank`
- Expected extracted path: `.cache/flashrank/ms-marco-MiniLM-L-12-v2`

On a machine with internet:

1) Download model zip from:
- `https://huggingface.co/prithivida/flashrank/resolve/main/ms-marco-MiniLM-L-12-v2.zip`

2) Copy zip to this project, then extract to:
- `.cache/flashrank/ms-marco-MiniLM-L-12-v2`

After extraction, keep `FLASHRANK_OFFLINE_ONLY=true` in `.env` to prevent online downloads.

## 9. Memory Phase-1 feature flags

Phase-1 introduces short-history budget trimming and profile memory (preference/constraint only).

Key flags in `.env`:

- `MEMORY_ENABLE`: enable short-history budget trimming in chat pipeline.
- `MEMORY_PROFILE_ENABLE`: enable profile extraction/load for each session.
- `MEMORY_SHORT_MAX_TOKENS`: max estimated tokens allowed for conversation history.
- `MEMORY_PROFILE_MAX_ITEMS`: max profile lines injected into prompts.
- `MONGODB_PROFILE_COLLECTION`: profile collection name (default `chat_profiles`).

Recommended initial values:

```env
MEMORY_ENABLE=true
MEMORY_PROFILE_ENABLE=true
MEMORY_SHORT_MAX_TOKENS=1200
MEMORY_PROFILE_MAX_ITEMS=6
MONGODB_PROFILE_COLLECTION=chat_profiles
```

Rollback:

- Set `MEMORY_ENABLE=false` to fully disable phase-1 memory behavior and keep current chat behavior.
