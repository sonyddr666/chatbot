"""Modelos Pydantic para a API."""

from pydantic import BaseModel, Field
from typing import Optional, Any


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = "default"
    use_rag: bool = False
    use_thinking: bool = True


class ChatResponse(BaseModel):
    response: str
    session_id: str
    cached: bool = False
    message_id: Optional[int] = None
    provider_id: Optional[str] = None
    provider_name: Optional[str] = None
    model_id: Optional[str] = None
    model_name: Optional[str] = None
    workspace_plan: Optional[dict] = None
    reasoning: Optional[str] = None
    skill_activities: list[dict[str, Any]] = Field(default_factory=list)


class ChatStreamRequest(BaseModel):
    message: str
    session_id: Optional[str] = "default"
    use_rag: bool = False
    use_thinking: bool = True


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


class RegistrationResponse(BaseModel):
    status: str = "pending"
    message: str


class AdminUserResponse(BaseModel):
    id: int
    email: str
    username: str
    display_name: str = ""
    is_admin: bool = False
    is_active: bool = False
    registration_status: str
    created_at: str
    approved_at: Optional[str] = None
    approved_by: Optional[int] = None


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


class PreferenceUpdateRequest(BaseModel):
    value: Any
    source: str = "manual"
    confidence: float = 1.0


class PreferenceSuggestionResolveRequest(BaseModel):
    accept: bool


class WorkspacePathRequest(BaseModel):
    path: str


class WorkspaceWriteRequest(BaseModel):
    path: str
    content: str


class WorkspaceMoveRequest(BaseModel):
    source: str
    target: str


class WorkspacePatchPreviewRequest(BaseModel):
    path: str
    content: str


class WorkspacePatchApplyRequest(BaseModel):
    path: str
    content: str
    expected_checksum: str


class WorkspaceAgentPlanRequest(BaseModel):
    instruction: str


class WorkspaceNodeResponse(BaseModel):
    name: str
    path: str
    kind: str
    size: int


class WorkspaceTreeResponse(BaseModel):
    path: str
    nodes: list[WorkspaceNodeResponse]


class WorkspaceFileResponse(BaseModel):
    path: str
    content: str


class WorkspaceInfoResponse(BaseModel):
    name: str
    path: str
    kind: str
    size: int


class WorkspacePatchPreviewResponse(BaseModel):
    path: str
    expected_checksum: str
    new_checksum: str
    diff: str


class WorkspacePatchApplyResponse(BaseModel):
    path: str
    applied: bool
    checksum: str
    snapshot_path: str
