"""SQLAlchemy models and lightweight SQLite migrations."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, create_engine, text
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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    feedback_score = Column(Integer, nullable=True)
    tokens_used = Column(Integer, default=0)
    moderated = Column(Boolean, default=False)
    provider_id = Column(String(100), nullable=True)
    provider_name = Column(String(255), nullable=True)
    model_id = Column(String(150), nullable=True)
    model_name = Column(String(255), nullable=True)

    conversation = relationship("Conversation", back_populates="messages")


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    filename = Column(String(255), nullable=False)
    source = Column(String(255), default="upload")
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
            message_cols = _sqlite_columns(conn, "messages")
            for name, ddl in {
                "provider_id": "ALTER TABLE messages ADD COLUMN provider_id VARCHAR(100)",
                "provider_name": "ALTER TABLE messages ADD COLUMN provider_name VARCHAR(255)",
                "model_id": "ALTER TABLE messages ADD COLUMN model_id VARCHAR(150)",
                "model_name": "ALTER TABLE messages ADD COLUMN model_name VARCHAR(255)",
                "user_id": "ALTER TABLE messages ADD COLUMN user_id INTEGER",
            }.items():
                if name not in message_cols:
                    conn.execute(text(ddl))

            conversation_cols = _sqlite_columns(conn, "conversations")
            if "user_id" not in conversation_cols:
                conn.execute(text("ALTER TABLE conversations ADD COLUMN user_id INTEGER"))

            document_cols = _sqlite_columns(conn, "knowledge_documents")
            if "user_id" not in document_cols:
                conn.execute(text("ALTER TABLE knowledge_documents ADD COLUMN user_id INTEGER"))

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
