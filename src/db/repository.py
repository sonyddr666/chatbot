"""Repository helpers for persistence."""

from datetime import datetime, timezone
from typing import Optional
import json
from sqlalchemy import func, or_

from src.core.auth import hash_password, verify_password
from src.core.userspace import ensure_user_space, safe_user_path
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
)


class UserRepo:
    @staticmethod
    def ensure_default_user() -> User:
        db = get_session_db()
        try:
            user = db.query(User).filter(User.username == "local-admin").first()
            if not user:
                user = User(
                    email="local-admin@example.local",
                    username="local-admin",
                    display_name="Local Admin",
                    password_hash=hash_password("local-admin"),
                    is_admin=True,
                )
                db.add(user)
                db.flush()
                db.add(UserProfile(user_id=user.id, language="pt", preferred_tone="direto"))
                db.commit()
                db.refresh(user)
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
    def authenticate(login: str, password: str) -> Optional[User]:
        db = get_session_db()
        try:
            user = (
                db.query(User)
                .filter(or_(User.email == login.strip().lower(), User.username == login.strip()))
                .first()
            )
            if not user or not user.is_active or not verify_password(password, user.password_hash):
                return None
            db.expunge(user)
            return user
        finally:
            db.close()

    @staticmethod
    def get(user_id: int) -> Optional[User]:
        db = get_session_db()
        try:
            user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
            if user:
                db.expunge(user)
            return user
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
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None,
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
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
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


class MessageRepo:
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
                    config = json.loads(user_skill.config_json or "{}") if user_skill else {}
                except json.JSONDecodeError:
                    config = {}
                result.append({
                    "id": skill.id,
                    "name": skill.name,
                    "description": skill.description,
                    "kind": skill.kind,
                    "definition": json.loads(skill.definition_json or "{}"),
                    "requires_network": skill.requires_network,
                    "requires_shell": skill.requires_shell,
                    "risk_level": skill.risk_level,
                    "enabled": user_skill.is_enabled if user_skill else False,
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
        enabled_skills = [skill for skill in SkillRepo.list_for_user(user_id) if skill.get("enabled")]
        if not enabled_skills:
            return ""

        lines = [
            "Skills habilitadas para este usuario:",
            "Use estas habilidades como preferencia operacional. Nao execute rede, shell ou acoes externas sem confirmacao explicita do usuario.",
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
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
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
                output_summary=output_summary[:2000],
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
                    "started_at": run.started_at.isoformat() if run.started_at else None,
                    "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                }
                for run in runs
            ]
        finally:
            db.close()
