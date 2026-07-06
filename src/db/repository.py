"""Repositório para acesso a dados."""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import func

from src.db.models import get_session_db, Conversation, Message, KnowledgeDocument


class ConversationRepo:
    @staticmethod
    def get_or_create(session_id: str) -> Conversation:
        db = get_session_db()
        try:
            conv = db.query(Conversation).filter(Conversation.session_id == session_id).first()
            if not conv:
                conv = Conversation(session_id=session_id, title=f"Conversa {session_id[:8]}")
                db.add(conv)
                db.commit()
                db.refresh(conv)
            return conv
        finally:
            db.close()

    @staticmethod
    def get_by_session(session_id: str) -> Optional[Conversation]:
        db = get_session_db()
        try:
            return db.query(Conversation).filter(Conversation.session_id == session_id).first()
        finally:
            db.close()

    @staticmethod
    def list_all() -> list[Conversation]:
        db = get_session_db()
        try:
            return db.query(Conversation).order_by(Conversation.updated_at.desc()).limit(50).all()
        finally:
            db.close()

    @staticmethod
    def rename(session_id: str, title: str) -> bool:
        db = get_session_db()
        try:
            conv = db.query(Conversation).filter(Conversation.session_id == session_id).first()
            if not conv:
                return False
            conv.title = title
            db.commit()
            return True
        finally:
            db.close()

    @staticmethod
    def delete(session_id: str) -> bool:
        db = get_session_db()
        try:
            conv = db.query(Conversation).filter(Conversation.session_id == session_id).first()
            if not conv:
                return False
            db.delete(conv)
            db.commit()
            return True
        finally:
            db.close()

    @staticmethod
    def add_message(
        session_id: str,
        role: str,
        content: str,
        tokens: int = 0,
        provider_id: str | None = None,
        provider_name: str | None = None,
        model_id: str | None = None,
        model_name: str | None = None,
    ) -> Message:
        db = get_session_db()
        try:
            conv = db.query(Conversation).filter(Conversation.session_id == session_id).first()
            if not conv:
                conv = Conversation(session_id=session_id, title=f"Conversa {session_id[:8]}")
                db.add(conv)
                db.flush()

            msg = Message(
                conversation_id=conv.id,
                role=role,
                content=content,
                tokens_used=tokens,
                provider_id=provider_id,
                provider_name=provider_name,
                model_id=model_id,
                model_name=model_name,
            )
            conv.messages_count = (conv.messages_count or 0) + 1
            conv.updated_at = datetime.now(timezone.utc)
            # Auto-titulo baseado na primeira mensagem do usuário
            if conv.messages_count == 1 and role == "user":
                conv.title = content[:60] + ("..." if len(content) > 60 else "")
            db.add(msg)
            db.commit()
            db.refresh(msg)
            return msg
        finally:
            db.close()

    @staticmethod
    def get_history(session_id: str, limit: int = 50) -> list[Message]:
        db = get_session_db()
        try:
            conv = db.query(Conversation).filter(Conversation.session_id == session_id).first()
            if not conv:
                return []
            return (
                db.query(Message)
                .filter(Message.conversation_id == conv.id)
                .order_by(Message.created_at.asc())
                .limit(limit)
                .all()
            )
        finally:
            db.close()

    @staticmethod
    def set_feedback(message_id: int, score: int) -> bool:
        db = get_session_db()
        try:
            msg = db.query(Message).filter(Message.id == message_id).first()
            if not msg:
                return False
            msg.feedback_score = score
            db.commit()
            return True
        finally:
            db.close()

    @staticmethod
    def set_language(session_id: str, lang: str) -> None:
        db = get_session_db()
        try:
            conv = ConversationRepo.get_or_create(session_id)
            conv.language = lang
            db.commit()
        finally:
            db.close()

    @staticmethod
    def get_stats() -> dict:
        db = get_session_db()
        try:
            total_msgs = db.query(func.count(Message.id)).scalar() or 0
            total_convs = db.query(func.count(Conversation.id)).scalar() or 0
            likes = db.query(func.count(Message.id)).filter(Message.feedback_score == 1).scalar() or 0
            dislikes = db.query(func.count(Message.id)).filter(Message.feedback_score == -1).scalar() or 0
            return {
                "total_messages": total_msgs,
                "total_conversations": total_convs,
                "likes": likes,
                "dislikes": dislikes,
            }
        finally:
            db.close()


class MessageRepo:
    @staticmethod
    def update_content(message_id: int, content: str) -> Optional[Message]:
        db = get_session_db()
        try:
            msg = db.query(Message).filter(Message.id == message_id).first()
            if not msg:
                return None
            msg.content = content
            db.commit()
            return msg
        finally:
            db.close()


class DocumentRepo:
    @staticmethod
    def save(filename: str, source: str, chunk_count: int, file_size: int) -> KnowledgeDocument:
        db = get_session_db()
        try:
            doc = KnowledgeDocument(
                filename=filename,
                source=source,
                chunk_count=chunk_count,
                file_size=file_size,
            )
            db.add(doc)
            db.commit()
            db.refresh(doc)
            return doc
        finally:
            db.close()

    @staticmethod
    def list_all() -> list[KnowledgeDocument]:
        db = get_session_db()
        try:
            return db.query(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc()).all()
        finally:
            db.close()

    @staticmethod
    def delete(doc_id: int) -> bool:
        db = get_session_db()
        try:
            doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == doc_id).first()
            if not doc:
                return False
            db.delete(doc)
            db.commit()
            return True
        finally:
            db.close()
