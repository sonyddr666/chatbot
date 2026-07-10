import asyncio
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

from src.config import settings
from src.core.workspace import read_text_file
from src.core.workspace_agent import (
    apply_workspace_plan,
    create_workspace_plan,
    get_workspace_plan,
    is_workspace_management_request,
    workspace_plan_status_context,
)
from src.db.models import init_db
from src.db.repository import ConversationRepo, DocumentRepo, SkillRepo, SkillRunRepo, UserRepo


class WorkspaceAgentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.previous_user_data_dir = settings.user_data_dir
        self.previous_database_url = settings.database_url
        settings.user_data_dir = self.tmp.name
        Path("C:/tmp").mkdir(parents=True, exist_ok=True)
        db_path = Path(f"C:/tmp/chatbot_workspace_agent_{uuid.uuid4().hex}.db")
        settings.database_url = f"sqlite:///{db_path.as_posix()}"
        init_db()
        self.user = UserRepo.create_user(
            f"workspace-agent-{uuid.uuid4().hex[:8]}@example.test",
            f"workspace_agent_{uuid.uuid4().hex[:8]}",
            "secret123",
            "Workspace Agent",
        )

    def tearDown(self):
        settings.user_data_dir = self.previous_user_data_dir
        settings.database_url = self.previous_database_url

    def test_document_md_request_activates_workspace_manager(self):
        self.assertTrue(is_workspace_management_request("use o que pesquisou e crie um documento md completo"))
        self.assertTrue(is_workspace_management_request("salve isso como uma nota Markdown"))
        self.assertFalse(is_workspace_management_request("como criar um documento md?"))

    def test_document_md_fallback_creates_a_real_file_action(self):
        with patch("src.core.workspace_agent.generate", new=AsyncMock(return_value="resposta sem JSON")):
            plan = asyncio.run(
                create_workspace_plan(self.user.id, "crie um documento md completo", {})
            )

        self.assertEqual(plan["status"], "pending")
        self.assertEqual(plan["actions"][0]["operation"], "write_file")
        self.assertEqual(plan["actions"][0]["path"], "documento.md")

    def test_referenced_search_is_sent_to_workspace_planner(self):
        SkillRunRepo.create(
            self.user.id,
            "perplexo_search",
            "completed",
            {"query": "deus existe"},
            output_summary="Pesquisa confirmada com https://example.test/fonte",
        )
        proposal = json.dumps({
            "summary": "Criar documento pesquisado",
            "actions": [{"operation": "write_file", "path": "deus.md", "content": "resultado"}],
        })
        generator = AsyncMock(return_value=proposal)

        with patch("src.core.workspace_agent.generate", new=generator):
            asyncio.run(
                create_workspace_plan(
                    self.user.id,
                    "use o que pesquisou e crie um documento md completo",
                    {},
                )
            )

        planner_messages = generator.await_args.args[0]
        self.assertIn("Pesquisa recente confirmada pelo backend", planner_messages[1].content)
        self.assertIn("https://example.test/fonte", planner_messages[1].content)

    def test_edit_it_exports_all_owned_conversations_to_latest_applied_file(self):
        proposal = json.dumps({
            "summary": "Criar documento vazio",
            "actions": [{"operation": "write_file", "path": "documento.txt", "content": ""}],
        })
        with patch("src.core.workspace_agent.generate", new=AsyncMock(return_value=proposal)):
            created = asyncio.run(create_workspace_plan(self.user.id, "criar documento", {}))
        apply_workspace_plan(self.user.id, created["id"])

        first_session = f"u{self.user.id}:primeira"
        second_session = f"u{self.user.id}:segunda"
        ConversationRepo.add_message(first_session, "user", "Mensagem alpha", user_id=self.user.id)
        ConversationRepo.add_message(
            first_session,
            "assistant",
            "Resposta alpha",
            user_id=self.user.id,
            reasoning="Raciocinio alpha",
            skill_activities=[{"name": "perplexo_search", "status": "completed"}],
        )
        ConversationRepo.add_message(second_session, "user", "Mensagem beta", user_id=self.user.id)
        SkillRunRepo.create(
            self.user.id,
            "perplexo_search",
            "completed",
            {"query": "pesquisa alpha"},
            output_summary="RESULTADO COMPLETO DA PESQUISA",
        )
        other = UserRepo.create_user(
            f"workspace-secret-{uuid.uuid4().hex[:8]}@example.test",
            f"workspace_secret_{uuid.uuid4().hex[:8]}",
            "secret123",
            "Other",
        )
        ConversationRepo.add_message("other-secret-session", "user", "SEGREDO ALHEIO", user_id=other.id)

        instruction = "edita ele e coloca os dados de todos chats completos"
        self.assertTrue(is_workspace_management_request(instruction, self.user.id))
        generator = AsyncMock(return_value="nao deve ser usado")
        with patch("src.core.workspace_agent.generate", new=generator):
            plan = asyncio.run(
                create_workspace_plan(
                    self.user.id,
                    instruction,
                    {},
                    session_id=first_session,
                )
            )

        generator.assert_not_awaited()
        action = plan["actions"][0]
        self.assertEqual(action["path"], "documento.txt")
        self.assertEqual(action["mode"], "edit")
        self.assertIn("Mensagem alpha", action["content"])
        self.assertIn("Mensagem beta", action["content"])
        self.assertIn("Raciocinio alpha", action["content"])
        self.assertIn("perplexo_search", action["content"])
        self.assertIn("RESULTADO COMPLETO DA PESQUISA", action["content"])
        self.assertNotIn("SEGREDO ALHEIO", action["content"])

    def test_workspace_manager_is_enabled_by_default_but_requires_confirmation(self):
        skills = SkillRepo.list_for_user(self.user.id)
        manager = next(skill for skill in skills if skill["name"] == "workspace_manager")
        proposal = json.dumps({
            "summary": "Criar perfil",
            "actions": [
                {"operation": "mkdir", "path": "sobre-mim"},
                {"operation": "write_file", "path": "sobre-mim/README.md", "content": "# Eu\n"},
            ],
        })

        with patch("src.core.workspace_agent.generate", new=AsyncMock(return_value=proposal)):
            plan = asyncio.run(create_workspace_plan(self.user.id, "crie pasta e arquivo", {}))

        workspace_file = Path(self.tmp.name) / str(self.user.id) / "workspace" / "sobre-mim" / "README.md"
        self.assertTrue(manager["enabled"])
        self.assertEqual(plan["status"], "pending")
        self.assertFalse(workspace_file.exists())
        self.assertEqual(DocumentRepo.list_all(self.user.id), [])

        applied = apply_workspace_plan(self.user.id, plan["id"])

        self.assertEqual(applied["status"], "applied")
        self.assertEqual(read_text_file(self.user.id, "sobre-mim/README.md"), "# Eu\n")
        self.assertEqual(DocumentRepo.list_all(self.user.id), [])
        self.assertIn("status=applied", workspace_plan_status_context(self.user.id))

    def test_plan_is_stored_only_inside_its_owner_userspace(self):
        other = UserRepo.create_user(
            f"workspace-other-{uuid.uuid4().hex[:8]}@example.test",
            f"workspace_other_{uuid.uuid4().hex[:8]}",
            "secret123",
            "Other",
        )
        proposal = json.dumps({
            "summary": "Criar nota",
            "actions": [{"operation": "write_file", "path": "note.md", "content": "segredo"}],
        })
        with patch("src.core.workspace_agent.generate", new=AsyncMock(return_value=proposal)):
            plan = asyncio.run(create_workspace_plan(self.user.id, "crie note.md", {}))

        owner_plan = get_workspace_plan(self.user.id, plan["id"])

        self.assertEqual(owner_plan["user_id"], self.user.id)
        with self.assertRaises(FileNotFoundError):
            get_workspace_plan(other.id, plan["id"])

    def test_recursive_delete_is_planned_and_applied_only_after_confirmation(self):
        from src.core.workspace import write_text_file

        write_text_file(self.user.id, "old/inside.txt", "remove")
        proposal = json.dumps({
            "summary": "Apagar pasta",
            "actions": [{"operation": "delete", "path": "old", "recursive": True}],
        })
        with patch("src.core.workspace_agent.generate", new=AsyncMock(return_value=proposal)):
            plan = asyncio.run(create_workspace_plan(self.user.id, "apague a pasta old", {}))

        folder = Path(self.tmp.name) / str(self.user.id) / "workspace" / "old"
        self.assertTrue(folder.exists())

        apply_workspace_plan(self.user.id, plan["id"])

        self.assertFalse(folder.exists())

    def test_ai_plan_rejects_absolute_paths(self):
        proposal = json.dumps({
            "summary": "Tentativa invalida",
            "actions": [{"operation": "write_file", "path": "C:/outside.txt", "content": "fora"}],
        })
        with patch("src.core.workspace_agent.generate", new=AsyncMock(return_value=proposal)):
            with self.assertRaisesRegex(ValueError, "absoluto"):
                asyncio.run(create_workspace_plan(self.user.id, "crie arquivo", {}))


if __name__ == "__main__":
    unittest.main()
