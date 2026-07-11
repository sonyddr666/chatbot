import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrontendAdminUsersTest(unittest.TestCase):
    def test_registration_waits_for_approval_without_storing_token(self):
        auth = (ROOT / "frontend/src/components/AuthPanel.tsx").read_text(encoding="utf-8")
        api = (ROOT / "frontend/src/lib/api.ts").read_text(encoding="utf-8")

        self.assertIn("api.registrationStatus()", auth)
        self.assertIn("Solicitacao enviada para aprovacao", auth)
        self.assertIn("req<RegistrationResponse>('/auth/register'", api)

    def test_admin_panel_exposes_guarded_approval_flow(self):
        panel = (ROOT / "frontend/src/components/AdminUsersPanel.tsx").read_text(encoding="utf-8")
        app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")

        self.assertIn("api.adminApproveUser", panel)
        self.assertIn("api.adminRejectUser", panel)
        self.assertIn("api.adminDeleteRegistration", panel)
        self.assertIn("Excluir e liberar dados", panel)
        self.assertIn("user.is_admin && <AdminUsersPanel", app)


if __name__ == "__main__":
    unittest.main()
