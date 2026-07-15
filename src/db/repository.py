"""Repository helpers for persistence."""

from datetime import datetime, timezone
from typing import Optional
import json
import re
from uuid import uuid4
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError

from src.core.auth import hash_password, verify_password
from src.core.userspace import ensure_user_space, safe_user_path
from src.core.time_utils import utc_isoformat
from src.core.skill_registry import DEFAULT_SKILLS
from src.db.models import (
    get_session_db,
    Conversation,
    Message,
    KnowledgeDocument,
    User,
    UserProfile,
    UserPreference,
    PreferenceSuggestion,
    Skill,
    UserSkill,
    SkillRun,
    ChatAttachment,
    ChatJob,
    ChatJobEvent,
    ScheduledAgentTask,
)


class UserRepo:
    @staticmethod
    def ensure_initial_admin() -> Optional[User]:
        """Create the configured bootstrap admin once, without resetting it later."""
        from src.config import settings

        email = settings.initial_admin_email.strip().lower()
        username = settings.initial_admin_username.strip()
        password = settings.initial_admin_password
        configured = (email, username, password)
        if not any(configured):
            return None
        if not all(configured):
            raise RuntimeError(
                "INITIAL_ADMIN_EMAIL, INITIAL_ADMIN_USERNAME e INITIAL_ADMIN_PASSWORD "
                "devem ser definidos juntos"
            )
        if len(password) < 12:
            raise RuntimeError("INITIAL_ADMIN_PASSWORD deve ter pelo menos 12 caracteres")

        db = get_session_db()
        try:
            user = (
                db.query(User)
                .filter(or_(User.email == email, User.username == username))
                .first()
            )
            if not user:
                user = User(
                    email=email,
                    username=username,
                    display_name=username,
                    password_hash=hash_password(password),
                    is_admin=True,
                    is_active=True,
                    registration_status="approved",
                    approved_at=datetime.now(timezone.utc),
                )
                db.add(user)
                db.flush()
                db.add(UserProfile(user_id=user.id, language="pt", preferred_tone="direto"))
                db.commit()
                db.refresh(user)
            elif user.email != email or user.username != username or not user.is_admin:
                raise RuntimeError(
                    "As credenciais do administrador inicial conflitam com um usuario existente"
                )
            else:
                user.is_active = True
                user.registration_status = "approved"
                if not user.approved_at:
                    user.approved_at = datetime.now(timezone.utc)
                db.commit()
            ensure_user_space(user.id)
            return user
        finally:
            db.close()

    @staticmethod
    def create_user(email: str, username: str, password: str, display_name: str = "") -> User:
        db = get_session_db()
        try:
            existing = db.query(User).filter(or_(User.email == email, User.username == username)).first()
            if existing:
                raise ValueError("Email ou username ja cadastrado")
            user = User(
                email=email.strip().lower(),
                username=username.strip(),
                display_name=display_name.strip() or username.strip(),
                password_hash=hash_password(password),
                is_active=True,
                registration_status="approved",
                approved_at=datetime.now(timezone.utc),
            )
            db.add(user)
            db.flush()
            ensure_user_space(user.id)
            db.add(UserProfile(user_id=user.id, language="pt", preferred_tone="direto"))
            db.commit()
            db.refresh(user)
            return user
        finally:
            db.close()

    @staticmethod
    def create_registration_request(email: str, username: str, password: str, display_name: str = "") -> User:
        normalized_email = email.strip().lower()
        normalized_username = username.strip().lower()
        if len(normalized_email) > 255 or "@" not in normalized_email or any(ch.isspace() for ch in normalized_email):
            raise ValueError("Email invalido")
        if not re.fullmatch(r"[a-z0-9_.-]{3,100}", normalized_username):
            raise ValueError("Usuario deve ter 3 a 100 caracteres: letras, numeros, ponto, traco ou sublinhado")

        db = get_session_db()
        try:
            existing = (
                db.query(User)
                .filter(
                    or_(
                        func.lower(User.email) == normalized_email,
                        func.lower(User.username) == normalized_username,
                    )
                )
                .first()
            )
            if existing:
                if existing.registration_status == "pending":
                    raise ValueError("Email ou usuario ja possui solicitacao aguardando aprovacao")
                raise ValueError("Email ou usuario ja cadastrado")
            user = User(
                email=normalized_email,
                username=normalized_username,
                display_name=display_name.strip() or normalized_username,
                password_hash=hash_password(password),
                is_active=False,
                is_admin=False,
                registration_status="pending",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            db.expunge(user)
            return user
        except IntegrityError as exc:
            db.rollback()
            raise ValueError("Email ou usuario ja cadastrado") from exc
        finally:
            db.close()

    @staticmethod
    def authenticate_with_status(login: str, password: str) -> tuple[Optional[User], str]:
        normalized_login = login.strip()
        db = get_session_db()
        try:
            user = (
                db.query(User)
                .filter(
                    or_(
                        func.lower(User.email) == normalized_login.lower(),
                        func.lower(User.username) == normalized_login.lower(),
                    )
                )
                .first()
            )
            if not user or not verify_password(password, user.password_hash):
                return None, "invalid"
            status = user.registration_status or "approved"
            if status != "approved" or not user.is_active:
                return None, status
            db.expunge(user)
            return user, "approved"
        finally:
            db.close()

    @staticmethod
    def authenticate(login: str, password: str) -> Optional[User]:
        user, _ = UserRepo.authenticate_with_status(login, password)
        return user

    @staticmethod
    def get(user_id: int) -> Optional[User]:
        db = get_session_db()
        try:
            user = db.query(User).filter(
                User.id == user_id,
                User.is_active == True,
                User.registration_status == "approved",
            ).first()
            if user:
                db.expunge(user)
            return user
        finally:
            db.close()

    @staticmethod
    def list_for_admin(status: str | None = None) -> list[User]:
        db = get_session_db()
        try:
            query = db.query(User)
            if status and status != "all":
                query = query.filter(User.registration_status == status)
            users = query.order_by(User.created_at.desc(), User.id.desc()).all()
            for user in users:
                db.expunge(user)
            return users
        finally:
            db.close()

    @staticmethod
    def approve_registration(user_id: int, admin_id: int) -> User:
        db = get_session_db()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                raise ValueError("Usuario nao encontrado")
            if user.is_admin:
                raise ValueError("Conta administrativa nao pode ser alterada por este fluxo")
            user.registration_status = "approved"
            user.is_active = True
            user.approved_by = admin_id
            user.approved_at = datetime.now(timezone.utc)
            if not user.profile:
                db.add(UserProfile(user_id=user.id, language="pt", preferred_tone="direto"))
            db.commit()
            db.refresh(user)
            ensure_user_space(user.id)
            db.expunge(user)
            return user
        finally:
            db.close()

    @staticmethod
    def reject_registration(user_id: int) -> User:
        db = get_session_db()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                raise ValueError("Usuario nao encontrado")
            if user.is_admin or user.registration_status == "approved":
                raise ValueError("Somente solicitacoes pendentes podem ser rejeitadas")
            user.registration_status = "rejected"
            user.is_active = False
            db.commit()
            db.refresh(user)
            db.expunge(user)
            return user
        finally:
            db.close()

    @staticmethod
    def delete_registration(user_id: int) -> bool:
        db = get_session_db()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return False
            if user.is_admin or user.registration_status == "approved":
                raise ValueError("Somente solicitacoes pendentes ou rejeitadas podem ser excluidas")
            db.delete(user)
            db.commit()
            return True
        finally:
            db.close()

    @staticmethod
    def get_profile(user_id: int) -> Optional[UserProfile]:
        db = get_session_db()
        try:
            profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
            if profile:
                db.expunge(profile)
            return profile
        finally:
            db.close()

    @staticmethod
    def update_profile(user_id: int, data: dict) -> UserProfile:
        db = get_session_db()
        try:
            profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
            if not profile:
                profile = UserProfile(user_id=user_id)
                db.add(profile)
                db.flush()
            for key in ("language", "timezone", "role", "technical_level", "preferred_tone", "memory_policy"):
                if key in data and data[key] is not None:
                    setattr(profile, key, str(data[key]))
            if "goals" in data:
                profile.goals_json = json.dumps(data.get("goals") or [], ensure_ascii=False)
            if "avoid" in data:
                profile.avoid_json = json.dumps(data.get("avoid") or [], ensure_ascii=False)
            profile.onboarding_json = json.dumps(data, ensure_ascii=False)
            profile.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(profile)
            db.expunge(profile)
            return profile
        finally:
            db.close()


class UserPreferenceRepo:
    DEFAULTS = {
        "answer_style": {"tone": "direto", "detail": "pratico"},
        "default_language": "pt",
        "rag_aggressiveness": "balanced",
    }

    @staticmethod
    def ensure_defaults(user_id: int) -> None:
        db = get_session_db()
        try:
            existing = {
                row.key
                for row in db.query(UserPreference).filter(UserPreference.user_id == user_id).all()
            }
            for key, value in UserPreferenceRepo.DEFAULTS.items():
                if key not in existing:
                    db.add(UserPreference(
                        user_id=user_id,
                        key=key,
                        value_json=json.dumps(value, ensure_ascii=False),
                        source="default",
                        confidence=100,
                    ))
            db.commit()
        finally:
            db.close()

    @staticmethod
    def set(
        user_id: int,
        key: str,
        value,
        source: str = "manual",
        confidence: float = 1.0,
    ) -> UserPreference:
        clean_key = key.strip()
        if not clean_key:
            raise ValueError("Chave de preferencia invalida")
        db = get_session_db()
        try:
            pref = (
                db.query(UserPreference)
                .filter(UserPreference.user_id == user_id, UserPreference.key == clean_key)
                .first()
            )
            if not pref:
                pref = UserPreference(user_id=user_id, key=clean_key)
                db.add(pref)
            pref.value_json = json.dumps(value, ensure_ascii=False)
            pref.source = source
            pref.confidence = max(0, min(100, int(confidence * 100)))
            pref.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(pref)
            db.expunge(pref)
            return pref
        finally:
            db.close()

    @staticmethod
    def list_for_user(user_id: int) -> dict:
        UserPreferenceRepo.ensure_defaults(user_id)
        db = get_session_db()
        try:
            rows = (
                db.query(UserPreference)
                .filter(UserPreference.user_id == user_id)
                .order_by(UserPreference.key.asc())
                .all()
            )
            return {
                row.key: {
                    "value": json.loads(row.value_json or "null"),
                    "source": row.source,
                    "confidence": row.confidence / 100,
                    "updated_at": utc_isoformat(row.updated_at) if row.updated_at else None,
                }
                for row in rows
            }
        finally:
            db.close()

    @staticmethod
    def prompt_context_for_user(user_id: int) -> str:
        preferences = UserPreferenceRepo.list_for_user(user_id)
        if not preferences:
            return ""

        lines = ["Preferencias pessoais do usuario:"]
        for key in sorted(preferences):
            info = preferences[key]
            value = json.dumps(info.get("value"), ensure_ascii=False, sort_keys=True)
            source = info.get("source", "manual")
            confidence = info.get("confidence", 1)
            lines.append(f"- {key}: {value} (fonte={source}, confianca={confidence})")
        return "\n".join(lines)


class PreferenceSuggestionRepo:
    @staticmethod
    def _to_dict(row: PreferenceSuggestion) -> dict:
        return {
            "id": row.id,
            "user_id": row.user_id,
            "suggestion_type": row.suggestion_type,
            "current_value": json.loads(row.current_value_json or "null"),
            "suggested_value": json.loads(row.suggested_value_json or "null"),
            "reason": row.reason,
            "confidence": row.confidence / 100,
            "status": row.status,
            "created_at": utc_isoformat(row.created_at) if row.created_at else None,
            "resolved_at": utc_isoformat(row.resolved_at) if row.resolved_at else None,
        }

    @staticmethod
    def create(
        user_id: int,
        suggestion_type: str,
        current_value,
        suggested_value,
        reason: str,
        confidence: float = 0.7,
    ) -> PreferenceSuggestion:
        clean_type = suggestion_type.strip()
        if not clean_type:
            raise ValueError("Tipo de sugestao invalido")
        db = get_session_db()
        try:
            suggestion = PreferenceSuggestion(
                user_id=user_id,
                suggestion_type=clean_type,
                current_value_json=json.dumps(current_value, ensure_ascii=False),
                suggested_value_json=json.dumps(suggested_value, ensure_ascii=False),
                reason=reason[:1000],
                confidence=max(0, min(100, int(confidence * 100))),
                status="pending",
            )
            db.add(suggestion)
            db.commit()
            db.refresh(suggestion)
            db.expunge(suggestion)
            return suggestion
        finally:
            db.close()

    @staticmethod
    def has_pending(user_id: int, suggestion_type: str) -> bool:
        db = get_session_db()
        try:
            return (
                db.query(PreferenceSuggestion)
                .filter(
                    PreferenceSuggestion.user_id == user_id,
                    PreferenceSuggestion.suggestion_type == suggestion_type,
                    PreferenceSuggestion.status == "pending",
                )
                .first()
                is not None
            )
        finally:
            db.close()

    @staticmethod
    def list_pending(user_id: int, limit: int = 20) -> list[dict]:
        db = get_session_db()
        try:
            rows = (
                db.query(PreferenceSuggestion)
                .filter(
                    PreferenceSuggestion.user_id == user_id,
                    PreferenceSuggestion.status == "pending",
                )
                .order_by(PreferenceSuggestion.created_at.desc(), PreferenceSuggestion.id.desc())
                .limit(limit)
                .all()
            )
            return [PreferenceSuggestionRepo._to_dict(row) for row in rows]
        finally:
            db.close()

    @staticmethod
    def resolve(user_id: int, suggestion_id: int, accept: bool) -> bool:
        db = get_session_db()
        try:
            suggestion = (
                db.query(PreferenceSuggestion)
                .filter(
                    PreferenceSuggestion.id == suggestion_id,
                    PreferenceSuggestion.user_id == user_id,
                    PreferenceSuggestion.status == "pending",
                )
                .first()
            )
            if not suggestion:
                return False
            suggestion.status = "accepted" if accept else "rejected"
            suggestion.resolved_at = datetime.now(timezone.utc)
            suggested_value = json.loads(suggestion.suggested_value_json or "null")
            suggestion_type = suggestion.suggestion_type
            confidence = suggestion.confidence / 100
            db.commit()
        finally:
            db.close()

        if accept:
            UserPreferenceRepo.set(
                user_id,
                suggestion_type,
                suggested_value,
                source="suggestion",
                confidence=confidence,
            )
        return True


class ConversationRepo:
    @staticmethod
    def get_or_create(session_id: str, user_id: int | None = None) -> Conversation:
        db = get_session_db()
        try:
            query = db.query(Conversation).filter(Conversation.session_id == session_id)
            if user_id is not None:
                query = query.filter(Conversation.user_id == user_id)
            conv = query.first()
            if not conv:
                conv = Conversation(session_id=session_id, user_id=user_id, title=f"Conversa {session_id[:8]}")
                db.add(conv)
                db.commit()
                db.refresh(conv)
            return conv
        finally:
            db.close()

    @staticmethod
    def get_by_session(session_id: str, user_id: int | None = None) -> Optional[Conversation]:
        db = get_session_db()
        try:
            query = db.query(Conversation).filter(Conversation.session_id == session_id)
            if user_id is not None:
                query = query.filter(Conversation.user_id == user_id)
            conv = query.first()
            if conv:
                db.expunge(conv)
            return conv
        finally:
            db.close()

    @staticmethod
    def list_all(user_id: int | None = None) -> list[Conversation]:
        db = get_session_db()
        try:
            query = db.query(Conversation)
            if user_id is not None:
                query = query.filter(Conversation.user_id == user_id)
            convs = query.order_by(Conversation.updated_at.desc()).limit(50).all()
            for conv in convs:
                db.expunge(conv)
            return convs
        finally:
            db.close()

    @staticmethod
    def activity_for_user(user_id: int, conversation_ids: list[int]) -> dict[int, dict]:
        """Return the latest persisted job state for each visible conversation."""
        if not conversation_ids:
            return {}
        db = get_session_db()
        try:
            jobs = db.query(ChatJob).filter(
                ChatJob.user_id == user_id,
                ChatJob.conversation_id.in_(conversation_ids),
            ).order_by(ChatJob.created_at.desc(), ChatJob.id.desc()).all()
            latest: dict[int, ChatJob] = {}
            for job in jobs:
                latest.setdefault(int(job.conversation_id), job)
            message_ids = [job.assistant_message_id for job in latest.values()]
            messages = db.query(Message).filter(Message.id.in_(message_ids)).all() if message_ids else []
            by_message_id = {message.id: message for message in messages}
            return {
                conversation_id: {
                    "job_status": job.status,
                    "has_unread_response": bool(
                        job.status == "completed"
                        and (message := by_message_id.get(job.assistant_message_id)) is not None
                        and message.read_at is None
                    ),
                }
                for conversation_id, job in latest.items()
            }
        finally:
            db.close()

    @staticmethod
    def export_for_user(user_id: int, session_id: str | None = None) -> list[dict]:
        """Return every persisted message owned by a user, without the UI history limits."""
        db = get_session_db()
        try:
            query = db.query(Conversation).filter(Conversation.user_id == user_id)
            if session_id:
                query = query.filter(Conversation.session_id == session_id)
            conversations = query.order_by(Conversation.created_at.asc(), Conversation.id.asc()).all()
            exported: list[dict] = []
            for conversation in conversations:
                messages = (
                    db.query(Message)
                    .filter(Message.conversation_id == conversation.id)
                    .order_by(Message.created_at.asc(), Message.id.asc())
                    .all()
                )
                exported.append({
                    "session_id": conversation.session_id,
                    "title": conversation.title,
                    "created_at": utc_isoformat(conversation.created_at) if conversation.created_at else None,
                    "updated_at": utc_isoformat(conversation.updated_at) if conversation.updated_at else None,
                    "messages": [
                        {
                            "id": message.id,
                            "role": message.role,
                            "content": message.content,
                            "reasoning": message.reasoning or "",
                            "skill_activities_json": message.skill_activities_json or "[]",
                            "attachments_json": message.attachments_json or "[]",
                            "created_at": utc_isoformat(message.created_at) if message.created_at else None,
                            "provider_name": message.provider_name or "",
                            "model_name": message.model_name or "",
                        }
                        for message in messages
                    ],
                })
            return exported
        finally:
            db.close()

    @staticmethod
    def rename(session_id: str, title: str, user_id: int | None = None) -> bool:
        db = get_session_db()
        try:
            query = db.query(Conversation).filter(Conversation.session_id == session_id)
            if user_id is not None:
                query = query.filter(Conversation.user_id == user_id)
            conv = query.first()
            if not conv:
                return False
            conv.title = title
            db.commit()
            return True
        finally:
            db.close()

    @staticmethod
    def delete(session_id: str, user_id: int | None = None) -> bool:
        db = get_session_db()
        try:
            query = db.query(Conversation).filter(Conversation.session_id == session_id)
            if user_id is not None:
                query = query.filter(Conversation.user_id == user_id)
            conv = query.first()
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
        user_id: int | None = None,
        reasoning: str = "",
        skill_activities: list[dict] | None = None,
    ) -> Message:
        db = get_session_db()
        try:
            query = db.query(Conversation).filter(Conversation.session_id == session_id)
            if user_id is not None:
                query = query.filter(Conversation.user_id == user_id)
            conv = query.first()
            if not conv:
                conv = Conversation(session_id=session_id, user_id=user_id, title=f"Conversa {session_id[:8]}")
                db.add(conv)
                db.flush()

            msg = Message(
                conversation_id=conv.id,
                user_id=user_id,
                role=role,
                content=content,
                reasoning=reasoning or "",
                skill_activities_json=json.dumps(skill_activities or [], ensure_ascii=False),
                tokens_used=tokens,
                provider_id=provider_id,
                provider_name=provider_name,
                model_id=model_id,
                model_name=model_name,
            )
            conv.messages_count = (conv.messages_count or 0) + 1
            conv.updated_at = datetime.now(timezone.utc)
            if conv.messages_count == 1 and role == "user":
                conv.title = content[:60] + ("..." if len(content) > 60 else "")
            db.add(msg)
            db.commit()
            db.refresh(msg)
            db.expunge(msg)
            return msg
        finally:
            db.close()

    @staticmethod
    def get_history(session_id: str, limit: int = 50, user_id: int | None = None) -> list[Message]:
        db = get_session_db()
        try:
            query = db.query(Conversation).filter(Conversation.session_id == session_id)
            if user_id is not None:
                query = query.filter(Conversation.user_id == user_id)
            conv = query.first()
            if not conv:
                return []
            messages = (
                db.query(Message)
                .filter(Message.conversation_id == conv.id)
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(limit)
                .all()
            )
            for msg in messages:
                db.expunge(msg)
            return list(reversed(messages))
        finally:
            db.close()

    @staticmethod
    def set_feedback(message_id: int, score: int, user_id: int | None = None) -> bool:
        db = get_session_db()
        try:
            query = db.query(Message).filter(Message.id == message_id)
            if user_id is not None:
                query = query.filter(Message.user_id == user_id)
            msg = query.first()
            if not msg:
                return False
            msg.feedback_score = score
            db.commit()
            return True
        finally:
            db.close()

    @staticmethod
    def set_language(session_id: str, lang: str, user_id: int | None = None) -> None:
        db = get_session_db()
        try:
            query = db.query(Conversation).filter(Conversation.session_id == session_id)
            if user_id is not None:
                query = query.filter(Conversation.user_id == user_id)
            conv = query.first()
            if not conv:
                conv = Conversation(session_id=session_id, user_id=user_id, title=f"Conversa {session_id[:8]}")
                db.add(conv)
                db.flush()
            conv.language = lang
            conv.updated_at = datetime.now(timezone.utc)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def get_stats(user_id: int | None = None) -> dict:
        db = get_session_db()
        try:
            msg_query = db.query(Message)
            conv_query = db.query(Conversation)
            if user_id is not None:
                msg_query = msg_query.filter(Message.user_id == user_id)
                conv_query = conv_query.filter(Conversation.user_id == user_id)
            total_msgs = msg_query.with_entities(func.count(Message.id)).scalar() or 0
            total_convs = conv_query.with_entities(func.count(Conversation.id)).scalar() or 0
            likes = msg_query.filter(Message.feedback_score == 1).with_entities(func.count(Message.id)).scalar() or 0
            dislikes = msg_query.filter(Message.feedback_score == -1).with_entities(func.count(Message.id)).scalar() or 0
            return {
                "total_messages": total_msgs,
                "total_conversations": total_convs,
                "likes": likes,
                "dislikes": dislikes,
            }
        finally:
            db.close()


class ChatAttachmentRepo:
    @staticmethod
    def _public(attachment: ChatAttachment) -> dict:
        return {
            "id": attachment.id,
            "filename": attachment.filename,
            "path": attachment.relative_path,
            "relative_path": attachment.relative_path,
            "content_type": attachment.content_type,
            "extension": attachment.extension,
            "kind": attachment.kind,
            "size": attachment.file_size,
            "checksum": attachment.checksum,
            "is_truncated": bool(attachment.is_truncated),
            "vision_description": attachment.vision_description or "",
            "vision_model": attachment.vision_model or "",
            "vision_updated_at": utc_isoformat(attachment.vision_updated_at) if attachment.vision_updated_at else None,
            "status": attachment.status,
            "created_at": utc_isoformat(attachment.created_at),
        }

    @staticmethod
    def create_many(user_id: int, session_id: str, artifacts: list) -> list[dict]:
        db = get_session_db()
        try:
            rows = [
                ChatAttachment(
                    id=artifact.id,
                    user_id=user_id,
                    session_id=session_id,
                    filename=artifact.filename,
                    relative_path=artifact.relative_path,
                    content_type=artifact.content_type,
                    extension=artifact.extension,
                    kind=artifact.kind,
                    file_size=artifact.file_size,
                    checksum=artifact.checksum,
                    extracted_text=artifact.extracted_text,
                    is_truncated=artifact.is_truncated,
                    status="ready",
                )
                for artifact in artifacts
            ]
            db.add_all(rows)
            db.commit()
            return [ChatAttachmentRepo._public(row) for row in rows]
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def get_owned(attachment_id: str, user_id: int) -> dict | None:
        db = get_session_db()
        try:
            row = db.query(ChatAttachment).filter(
                ChatAttachment.id == attachment_id,
                ChatAttachment.user_id == user_id,
            ).first()
            return ChatAttachmentRepo._public(row) if row else None
        finally:
            db.close()

    @staticmethod
    def save_vision_description(
        attachment_id: str,
        user_id: int,
        description: str,
        vision_model: str,
    ) -> dict | None:
        db = get_session_db()
        try:
            row = db.query(ChatAttachment).filter(
                ChatAttachment.id == attachment_id,
                ChatAttachment.user_id == user_id,
                ChatAttachment.kind == "image",
            ).first()
            if not row:
                return None
            row.vision_description = str(description or "").strip()
            row.vision_model = str(vision_model or "").strip()
            row.vision_updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(row)
            return ChatAttachmentRepo._public(row)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def list_owned_for_delivery(user_id: int, session_id: str, limit: int = 100) -> list[dict]:
        """List ready files with current-conversation uploads first."""
        db = get_session_db()
        try:
            base = db.query(ChatAttachment).filter(
                ChatAttachment.user_id == user_id,
                ChatAttachment.status == "ready",
            )
            current = (
                base.filter(ChatAttachment.session_id == session_id)
                .order_by(ChatAttachment.created_at.desc(), ChatAttachment.id.desc())
                .limit(limit)
                .all()
            )
            remaining = max(0, limit - len(current))
            previous = []
            if remaining:
                previous = (
                    base.filter(ChatAttachment.session_id != session_id)
                    .order_by(ChatAttachment.created_at.desc(), ChatAttachment.id.desc())
                    .limit(remaining)
                    .all()
                )
            return [ChatAttachmentRepo._public(row) for row in [*current, *previous]]
        finally:
            db.close()

    @staticmethod
    def prepare_delivery(
        job_id: str,
        user_id: int,
        *,
        attachment_id: str | None = None,
        artifact=None,
    ) -> dict:
        """Resolve or register one attachment that an assistant message will deliver."""
        if bool(attachment_id) == bool(artifact):
            raise ValueError("Informe exatamente um arquivo para entrega")

        db = get_session_db()
        try:
            job = db.query(ChatJob).filter(ChatJob.id == job_id, ChatJob.user_id == user_id).first()
            if not job:
                raise ValueError("Job nao encontrado")

            row = None
            if attachment_id:
                row = db.query(ChatAttachment).filter(
                    ChatAttachment.id == attachment_id,
                    ChatAttachment.user_id == user_id,
                    ChatAttachment.status == "ready",
                ).first()
                if not row:
                    raise ValueError("Arquivo nao encontrado para este usuario")
            else:
                if int(artifact.user_id) != user_id:
                    raise ValueError("Arquivo pertence a outro usuario")
                row = db.query(ChatAttachment).filter(
                    ChatAttachment.user_id == user_id,
                    ChatAttachment.relative_path == artifact.relative_path,
                    ChatAttachment.checksum == artifact.checksum,
                    ChatAttachment.status == "ready",
                ).order_by(ChatAttachment.created_at.desc()).first()
                if not row:
                    conversation = db.query(Conversation).filter(Conversation.id == job.conversation_id).first()
                    row = ChatAttachment(
                        id=artifact.id,
                        user_id=user_id,
                        session_id=conversation.session_id if conversation else "",
                        conversation_id=job.conversation_id,
                        message_id=job.assistant_message_id,
                        filename=artifact.filename,
                        relative_path=artifact.relative_path,
                        content_type=artifact.content_type,
                        extension=artifact.extension,
                        kind=artifact.kind,
                        file_size=artifact.file_size,
                        checksum=artifact.checksum,
                        extracted_text=artifact.extracted_text,
                        is_truncated=artifact.is_truncated,
                        status="ready",
                        attached_at=datetime.now(timezone.utc),
                    )
                    db.add(row)
                    db.flush()

            payload = ChatAttachmentRepo._public(row)
            db.commit()
            return payload
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def delete_pending(attachment_id: str, user_id: int) -> dict | None:
        db = get_session_db()
        try:
            row = db.query(ChatAttachment).filter(
                ChatAttachment.id == attachment_id,
                ChatAttachment.user_id == user_id,
                ChatAttachment.message_id.is_(None),
            ).first()
            if not row:
                return None
            payload = ChatAttachmentRepo._public(row)
            db.delete(row)
            db.commit()
            return payload
        finally:
            db.close()

    @staticmethod
    def model_content_for_message(message_id: int, user_id: int, user_text: str):
        from src.core.chat_attachments import build_model_user_content

        db = get_session_db()
        try:
            rows = db.query(ChatAttachment).filter(
                ChatAttachment.message_id == message_id,
                ChatAttachment.user_id == user_id,
                ChatAttachment.status == "ready",
            ).order_by(ChatAttachment.created_at.asc(), ChatAttachment.id.asc()).all()
            if not rows:
                return user_text
            attachments = [
                {
                    **ChatAttachmentRepo._public(row),
                    "extracted_text": row.extracted_text or "",
                }
                for row in rows
            ]
            return build_model_user_content(user_id, user_text, attachments)
        finally:
            db.close()


class ChatJobRepo:
    TERMINAL_STATUSES = {"completed", "interrupted", "failed", "cancelled"}

    @staticmethod
    def _validate_replayed_request(
        snapshot: dict,
        *,
        session_id: str,
        message: str,
        response_mode: str,
        reasoning_effort: str,
        use_rag: bool,
        attachment_ids: list[str] | None = None,
    ) -> None:
        expected = (
            session_id,
            message,
            response_mode,
            reasoning_effort,
            bool(use_rag),
            tuple(attachment_ids or []),
        )
        actual = (
            snapshot.get("session_id"),
            snapshot.get("message"),
            snapshot.get("response_mode"),
            snapshot.get("reasoning_effort"),
            bool(snapshot.get("use_rag")),
            tuple(item.get("id") for item in snapshot.get("attachments") or []),
        )
        if actual != expected:
            raise ValueError("client_request_id ja foi usado por outro pedido")

    @staticmethod
    def create_with_messages(
        *,
        user_id: int,
        session_id: str,
        message: str,
        provider: dict,
        response_mode: str,
        reasoning_effort: str,
        use_rag: bool,
        client_request_id: str | None = None,
        attachment_ids: list[str] | None = None,
    ) -> dict:
        db = get_session_db()
        try:
            requested_attachment_ids = list(dict.fromkeys(attachment_ids or []))
            if len(requested_attachment_ids) != len(attachment_ids or []):
                raise ValueError("Anexo duplicado no mesmo pedido")
            if client_request_id:
                existing = db.query(ChatJob).filter(
                    ChatJob.user_id == user_id,
                    ChatJob.client_request_id == client_request_id,
                ).first()
                if existing:
                    snapshot = ChatJobRepo._snapshot(db, existing)
                    ChatJobRepo._validate_replayed_request(
                        snapshot,
                        session_id=session_id,
                        message=message,
                        response_mode=response_mode,
                        reasoning_effort=reasoning_effort,
                        use_rag=use_rag,
                        attachment_ids=requested_attachment_ids,
                    )
                    return snapshot

            attachment_rows: list[ChatAttachment] = []
            if requested_attachment_ids:
                found = db.query(ChatAttachment).filter(
                    ChatAttachment.id.in_(requested_attachment_ids),
                    ChatAttachment.user_id == user_id,
                ).all()
                by_id = {row.id: row for row in found}
                if len(by_id) != len(requested_attachment_ids):
                    raise ValueError("Um ou mais anexos nao existem para este usuario")
                attachment_rows = [by_id[attachment_id] for attachment_id in requested_attachment_ids]
                for attachment in attachment_rows:
                    if attachment.session_id != session_id:
                        raise ValueError("Anexo pertence a outra conversa")
                    if attachment.status != "ready":
                        raise ValueError("Anexo ainda nao esta pronto")
                    if attachment.message_id is not None:
                        raise ValueError("Anexo ja foi enviado em outra mensagem")

            conv = db.query(Conversation).filter(
                Conversation.session_id == session_id,
                Conversation.user_id == user_id,
            ).first()
            if not conv:
                conv = Conversation(session_id=session_id, user_id=user_id, title=f"Conversa {session_id[:8]}")
                db.add(conv)
                db.flush()

            active = db.query(ChatJob).filter(
                ChatJob.conversation_id == conv.id,
                ChatJob.status.in_(["queued", "running"]),
            ).first()
            if active:
                raise ValueError("Esta conversa ja possui uma resposta em andamento")

            job_id = f"job_{uuid4().hex}"
            user_message = Message(
                conversation_id=conv.id,
                user_id=user_id,
                role="user",
                content=message,
                attachments_json=json.dumps(
                    [ChatAttachmentRepo._public(row) for row in attachment_rows],
                    ensure_ascii=False,
                ),
                status="completed",
            )
            assistant_message = Message(
                conversation_id=conv.id,
                user_id=user_id,
                role="assistant",
                content="",
                reasoning="",
                skill_activities_json="[]",
                provider_id=provider.get("provider_id"),
                provider_name=provider.get("provider_name"),
                model_id=provider.get("model_id"),
                model_name=provider.get("model_name"),
                job_id=job_id,
                status="running",
            )
            db.add_all([user_message, assistant_message])
            db.flush()
            for attachment in attachment_rows:
                attachment.conversation_id = conv.id
                attachment.message_id = user_message.id
                attachment.attached_at = datetime.now(timezone.utc)

            job = ChatJob(
                id=job_id,
                user_id=user_id,
                client_request_id=client_request_id,
                conversation_id=conv.id,
                user_message_id=user_message.id,
                assistant_message_id=assistant_message.id,
                provider_id=provider.get("provider_id") or "",
                provider_name=provider.get("provider_name") or "",
                model_id=provider.get("model_id") or "",
                model_name=provider.get("model_name") or "",
                response_mode=response_mode,
                reasoning_effort=reasoning_effort,
                use_rag=use_rag,
                status="queued",
            )
            db.add(job)
            conv.messages_count = (conv.messages_count or 0) + 2
            conv.updated_at = datetime.now(timezone.utc)
            if (conv.messages_count <= 2):
                title = message.strip() or ", ".join(row.filename for row in attachment_rows)
                conv.title = title[:60] + ("..." if len(title) > 60 else "")
            db.commit()
            return ChatJobRepo.get(job_id, user_id) or {}
        except IntegrityError:
            db.rollback()
            if client_request_id:
                existing = db.query(ChatJob).filter(
                    ChatJob.user_id == user_id,
                    ChatJob.client_request_id == client_request_id,
                ).first()
                if existing:
                    snapshot = ChatJobRepo._snapshot(db, existing)
                    ChatJobRepo._validate_replayed_request(
                        snapshot,
                        session_id=session_id,
                        message=message,
                        response_mode=response_mode,
                        reasoning_effort=reasoning_effort,
                        use_rag=use_rag,
                        attachment_ids=requested_attachment_ids,
                    )
                    return snapshot
            raise
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _snapshot(db, job: ChatJob) -> dict:
        assistant = db.query(Message).filter(Message.id == job.assistant_message_id).first()
        user_message = db.query(Message).filter(Message.id == job.user_message_id).first()
        conversation = db.query(Conversation).filter(Conversation.id == job.conversation_id).first()
        return {
            "id": job.id,
            "user_id": job.user_id,
            "client_request_id": job.client_request_id,
            "conversation_id": job.conversation_id,
            "user_message_id": job.user_message_id,
            "assistant_message_id": job.assistant_message_id,
            "session_id": conversation.session_id if conversation else "",
            "message": user_message.content if user_message else "",
            "attachments": json.loads(user_message.attachments_json or "[]") if user_message else [],
            "assistant_attachments": json.loads(assistant.attachments_json or "[]") if assistant else [],
            "provider_id": job.provider_id or "",
            "provider_name": job.provider_name or "",
            "model_id": job.model_id or "",
            "model_name": job.model_name or "",
            "response_mode": job.response_mode,
            "reasoning_effort": job.reasoning_effort,
            "use_rag": bool(job.use_rag),
            "status": job.status,
            "last_event_id": job.last_event_id or 0,
            "content": assistant.content if assistant else "",
            "reasoning": assistant.reasoning if assistant else "",
            "error": job.error or "",
            "created_at": utc_isoformat(job.created_at),
            "started_at": utc_isoformat(job.started_at) if job.started_at else None,
            "completed_at": utc_isoformat(job.completed_at) if job.completed_at else None,
        }

    @staticmethod
    def get(job_id: str, user_id: int | None = None) -> dict | None:
        db = get_session_db()
        try:
            query = db.query(ChatJob).filter(ChatJob.id == job_id)
            if user_id is not None:
                query = query.filter(ChatJob.user_id == user_id)
            job = query.first()
            return ChatJobRepo._snapshot(db, job) if job else None
        finally:
            db.close()

    @staticmethod
    def list_for_user(user_id: int, limit: int = 25) -> list[dict]:
        db = get_session_db()
        try:
            jobs = (
                db.query(ChatJob)
                .filter(ChatJob.user_id == user_id)
                .order_by(ChatJob.created_at.desc(), ChatJob.id.desc())
                .limit(max(1, min(int(limit), 100)))
                .all()
            )
            return [ChatJobRepo._snapshot(db, job) for job in jobs]
        finally:
            db.close()

    @staticmethod
    def set_running(job_id: str) -> None:
        db = get_session_db()
        try:
            job = db.query(ChatJob).filter(ChatJob.id == job_id).first()
            if job:
                job.status = "running"
                job.started_at = datetime.now(timezone.utc)
                db.commit()
        finally:
            db.close()

    @staticmethod
    def claim_queued(job_id: str) -> bool:
        db = get_session_db()
        try:
            updated = db.query(ChatJob).filter(
                ChatJob.id == job_id,
                ChatJob.status == "queued",
            ).update({
                ChatJob.status: "running",
                ChatJob.started_at: datetime.now(timezone.utc),
            }, synchronize_session=False)
            db.commit()
            return updated == 1
        finally:
            db.close()

    @staticmethod
    def add_event(job_id: str, event_type: str, payload: str) -> int:
        db = get_session_db()
        try:
            job = db.query(ChatJob).filter(ChatJob.id == job_id).first()
            if not job:
                raise ValueError("Job nao encontrado")
            event = ChatJobEvent(job_id=job_id, type=event_type, payload=payload)
            db.add(event)
            db.flush()
            job.last_event_id = event.id
            message = db.query(Message).filter(Message.id == job.assistant_message_id).first()
            if message and event_type == "text_delta":
                message.content = (message.content or "") + payload
            elif message and event_type == "reasoning":
                message.reasoning = (message.reasoning or "") + payload
            elif message and event_type == "skill":
                try:
                    activities = json.loads(message.skill_activities_json or "[]")
                    activities.append(json.loads(payload))
                    message.skill_activities_json = json.dumps(activities, ensure_ascii=False)
                except (TypeError, json.JSONDecodeError):
                    pass
            elif message and event_type == "attachment":
                try:
                    attachment = json.loads(payload)
                    attachments = json.loads(message.attachments_json or "[]")
                    if not any(item.get("id") == attachment.get("id") for item in attachments):
                        attachments.append(attachment)
                        message.attachments_json = json.dumps(attachments, ensure_ascii=False)
                except (AttributeError, TypeError, json.JSONDecodeError):
                    pass
            db.commit()
            return int(event.id)
        finally:
            db.close()

    @staticmethod
    def list_events(job_id: str, user_id: int, after_id: int = 0, limit: int = 200) -> list[dict]:
        db = get_session_db()
        try:
            owned = db.query(ChatJob.id).filter(ChatJob.id == job_id, ChatJob.user_id == user_id).first()
            if not owned:
                return []
            events = db.query(ChatJobEvent).filter(
                ChatJobEvent.job_id == job_id,
                ChatJobEvent.id > max(0, after_id),
            ).order_by(ChatJobEvent.id.asc()).limit(limit).all()
            return [{
                "id": event.id,
                "type": event.type,
                "payload": event.payload,
                "created_at": utc_isoformat(event.created_at),
            } for event in events]
        finally:
            db.close()

    @staticmethod
    def finish(job_id: str, status: str, error: str = "") -> int:
        db = get_session_db()
        try:
            job = db.query(ChatJob).filter(ChatJob.id == job_id).first()
            if not job:
                return 0
            job.status = status
            job.error = error
            job.completed_at = datetime.now(timezone.utc)
            message = db.query(Message).filter(Message.id == job.assistant_message_id).first()
            if message:
                message.status = status
            event_type = "done" if status == "completed" else "error"
            payload = json.dumps({"status": status, "error": error}, ensure_ascii=False)
            event = ChatJobEvent(job_id=job_id, type=event_type, payload=payload)
            db.add(event)
            db.flush()
            job.last_event_id = event.id
            db.commit()
            return int(event.id)
        finally:
            db.close()

    @staticmethod
    def interrupt_stale() -> int:
        db = get_session_db()
        try:
            jobs = db.query(ChatJob).filter(ChatJob.status == "running").all()
            for job in jobs:
                job.status = "interrupted"
                job.error = "Servidor reiniciado durante a resposta"
                job.completed_at = datetime.now(timezone.utc)
                message = db.query(Message).filter(Message.id == job.assistant_message_id).first()
                if message:
                    message.status = "interrupted"
            db.commit()
            return len(jobs)
        finally:
            db.close()

    @staticmethod
    def list_queued_ids() -> list[str]:
        db = get_session_db()
        try:
            return [job_id for (job_id,) in db.query(ChatJob.id).filter(ChatJob.status == "queued").all()]
        finally:
            db.close()


class ScheduledTaskRepo:
    @staticmethod
    def _public(row: ScheduledAgentTask) -> dict:
        return {
            "id": row.id,
            "user_id": row.user_id,
            "session_id": row.session_id,
            "prompt": row.prompt,
            "run_at": utc_isoformat(row.run_at),
            "status": row.status,
            "job_id": row.job_id or "",
            "error": row.error or "",
            "created_at": utc_isoformat(row.created_at),
            "completed_at": utc_isoformat(row.completed_at) if row.completed_at else None,
        }

    @staticmethod
    def create(user_id: int, session_id: str, prompt: str, run_at: datetime) -> dict:
        normalized_prompt = (prompt or "").strip()
        if not normalized_prompt:
            raise ValueError("Prompt agendado nao pode ser vazio")
        if len(normalized_prompt) > 8000:
            raise ValueError("Prompt agendado excede 8000 caracteres")
        utc_run_at = run_at.astimezone(timezone.utc).replace(tzinfo=None)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if utc_run_at <= now:
            raise ValueError("O horario agendado precisa estar no futuro")
        task_id = f"schedule_{uuid4().hex}"
        db = get_session_db()
        try:
            row = ScheduledAgentTask(
                id=task_id,
                user_id=user_id,
                session_id=(session_id or "").strip(),
                prompt=normalized_prompt,
                run_at=utc_run_at,
                status="scheduled",
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return ScheduledTaskRepo._public(row)
        finally:
            db.close()

    @staticmethod
    def list_for_user(user_id: int, limit: int = 50) -> list[dict]:
        db = get_session_db()
        try:
            rows = (
                db.query(ScheduledAgentTask)
                .filter(ScheduledAgentTask.user_id == user_id)
                .order_by(ScheduledAgentTask.run_at.desc(), ScheduledAgentTask.id.desc())
                .limit(max(1, min(int(limit), 100)))
                .all()
            )
            return [ScheduledTaskRepo._public(row) for row in rows]
        finally:
            db.close()

    @staticmethod
    def claim_due(limit: int = 20) -> list[dict]:
        db = get_session_db()
        try:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            ids = [
                task_id
                for (task_id,) in (
                    db.query(ScheduledAgentTask.id)
                    .filter(
                        ScheduledAgentTask.status == "scheduled",
                        ScheduledAgentTask.run_at <= now,
                    )
                    .order_by(ScheduledAgentTask.run_at.asc())
                    .limit(max(1, min(int(limit), 100)))
                    .all()
                )
            ]
            claimed: list[dict] = []
            for task_id in ids:
                updated = db.query(ScheduledAgentTask).filter(
                    ScheduledAgentTask.id == task_id,
                    ScheduledAgentTask.status == "scheduled",
                ).update({ScheduledAgentTask.status: "running"}, synchronize_session=False)
                if updated:
                    row = db.query(ScheduledAgentTask).filter(ScheduledAgentTask.id == task_id).first()
                    if row:
                        claimed.append(ScheduledTaskRepo._public(row))
            db.commit()
            return claimed
        finally:
            db.close()

    @staticmethod
    def finish(task_id: str, status: str, *, job_id: str = "", error: str = "") -> bool:
        if status not in {"completed", "failed", "cancelled"}:
            raise ValueError("Status final invalido")
        db = get_session_db()
        try:
            row = db.query(ScheduledAgentTask).filter(ScheduledAgentTask.id == task_id).first()
            if not row:
                return False
            row.status = status
            row.job_id = job_id
            row.error = error[:4000]
            row.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.commit()
            return True
        finally:
            db.close()

    @staticmethod
    def cancel(task_id: str, user_id: int) -> bool:
        db = get_session_db()
        try:
            updated = db.query(ScheduledAgentTask).filter(
                ScheduledAgentTask.id == task_id,
                ScheduledAgentTask.user_id == user_id,
                ScheduledAgentTask.status == "scheduled",
            ).update({
                ScheduledAgentTask.status: "cancelled",
                ScheduledAgentTask.completed_at: datetime.now(timezone.utc).replace(tzinfo=None),
            }, synchronize_session=False)
            db.commit()
            return updated == 1
        finally:
            db.close()

    @staticmethod
    def recover_running() -> int:
        db = get_session_db()
        try:
            updated = db.query(ScheduledAgentTask).filter(
                ScheduledAgentTask.status == "running",
            ).update({ScheduledAgentTask.status: "scheduled"}, synchronize_session=False)
            db.commit()
            return int(updated)
        finally:
            db.close()


class MessageRepo:
    @staticmethod
    def mark_read(message_id: int, user_id: int) -> bool:
        db = get_session_db()
        try:
            message = db.query(Message).filter(
                Message.id == message_id,
                Message.user_id == user_id,
            ).first()
            if not message:
                return False
            message.read_at = datetime.now(timezone.utc)
            db.commit()
            return True
        finally:
            db.close()

    @staticmethod
    def update_content(message_id: int, content: str, user_id: int | None = None) -> Optional[Message]:
        db = get_session_db()
        try:
            query = db.query(Message).filter(Message.id == message_id)
            if user_id is not None:
                query = query.filter(Message.user_id == user_id)
            msg = query.first()
            if not msg:
                return None
            msg.content = content
            db.commit()
            db.refresh(msg)
            db.expunge(msg)
            return msg
        finally:
            db.close()


class DocumentRepo:
    @staticmethod
    def save(
        filename: str,
        source: str,
        chunk_count: int,
        file_size: int,
        user_id: int | None = None,
        upload_path: str = "",
        checksum: str = "",
        status: str = "indexed",
        parser: str = "",
        error_message: str = "",
        vector_ids: list[str] | None = None,
        manifest_path: str = "",
        extracted_path: str = "",
    ) -> KnowledgeDocument:
        db = get_session_db()
        try:
            doc = KnowledgeDocument(
                user_id=user_id,
                filename=filename,
                source=source,
                upload_path=upload_path,
                checksum=checksum,
                status=status,
                parser=parser,
                error_message=error_message,
                vector_ids_json=json.dumps(vector_ids or [], ensure_ascii=False),
                manifest_path=manifest_path,
                extracted_path=extracted_path,
                chunk_count=chunk_count,
                file_size=file_size,
            )
            db.add(doc)
            db.commit()
            db.refresh(doc)
            db.expunge(doc)
            return doc
        finally:
            db.close()

    @staticmethod
    def set_manifest_path(doc_id: int, user_id: int | None, manifest_path: str) -> bool:
        db = get_session_db()
        try:
            query = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == doc_id)
            if user_id is not None:
                query = query.filter(KnowledgeDocument.user_id == user_id)
            doc = query.first()
            if not doc:
                return False
            doc.manifest_path = manifest_path
            db.commit()
            return True
        finally:
            db.close()

    @staticmethod
    def update_ingestion(
        doc_id: int,
        user_id: int,
        *,
        status: str,
        parser: str,
        chunk_count: int,
        vector_ids: list[str] | None = None,
        error_message: str = "",
        extracted_path: str | None = None,
    ) -> Optional[KnowledgeDocument]:
        """Update RAG-derived document state without changing the stored original."""
        db = get_session_db()
        try:
            doc = (
                db.query(KnowledgeDocument)
                .filter(KnowledgeDocument.id == doc_id, KnowledgeDocument.user_id == user_id)
                .first()
            )
            if not doc:
                return None
            doc.status = status
            doc.parser = parser
            doc.chunk_count = chunk_count
            doc.vector_ids_json = json.dumps(vector_ids or [], ensure_ascii=False)
            doc.error_message = error_message
            if extracted_path is not None:
                doc.extracted_path = extracted_path
            db.commit()
            db.refresh(doc)
            db.expunge(doc)
            return doc
        finally:
            db.close()

    @staticmethod
    def list_all(user_id: int | None = None) -> list[KnowledgeDocument]:
        db = get_session_db()
        try:
            query = db.query(KnowledgeDocument)
            if user_id is not None:
                query = query.filter(KnowledgeDocument.user_id == user_id)
            docs = query.order_by(KnowledgeDocument.created_at.desc()).all()
            for doc in docs:
                db.expunge(doc)
            return docs
        finally:
            db.close()

    @staticmethod
    def list_by_source(user_id: int, source: str) -> list[KnowledgeDocument]:
        """Return documents of one source, scoped to exactly one user."""
        db = get_session_db()
        try:
            docs = (
                db.query(KnowledgeDocument)
                .filter(
                    KnowledgeDocument.user_id == user_id,
                    KnowledgeDocument.source == source,
                )
                .order_by(KnowledgeDocument.created_at.desc(), KnowledgeDocument.id.desc())
                .all()
            )
            for doc in docs:
                db.expunge(doc)
            return docs
        finally:
            db.close()

    @staticmethod
    def get(doc_id: int, user_id: int | None = None) -> Optional[KnowledgeDocument]:
        db = get_session_db()
        try:
            query = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == doc_id)
            if user_id is not None:
                query = query.filter(KnowledgeDocument.user_id == user_id)
            doc = query.first()
            if doc:
                db.expunge(doc)
            return doc
        finally:
            db.close()

    @staticmethod
    def delete(doc_id: int, user_id: int | None = None) -> bool:
        db = get_session_db()
        try:
            query = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == doc_id)
            if user_id is not None:
                query = query.filter(KnowledgeDocument.user_id == user_id)
            doc = query.first()
            if not doc:
                return False
            db.delete(doc)
            db.commit()
            return True
        finally:
            db.close()


class SkillRepo:
    @staticmethod
    def ensure_defaults() -> None:
        db = get_session_db()
        try:
            for item in DEFAULT_SKILLS:
                skill = db.query(Skill).filter(Skill.name == item["name"]).first()
                if not skill:
                    db.add(Skill(
                        name=item["name"],
                        description=item["description"],
                        kind=item["kind"],
                        definition_json=json.dumps(item["definition"], ensure_ascii=False),
                        requires_network=item["requires_network"],
                        requires_shell=item["requires_shell"],
                        risk_level=item["risk_level"],
                    ))
                else:
                    # Keep the persisted catalogue aligned with the code registry
                    # without changing which skills each user has enabled.
                    skill.description = item["description"]
                    skill.kind = item["kind"]
                    skill.definition_json = json.dumps(item["definition"], ensure_ascii=False)
                    skill.requires_network = item["requires_network"]
                    skill.requires_shell = item["requires_shell"]
                    skill.risk_level = item["risk_level"]
            db.commit()
        finally:
            db.close()

    @staticmethod
    def list_for_user(user_id: int) -> list[dict]:
        SkillRepo.ensure_defaults()
        db = get_session_db()
        try:
            skills = db.query(Skill).order_by(Skill.name.asc()).all()
            enabled = {
                row.skill_id: row
                for row in db.query(UserSkill).filter(UserSkill.user_id == user_id).all()
            }
            result = []
            for skill in skills:
                user_skill = enabled.get(skill.id)
                try:
                    definition = json.loads(skill.definition_json or "{}")
                except json.JSONDecodeError:
                    definition = {}
                try:
                    config = json.loads(user_skill.config_json or "{}") if user_skill else {}
                except json.JSONDecodeError:
                    config = {}
                result.append({
                    "id": skill.id,
                    "name": skill.name,
                    "description": skill.description,
                    "kind": skill.kind,
                    "definition": definition,
                    "requires_network": skill.requires_network,
                    "requires_shell": skill.requires_shell,
                    "risk_level": skill.risk_level,
                    "enabled": user_skill.is_enabled if user_skill else bool(definition.get("default_enabled", False)),
                    "config": config,
                }
                )
            return result
        finally:
            db.close()

    @staticmethod
    def set_enabled(user_id: int, skill_name: str, enabled: bool, config: dict | None = None) -> bool:
        SkillRepo.ensure_defaults()
        db = get_session_db()
        try:
            skill = db.query(Skill).filter(Skill.name == skill_name).first()
            if not skill:
                return False
            user_skill = db.query(UserSkill).filter(UserSkill.user_id == user_id, UserSkill.skill_id == skill.id).first()
            if not user_skill:
                user_skill = UserSkill(user_id=user_id, skill_id=skill.id)
                db.add(user_skill)
            user_skill.is_enabled = enabled
            if config is not None:
                user_skill.config_json = json.dumps(config, ensure_ascii=False)
            user_skill.updated_at = datetime.now(timezone.utc)
            db.commit()
            return True
        finally:
            db.close()

    @staticmethod
    def enabled_context_for_user(user_id: int) -> str:
        """Build a safe prompt context from skills enabled for one user."""
        enabled_skills = [
            skill
            for skill in SkillRepo.list_for_user(user_id)
            if skill.get("enabled") and skill.get("kind") != "workspace_agent"
        ]
        if not enabled_skills:
            return ""

        lines = [
            "Skills habilitadas para este usuario:",
            "Pedidos explicitos como pesquise, busque ou procure autorizam as skills de pesquisa. "
            "Quando houver 'Resultado da skill' no contexto, a pesquisa ja foi executada: use o resultado, preserve as fontes e nao peca nova confirmacao. "
            "Pedidos explicitos sobre chats anteriores autorizam a skill conversation_history, sempre limitada ao proprio usuario. "
            "Shell e escrita externa continuam proibidos sem o fluxo seguro correspondente.",
        ]
        for skill in enabled_skills:
            definition = skill.get("definition") or {}
            definition_text = json.dumps(definition, ensure_ascii=False, sort_keys=True)
            lines.append(
                f"- {skill['name']} ({skill['kind']}): {skill['description']} Definicao: {definition_text}"
            )
        return "\n".join(lines)


class SkillRunRepo:
    @staticmethod
    def _append_audit_file(run: SkillRun) -> None:
        try:
            audit_path = safe_user_path(run.user_id, "skills", "audit/skill_runs.jsonl")
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "id": run.id,
                "user_id": run.user_id,
                "skill_name": run.skill_name,
                "status": run.status,
                "input": json.loads(run.input_json or "{}"),
                "output_summary": run.output_summary,
                "error_message": run.error_message,
                "started_at": utc_isoformat(run.started_at) if run.started_at else None,
                "finished_at": utc_isoformat(run.finished_at) if run.finished_at else None,
            }
            with audit_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        except Exception:
            pass

    @staticmethod
    def create(
        user_id: int,
        skill_name: str,
        status: str,
        input_data: dict,
        output_summary: str = "",
        error_message: str = "",
    ) -> SkillRun:
        db = get_session_db()
        try:
            now = datetime.now(timezone.utc)
            run = SkillRun(
                user_id=user_id,
                skill_name=skill_name,
                status=status,
                input_json=json.dumps(input_data, ensure_ascii=False),
                output_summary=output_summary,
                error_message=error_message[:2000],
                started_at=now,
                finished_at=now,
            )
            db.add(run)
            db.commit()
            db.refresh(run)
            SkillRunRepo._append_audit_file(run)
            db.expunge(run)
            return run
        finally:
            db.close()

    @staticmethod
    def list_for_user(user_id: int, limit: int = 50) -> list[dict]:
        db = get_session_db()
        try:
            runs = (
                db.query(SkillRun)
                .filter(SkillRun.user_id == user_id)
                .order_by(SkillRun.started_at.desc(), SkillRun.id.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": run.id,
                    "user_id": run.user_id,
                    "skill_name": run.skill_name,
                    "status": run.status,
                    "input_json": run.input_json,
                    "output_summary": run.output_summary,
                    "error_message": run.error_message,
                    "started_at": utc_isoformat(run.started_at) if run.started_at else None,
                    "finished_at": utc_isoformat(run.finished_at) if run.finished_at else None,
                }
                for run in runs
            ]
        finally:
            db.close()
