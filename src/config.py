"""Configuração centralizada via variáveis de ambiente.
Suporta OpenAI, Anthropic, Ollama e APIs custom compatíveis com OpenAI.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal, Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ─── Provedor LLM ─────────────────────────────────────────────
    # Escolha: "openai" | "anthropic" | "ollama" | "custom_openai"
    llm_provider: str = "custom_openai"

    # OpenAI nativo
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Anthropic nativo
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-haiku-20240307"

    # Ollama (local)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"

    # ─── Custom OpenAI-compatible (OpenCode Zen, OpenCode Go) ────
    # Define baseURL, apiKey e model para qualquer API compatível com OpenAI.
    # Perfis disponíveis (mude CUSTOM_PROFILE):
    #   "opencode-go"       → Assinatura de baixo custo
    #   "opencode-zen"      → Gateway pay-as-you-go
    #   "opencode-zen-free" → Modelos gratuitos (default)
    custom_profile: str = "opencode-zen-free"
    custom_api_key: str = ""
    custom_base_url: str = ""
    custom_model: str = ""

    # ─── API Keys (via .env, NÃO hardcoded) ──────────────────────
    opencode_zen_api_key: str = ""
    opencode_go_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # ─── Perfis pré-configurados ─────────────────────────────────
    # Mapeamento de perfis → (baseURL, model padrão)
    # As API keys são obtidas das variáveis de ambiente
    CUSTOM_PROFILES: dict = {
        # ─── OpenCode Zen ──────────────────────────────────────
        "opencode-zen": {
            "base_url": "https://opencode.ai/zen/v1",
            "api_key_var": "opencode_zen_api_key",
            "model": "gpt-5.4",
        },
        "opencode-zen-free": {
            "base_url": "https://opencode.ai/zen/v1",
            "api_key_var": "opencode_zen_api_key",
            "model": "deepseek-v4-flash-free",
        },
        "opencode-zen-openai": {
            "base_url": "https://opencode.ai/zen/v1",
            "api_key_var": "opencode_zen_api_key",
            "model": "gpt-5.5",
        },
        "opencode-zen-anthropic": {
            "base_url": "https://opencode.ai/zen/v1",
            "api_key_var": "opencode_zen_api_key",
            "model": "claude-sonnet-5",
        },
        "opencode-zen-paid": {
            "base_url": "https://opencode.ai/zen/v1",
            "api_key_var": "opencode_zen_api_key",
            "model": "deepseek-v4-flash",
        },
        # ─── OpenCode Go ───────────────────────────────────────
        "opencode-go": {
            "base_url": "https://opencode.ai/zen/go/v1",
            "api_key_var": "opencode_go_api_key",
            "model": "deepseek-v4-flash",
        },
        "opencode-go-anthropic": {
            "base_url": "https://opencode.ai/zen/go/v1",
            "api_key_var": "opencode_go_api_key",
            "model": "qwen3.7-max",
        },
    }

    # ─── Embeddings ──────────────────────────────────────────────
    embedding_provider: Literal["openai", "huggingface"] = "huggingface"
    embedding_model: str = "all-MiniLM-L6-v2"

    # ─── Vector DB ───────────────────────────────────────────────
    vector_db_type: Literal["chroma", "pinecone", "qdrant"] = "chroma"
    chroma_persist_dir: str = "./data/chroma"

    # ─── Database ────────────────────────────────────────────────
    database_url: str = "sqlite:///./data/chatbot.db"
    auth_secret_key: str = ""
    user_data_dir: str = "./data/users"
    initial_admin_email: str = ""
    initial_admin_username: str = ""
    initial_admin_password: str = ""
    allow_registration: bool = False

    # Perplexo HTTP tool server. The API key is global infrastructure config and
    # is never returned to clients or persisted in per-user skill settings.
    perplexo_base_url: str = "https://api.ghost1.cloud"
    mcp_api_key: str = ""
    perplexo_timeout_seconds: float = 25.0

    # Inworld TTS. The API key is infrastructure-only and is never returned to
    # the browser. Audio is synthesized in short chunks produced from LLM SSE.
    inworld_api_key: str = ""
    inworld_tts_base_url: str = "https://api.inworld.ai"
    inworld_tts_model: str = "inworld-tts-2"
    inworld_tts_default_voice: str = ""
    inworld_tts_timeout_seconds: float = 20.0
    inworld_tts_voice_cache_seconds: int = 300
    inworld_tts_audio_cache_seconds: int = 300
    inworld_tts_audio_cache_max_items: int = 256

    # Codex SSE v2 keeps the current parser available as an instant rollback.
    codex_sse_enabled: bool = True
    codex_response_mode_default: Literal["normal", "thinking", "live"] = "normal"
    # Antigravity uses an internal Google endpoint; this flag is an instant
    # rollback if that non-public protocol changes.
    antigravity_enabled: bool = True

    # ─── Redis ───────────────────────────────────────────────────
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # ─── App ─────────────────────────────────────────────────────
    log_level: str = "INFO"
    api_port: int = 8000
    max_upload_size_mb: int = 10
    enable_moderation: bool = True
    enable_multilang: bool = True
    enable_rag: bool = True
    rate_limit_per_minute: int = 30

    # ─── Helpers ────────────────────────────────────────────────
    @property
    def custom_provider_config(self) -> dict:
        """Retorna a configuração do perfil custom selecionado."""
        profile = self.custom_profile
        cfg = self.CUSTOM_PROFILES.get(profile, {})

        # Resolve a API key do perfil (via env var) ou do campo manual
        api_key_var = cfg.get("api_key_var", "")
        env_api_key = getattr(self, api_key_var, "") if api_key_var else ""
        api_key = self.custom_api_key or env_api_key or ""

        # Se o usuário definiu manualmente, sobrepõe
        return {
            "base_url": self.custom_base_url or cfg.get("base_url", ""),
            "api_key": api_key,
            "model": self.custom_model or cfg.get("model", "gpt-4o-mini"),
        }


settings = Settings()
