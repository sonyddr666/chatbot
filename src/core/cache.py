"""Cache Redis para respostas frequentes."""

from typing import Optional, Any
import json
import hashlib

from src.config import settings

# Tenta conectar ao Redis, fallback para cache em memória
_redis_client = None
_memory_cache: dict[str, Any] = {}

try:
    import redis.asyncio as aioredis
    _redis_client = aioredis.from_url(
        f"redis://{settings.redis_host}:{settings.redis_port}/{settings.redis_db}",
        decode_responses=True,
    )
except Exception:
    pass


def _make_key(prefix: str, *args) -> str:
    """Gera uma chave de cache."""
    content = ":".join(str(a) for a in args)
    return f"{prefix}:{hashlib.md5(content.encode()).hexdigest()}"


async def cache_get(key: str) -> Optional[str]:
    """Obtém valor do cache."""
    if _redis_client:
        try:
            return await _redis_client.get(key)
        except Exception:
            return _memory_cache.get(key)
    return _memory_cache.get(key)


async def cache_set(key: str, value: str, ttl: int = 3600) -> None:
    """Armazena valor no cache com TTL."""
    if _redis_client:
        try:
            await _redis_client.setex(key, ttl, value)
            return
        except Exception:
            pass
    _memory_cache[key] = value


async def cache_delete(key: str) -> None:
    """Remove valor do cache."""
    if _redis_client:
        try:
            await _redis_client.delete(key)
            return
        except Exception:
            pass
    _memory_cache.pop(key, None)


async def cache_llm_response(prompt_hash: str, response: str, ttl: int = 300) -> None:
    """Cacheia resposta LLM."""
    key = _make_key("llm", prompt_hash)
    await cache_set(key, response, ttl)


async def get_cached_llm_response(prompt_hash: str) -> Optional[str]:
    """Recupera resposta LLM cacheada."""
    key = _make_key("llm", prompt_hash)
    return await cache_get(key)
