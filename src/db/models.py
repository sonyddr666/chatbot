"""Modelos SQLAlchemy para persistência."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime, ForeignKey, create_engine, text
from sqlalchemy.orm import DeclarativeBase, relationship, Session

from src.config import settings


class Base(DeclarativeBase):
    pass


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True)
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
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    feedback_score = Column(Integer, nullable=True)  # 1 (like) ou -1 (dislike)
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
    filename = Column(String(255), nullable=False)
    source = Column(String(255), default="upload")
    chunk_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    file_size = Column(Integer, default=0)


def get_engine():
    """Retorna engine SQLAlchemy."""
    return create_engine(settings.database_url, echo=False)


def init_db():
    """Cria todas as tabelas e aplica migração simples para SQLite existente."""
    import os
    db_path = settings.database_url.replace("sqlite:///", "")
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    engine = get_engine()
    Base.metadata.create_all(engine)

    # Migração leve: adiciona metadata de provider/model em bancos antigos.
    if settings.database_url.startswith("sqlite"):
        with engine.begin() as conn:
            cols = {row[1] for row in conn.execute(text("PRAGMA table_info(messages)"))}
            for name, ddl in {
                "provider_id": "ALTER TABLE messages ADD COLUMN provider_id VARCHAR(100)",
                "provider_name": "ALTER TABLE messages ADD COLUMN provider_name VARCHAR(255)",
                "model_id": "ALTER TABLE messages ADD COLUMN model_id VARCHAR(150)",
                "model_name": "ALTER TABLE messages ADD COLUMN model_name VARCHAR(255)",
            }.items():
                if name not in cols:
                    conn.execute(text(ddl))

            # Repara contadores quebrados por versões antigas do repo.
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
    """Retorna uma sessão do banco."""
    engine = get_engine()
    return Session(engine)
