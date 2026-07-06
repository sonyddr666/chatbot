# Project Summary And Cleanup Notes

## Current Snapshot

This project is a full-stack intelligent chatbot with a FastAPI backend, React/Vite frontend, SQLite persistence, RAG through ChromaDB, and multi-provider LLM configuration.

## What Was Found

- The folder was not initialized as a Git repository when checked.
- The GitHub CLI (`gh`) was not installed in the local shell.
- `pytest` was not available in the global Python used by the shell, so tests could not run from that environment.
- Generated/local files exist and should stay out of GitHub: `.env`, `.venv/`, `frontend/node_modules/`, `frontend/dist/`, `data/`, logs, and Python bytecode caches.
- `src/api/ws_routes.py` appears duplicated or unused because the active WebSocket endpoint is already inside `src/api/app.py`.
- `src/tools/calculator.py`, `src/tools/weather.py`, and `src/tools/web_search.py` exist as examples, but they are not currently wired into the chat execution path.
- Provider fallback IDs are inconsistent in a few places: `opencode-zen-free` is the real default, but `zen-free` appears as an old fallback.
- `src/api/app.py` defines a custom `/docs` route redirecting to `/docs`, which can conflict with FastAPI's generated docs route.
- CORS is wide open with `allow_origins=["*"]` and `allow_credentials=True`, which is acceptable for local dev but should be tightened before production.

## Cleanup Conversation Summary

Safe or mostly safe to delete locally:

- `api.log`
- `frontend.log`
- `frontend/frontend.log`
- `nul`
- `frontend/dist/`
- `__pycache__/`
- `.pytest_cache/`

Recreatable but heavier:

- `.venv/`: recreate with `python -m venv .venv` and `pip install -r requirements.txt`.
- `frontend/node_modules/`: recreate with `npm install` inside `frontend/`.
- Hugging Face model cache: downloaded again when local embeddings run.

Do not delete without backup:

- `.env`: local secrets and environment config.
- `data/chatbot.db`: conversation history.
- `data/providers.json`: provider/model configuration.
- `data/account_pool.json`: Codex/ChatGPT token pool data.
- `data/chroma/`: local vector index for RAG.

## GitHub Upload Scope

Upload source, tests, docs, templates, lockfiles, Docker files, and scripts.

Do not upload secrets, runtime data, dependencies, build output, logs, or caches.

## Suggested Next Fixes

1. Initialize Git and push a clean source snapshot to `sonyddr666/chatbot`.
2. Fix provider fallback IDs from `zen-free` to `opencode-zen-free`.
3. Remove or wire `src/api/ws_routes.py`.
4. Decide whether `src/tools/` should become real function-calling tools or stay out of the app.
5. Fix the `/docs` redirect conflict.
6. Add a clean local setup path for tests.
