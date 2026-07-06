"""Sistema de feedback do usuário."""

from typing import Optional
from src.db.repository import ConversationRepo


class FeedbackManager:
    """Gerencia feedback dos usuários sobre as respostas."""

    @staticmethod
    def register_feedback(message_id: int, score: int) -> bool:
        """
        Registra feedback para uma mensagem.
        score: 1 = like, -1 = dislike, 0 = neutro
        """
        if score not in (1, -1, 0):
            return False
        return ConversationRepo.set_feedback(message_id, score)

    @staticmethod
    def get_stats() -> dict:
        """Retorna estatísticas de feedback."""
        stats = ConversationRepo.get_stats()
        total = stats["likes"] + stats["dislikes"]
        if total > 0:
            stats["satisfaction_rate"] = round(stats["likes"] / total * 100, 1)
        else:
            stats["satisfaction_rate"] = 0
        return stats
