"""Modelos Pydantic para a API."""

from pydantic import BaseModel
from typing import Optional


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
    metadata: Optional[dict] = {}


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
