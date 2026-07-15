"""SQLAlchemy models and lightweight SQLite migrations."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Index, create_engine, text
from sqlalchemy.orm import DeclarativeBase, relationship, Session

from src.config import settings


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(255), default="")
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    registration_status = Column(String(20), nullable=False, default="approved", index=True)
    approved_at = Column(DateTime, nullable=True)
    approved_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    profile = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    language = Column(String(10), default="pt")
    timezone = Column(String(80), default="America/Sao_Paulo")
    role = Column(String(255), default="")
    technical_level = Column(String(80), default="")
    preferred_tone = Column(String(120), default="")
    goals_json = Column(Text, default="[]")
    avoid_json = Column(Text, default="[]")
    memory_policy = Column(String(50), default="ask")
    onboarding_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="profile")


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    key = Column(String(120), nullable=False, index=True)
    value_json = Column(Text, default="{}")
    source = Column(String(80), default="manual")
    confidence = Column(Integer, default=100)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class PreferenceSuggestion(Base):
    __tablename__ = "preference_suggestions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    suggestion_type = Column(String(120), nullable=False, index=True)
    current_value_json = Column(Text, default="null")
    suggested_value_json = Column(Text, default="null")
    reason = Column(Text, default="")
    confidence = Column(Integer, default=70)
    status = Column(String(40), default="pending", index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    resolved_at = Column(DateTime, nullable=True)


class UserProviderConfig(Base):
    __tablename__ = "user_provider_configs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    provider_id = Column(String(120), nullable=False, index=True)
    display_name = Column(String(255), default="")
    base_url = Column(String(500), default="")
    model = Column(String(150), default="")
    api_format = Column(String(80), default="chat_completions")
    api_key_encrypted = Column(Text, default="")
    is_enabled = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class AntigravityAccount(Base):
    """Google Antigravity OAuth account owned by one chatbot user."""

    __tablename__ = "antigravity_accounts"
    __table_args__ = (
        Index("uq_antigravity_user_email", "user_id", "email", unique=True),
    )

    id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    email = Column(String(255), nullable=False, default="")
    label = Column(String(255), nullable=False, default="")
    access_token_encrypted = Column(Text, nullable=False, default="")
    refresh_token_encrypted = Column(Text, nullable=False, default="")
    client_id = Column(String(500), nullable=False, default="")
    client_secret_encrypted = Column(Text, nullable=False, default="")
    expires_at = Column(Integer, nullable=False, default=0)
    project_id = Column(String(255), nullable=False, default="")
    endpoint = Column(String(500), nullable=False, default="")
    models_json = Column(Text, nullable=False, default="{}")
    quota_json = Column(Text, nullable=False, default="[]")
    account_type = Column(String(255), nullable=False, default="")
    is_selected = Column(Boolean, nullable=False, default=False, index=True)
    is_enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    session_id = Column(String(100), unique=True, nullable=False, index=True)
    title = Column(String(255), default="Nova conversa")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    language = Column(String(10), default="pt")
    messages_count = Column(Integer, default=0)

    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    reasoning = Column(Text, nullable=False, default="")
    skill_activities_json = Column(Text, nullable=False, default="[]")
    attachments_json = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    feedback_score = Column(Integer, nullable=True)
    tokens_used = Column(Integer, default=0)
    moderated = Column(Boolean, default=False)
    provider_id = Column(String(100), nullable=True)
    provider_name = Column(String(255), nullable=True)
    model_id = Column(String(150), nullable=True)
    model_name = Column(String(255), nullable=True)
    job_id = Column(String(64), nullable=True, index=True)
    status = Column(String(30), nullable=False, default="completed", index=True)
    read_at = Column(DateTime, nullable=True)

    conversation = relationship("Conversation", back_populates="messages")


class ChatAttachment(Base):
    __tablename__ = "chat_attachments"

    id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_id = Column(String(255), nullable=False, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=True, index=True)
    filename = Column(String(255), nullable=False)
    relative_path = Column(String(1000), nullable=False)
    content_type = Column(String(255), nullable=False, default="application/octet-stream")
    extension = Column(String(32), nullable=False, default="")
    kind = Column(String(30), nullable=False, default="text")
    file_size = Column(Integer, nullable=False, default=0)
    checksum = Column(String(128), nullable=False, default="")
    extracted_text = Column(Text, nullable=False, default="")
    vision_description = Column(Text, nullable=False, default="")
    vision_model = Column(String(255), nullable=False, default="")
    vision_updated_at = Column(DateTime, nullable=True)
    is_truncated = Column(Boolean, nullable=False, default=False)
    status = Column(String(30), nullable=False, default="ready", index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    attached_at = Column(DateTime, nullable=True)


class ChatJob(Base):
    __tablename__ = "chat_jobs"
    __table_args__ = (
        Index("uq_chat_jobs_user_client_request", "user_id", "client_request_id", unique=True),
    )

    id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    client_request_id = Column(String(64), nullable=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, index=True)
    user_message_id = Column(Integer, ForeignKey("messages.id"), nullable=False)
    assistant_message_id = Column(Integer, ForeignKey("messages.id"), nullable=False)
    provider_id = Column(String(100), default="")
    provider_name = Column(String(255), default="")
    model_id = Column(String(150), default="")
    model_name = Column(String(255), default="")
    response_mode = Column(String(30), nullable=False, default="normal")
    reasoning_effort = Column(String(30), nullable=False, default="low")
    use_rag = Column(Boolean, nullable=False, default=False)
    status = Column(String(30), nullable=False, default="queued", index=True)
    last_event_id = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error = Column(Text, default="")


class ChatJobEvent(Base):
    __tablename__ = "chat_job_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(64), ForeignKey("chat_jobs.id"), nullable=False, index=True)
    type = Column(String(40), nullable=False, index=True)
    payload = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ScheduledAgentTask(Base):
    __tablename__ = "scheduled_agent_tasks"

    id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_id = Column(String(255), nullable=False, default="")
    prompt = Column(Text, nullable=False)
    run_at = Column(DateTime, nullable=False, index=True)
    status = Column(String(30), nullable=False, default="scheduled", index=True)
    job_id = Column(String(64), nullable=False, default="")
    error = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    filename = Column(String(255), nullable=False)
    source = Column(String(255), default="upload")
    upload_path = Column(String(1000), default="")
    checksum = Column(String(128), default="")
    status = Column(String(60), default="indexed")
    parser = Column(String(80), default="")
    error_message = Column(Text, default="")
    vector_ids_json = Column(Text, default="[]")
    manifest_path = Column(String(1000), default="")
    extracted_path = Column(String(1000), default="")
    chunk_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    file_size = Column(Integer, default=0)


class Skill(Base):
    __tablename__ = "skills"

    id = Column(Integer, primary_key=True)
    name = Column(String(120), unique=True, nullable=False, index=True)
    description = Column(Text, default="")
    kind = Column(String(50), default="knowledge")
    definition_json = Column(Text, default="{}")
    requires_network = Column(Boolean, default=False)
    requires_shell = Column(Boolean, default=False)
    risk_level = Column(Integer, default=1)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class UserSkill(Base):
    __tablename__ = "user_skills"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    skill_id = Column(Integer, ForeignKey("skills.id"), nullable=False, index=True)
    is_enabled = Column(Boolean, default=True)
    config_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    skill = relationship("Skill")


class SkillRun(Base):
    __tablename__ = "skill_runs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    skill_name = Column(String(120), nullable=False, index=True)
    status = Column(String(40), nullable=False, default="completed")
    input_json = Column(Text, default="{}")
    output_summary = Column(Text, default="")
    error_message = Column(Text, default="")
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime, nullable=True)


def get_engine():
    return create_engine(settings.database_url, echo=False)


def _sqlite_columns(conn, table: str) -> set[str]:
    return {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}


def init_db():
    import os

    db_path = settings.database_url.replace("sqlite:///", "")
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    engine = get_engine()
    Base.metadata.create_all(engine)

    if settings.database_url.startswith("sqlite"):
        with engine.begin() as conn:
            user_cols = _sqlite_columns(conn, "users")
            for name, ddl in {
                "registration_status": "ALTER TABLE users ADD COLUMN registration_status VARCHAR(20) NOT NULL DEFAULT 'approved'",
                "approved_at": "ALTER TABLE users ADD COLUMN approved_at DATETIME",
                "approved_by": "ALTER TABLE users ADD COLUMN approved_by INTEGER",
            }.items():
                if name not in user_cols:
                    conn.execute(text(ddl))

            message_cols = _sqlite_columns(conn, "messages")
            for name, ddl in {
                "provider_id": "ALTER TABLE messages ADD COLUMN provider_id VARCHAR(100)",
                "provider_name": "ALTER TABLE messages ADD COLUMN provider_name VARCHAR(255)",
                "model_id": "ALTER TABLE messages ADD COLUMN model_id VARCHAR(150)",
                "model_name": "ALTER TABLE messages ADD COLUMN model_name VARCHAR(255)",
                "user_id": "ALTER TABLE messages ADD COLUMN user_id INTEGER",
                "reasoning": "ALTER TABLE messages ADD COLUMN reasoning TEXT NOT NULL DEFAULT ''",
                "skill_activities_json": "ALTER TABLE messages ADD COLUMN skill_activities_json TEXT NOT NULL DEFAULT '[]'",
                "attachments_json": "ALTER TABLE messages ADD COLUMN attachments_json TEXT NOT NULL DEFAULT '[]'",
                "job_id": "ALTER TABLE messages ADD COLUMN job_id VARCHAR(64)",
                "status": "ALTER TABLE messages ADD COLUMN status VARCHAR(30) NOT NULL DEFAULT 'completed'",
                "read_at": "ALTER TABLE messages ADD COLUMN read_at DATETIME",
            }.items():
                if name not in message_cols:
                    conn.execute(text(ddl))

            conversation_cols = _sqlite_columns(conn, "conversations")
            if "user_id" not in conversation_cols:
                conn.execute(text("ALTER TABLE conversations ADD COLUMN user_id INTEGER"))

            chat_job_cols = _sqlite_columns(conn, "chat_jobs")
            if "client_request_id" not in chat_job_cols:
                conn.execute(text("ALTER TABLE chat_jobs ADD COLUMN client_request_id VARCHAR(64)"))
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_jobs_user_client_request "
                "ON chat_jobs (user_id, client_request_id)"
            ))

            attachment_cols = _sqlite_columns(conn, "chat_attachments")
            for name, ddl in {
                "vision_description": "ALTER TABLE chat_attachments ADD COLUMN vision_description TEXT NOT NULL DEFAULT ''",
                "vision_model": "ALTER TABLE chat_attachments ADD COLUMN vision_model VARCHAR(255) NOT NULL DEFAULT ''",
                "vision_updated_at": "ALTER TABLE chat_attachments ADD COLUMN vision_updated_at DATETIME",
            }.items():
                if name not in attachment_cols:
                    conn.execute(text(ddl))

            document_cols = _sqlite_columns(conn, "knowledge_documents")
            for name, ddl in {
                "user_id": "ALTER TABLE knowledge_documents ADD COLUMN user_id INTEGER",
                "upload_path": "ALTER TABLE knowledge_documents ADD COLUMN upload_path VARCHAR(1000) DEFAULT ''",
                "checksum": "ALTER TABLE knowledge_documents ADD COLUMN checksum VARCHAR(128) DEFAULT ''",
                "status": "ALTER TABLE knowledge_documents ADD COLUMN status VARCHAR(60) DEFAULT 'indexed'",
                "parser": "ALTER TABLE knowledge_documents ADD COLUMN parser VARCHAR(80) DEFAULT ''",
                "error_message": "ALTER TABLE knowledge_documents ADD COLUMN error_message TEXT DEFAULT ''",
                "vector_ids_json": "ALTER TABLE knowledge_documents ADD COLUMN vector_ids_json TEXT DEFAULT '[]'",
                "manifest_path": "ALTER TABLE knowledge_documents ADD COLUMN manifest_path VARCHAR(1000) DEFAULT ''",
                "extracted_path": "ALTER TABLE knowledge_documents ADD COLUMN extracted_path VARCHAR(1000) DEFAULT ''",
            }.items():
                if name not in document_cols:
                    conn.execute(text(ddl))

            if "skill_runs" not in {
                row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            }:
                SkillRun.__table__.create(bind=conn)

            if "user_preferences" not in {
                row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            }:
                UserPreference.__table__.create(bind=conn)

            if "preference_suggestions" not in {
                row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            }:
                PreferenceSuggestion.__table__.create(bind=conn)

            if "user_provider_configs" not in {
                row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            }:
                UserProviderConfig.__table__.create(bind=conn)

            conn.execute(text("""
                UPDATE conversations
                SET messages_count = (
                    SELECT COUNT(*) FROM messages WHERE messages.conversation_id = conversations.id
                )
            """))
            conn.execute(text("""
                UPDATE conversations
                SET title = COALESCE((
                    SELECT substr(content, 1, 60)
                    FROM messages
                    WHERE messages.conversation_id = conversations.id AND role = 'user'
                    ORDER BY created_at ASC
                    LIMIT 1
                ), title)
                WHERE title LIKE 'Conversa %'
            """))


def get_session_db():
    engine = get_engine()
    return Session(engine)
