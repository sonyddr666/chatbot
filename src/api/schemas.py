"""Modelos Pydantic para a API."""

from pydantic import BaseModel, Field
from typing import Optional, Any


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = "default"
    use_rag: bool = False


class ChatResponse(BaseModel):
    response: str
    session_id: str
    cached: bool = False
    message_id: Optional[int] = None
    provider_id: Optional[str] = None
    provider_name: Optional[str] = None
    model_id: Optional[str] = None
    model_name: Optional[str] = None


class ChatStreamRequest(BaseModel):
    message: str
    session_id: Optional[str] = "default"
    use_rag: bool = False


class IngestRequest(BaseModel):
    text: str
    source: Optional[str] = "manual"
    metadata: Optional[dict] = Field(default_factory=dict)


class IngestResponse(BaseModel):
    chunks_count: int
    ids: list[str]


class FeedbackRequest(BaseModel):
    message_id: int
    score: int  # 1 = like, -1 = dislike


class StatsResponse(BaseModel):
    total_messages: int = 0
    total_conversations: int = 0
    likes: int = 0
    dislikes: int = 0
    satisfaction_rate: float = 0.0


class ConversationResponse(BaseModel):
    id: int
    session_id: str
    title: str
    language: str
    message_count: int
    created_at: str
    updated_at: str


class RegisterRequest(BaseModel):
    email: str
    username: str
    password: str
    display_name: Optional[str] = ""


class LoginRequest(BaseModel):
    login: str
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    display_name: str = ""
    is_admin: bool = False


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class OnboardingRequest(BaseModel):
    display_name: Optional[str] = None
    language: Optional[str] = "pt"
    timezone: Optional[str] = "America/Sao_Paulo"
    role: Optional[str] = ""
    technical_level: Optional[str] = ""
    preferred_tone: Optional[str] = "direto"
    goals: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    memory_policy: Optional[str] = "ask"
    extra: dict[str, Any] = Field(default_factory=dict)


class SkillToggleRequest(BaseModel):
    enabled: bool
    config: Optional[dict[str, Any]] = None
