import unittest
from pathlib import Path


class FrontendWorkspaceManagerTest(unittest.TestCase):
    def test_workspace_has_tree_drag_confirmation_and_opt_in_rag(self):
        panel = Path("frontend/src/components/WorkspacePanel.tsx").read_text(encoding="utf-8")
        plan_card = Path("frontend/src/components/WorkspacePlanCard.tsx").read_text(encoding="utf-8")
        api = Path("frontend/src/lib/api.ts").read_text(encoding="utf-8")

        for contract in (
            "application/x-workspace-path",
            "'movimentacao'",
            "Confirmar exclusao",
            "Gerenciador completo de arquivos",
            "Selecionar para RAG",
            "workspaceRagIngest",
        ):
            self.assertIn(contract, panel + api)

        self.assertIn("WorkspacePlanCard", plan_card)
        self.assertIn("Confirmar e executar", plan_card)
        self.assertIn("Tudo concluido", plan_card)
        self.assertIn("#16a34a", plan_card)
        self.assertIn("Adicionar selecionados ao RAG", plan_card)
        self.assertIn("workspaceAiApplyPlan", api)
        self.assertIn("workspace_plan", api)

        chat_message = Path("frontend/src/components/ChatMessage.tsx").read_text(encoding="utf-8")
        self.assertIn("workspace-plan:[a-f0-9]{32}", chat_message)
        self.assertIn("hover:brightness-150", panel)
        self.assertIn("Extraindo texto, criando chunks", panel)
        self.assertIn("Processando ${index + 1}", plan_card)
        self.assertIn("workspaceReadBlob", panel + api)
        self.assertIn("'.webp'", panel)
        self.assertIn("Preview visual - original preservado", panel)
        self.assertIn("imageExpanded", panel)
        self.assertIn("Baixar original", panel)

    def test_sidebar_upload_no_longer_uses_immediate_rag_endpoint(self):
        sidebar = Path("frontend/src/components/Sidebar.tsx").read_text(encoding="utf-8")
        self.assertIn("api.uploadOriginalDocument", sidebar)
        self.assertNotIn("api.uploadDocument(file)", sidebar)
        self.assertIn("documents-changed", sidebar)
        self.assertIn("refreshDocuments", sidebar)


if __name__ == "__main__":
    unittest.main()
