import tempfile
import unittest
import uuid
from pathlib import Path

from src.config import settings


class UserSpaceServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.previous_user_data_dir = getattr(settings, "user_data_dir", "./data/users")
        settings.user_data_dir = self.tmp.name

    def tearDown(self):
        settings.user_data_dir = self.previous_user_data_dir

    def test_ensure_user_space_creates_expected_directories(self):
        from src.core.userspace import ensure_user_space

        paths = ensure_user_space(42)

        self.assertEqual(paths.user_id, 42)
        self.assertTrue(paths.root.is_dir())
        self.assertTrue(paths.profile.is_dir())
        self.assertTrue(paths.workspace.is_dir())
        self.assertTrue(paths.uploads.is_dir())
        self.assertTrue((paths.uploads / "original").is_dir())
        self.assertTrue(paths.rag.is_dir())
        self.assertTrue((paths.rag / "documents").is_dir())
        self.assertTrue((paths.rag / "extracted").is_dir())
        self.assertTrue((paths.rag / "manifests").is_dir())
        self.assertTrue(paths.skills.is_dir())
        self.assertTrue((paths.skills / "user").is_dir())
        self.assertTrue((paths.skills / "audit").is_dir())

    def test_safe_user_path_accepts_normal_relative_path(self):
        from src.core.userspace import safe_user_path

        resolved = safe_user_path(7, "workspace", "projetos/app.md")

        expected = Path(self.tmp.name).resolve() / "7" / "workspace" / "projetos" / "app.md"
        self.assertEqual(resolved, expected)

    def test_safe_user_path_blocks_path_traversal(self):
        from src.core.userspace import safe_user_path

        with self.assertRaises(ValueError):
            safe_user_path(7, "workspace", "../secret.txt")

    def test_safe_user_path_blocks_absolute_paths(self):
        from src.core.userspace import safe_user_path

        with self.assertRaises(ValueError):
            safe_user_path(7, "workspace", "C:/Windows/win.ini")

    def test_safe_user_path_blocks_unknown_area(self):
        from src.core.userspace import safe_user_path

        with self.assertRaises(ValueError):
            safe_user_path(7, "database", "chatbot.db")

    def test_write_profile_text_saves_file_inside_profile_area(self):
        from src.core.userspace import write_profile_text

        path = write_profile_text(7, "onboarding.md", "# Perfil\nTeste")

        expected = Path(self.tmp.name).resolve() / "7" / "profile" / "onboarding.md"
        self.assertEqual(path, expected)
        self.assertEqual(path.read_text(encoding="utf-8"), "# Perfil\nTeste")

    def test_write_profile_text_blocks_unsafe_filename(self):
        from src.core.userspace import write_profile_text

        with self.assertRaises(ValueError):
            write_profile_text(7, "../onboarding.md", "fora")

    def test_create_user_initializes_user_space(self):
        from src.db.models import init_db
        from src.db.repository import UserRepo

        Path("C:/tmp").mkdir(parents=True, exist_ok=True)
        db_path = Path(f"C:/tmp/chatbot_userspace_{uuid.uuid4().hex}.db")
        previous_database_url = settings.database_url
        settings.database_url = f"sqlite:///{db_path.as_posix()}"
        self.addCleanup(lambda: setattr(settings, "database_url", previous_database_url))
        init_db()

        user = UserRepo.create_user(
            "userspace@example.test",
            "userspace",
            "secret123",
            "User Space",
        )

        root = Path(self.tmp.name).resolve() / str(user.id)
        self.assertTrue((root / "profile").is_dir())
        self.assertTrue((root / "workspace").is_dir())
        self.assertTrue((root / "uploads" / "original").is_dir())
        self.assertTrue((root / "rag" / "documents").is_dir())
        self.assertTrue((root / "skills" / "user").is_dir())
        self.assertTrue((root / "skills" / "audit").is_dir())

    def test_initial_admin_initializes_user_space(self):
        from src.db.models import init_db
        from src.db.repository import UserRepo

        Path("C:/tmp").mkdir(parents=True, exist_ok=True)
        db_path = Path(f"C:/tmp/chatbot_userspace_{uuid.uuid4().hex}.db")
        previous_database_url = settings.database_url
        previous_admin = (
            settings.initial_admin_email,
            settings.initial_admin_username,
            settings.initial_admin_password,
        )
        settings.database_url = f"sqlite:///{db_path.as_posix()}"
        self.addCleanup(lambda: setattr(settings, "database_url", previous_database_url))
        settings.initial_admin_email = "admin@example.test"
        settings.initial_admin_username = "admin"
        settings.initial_admin_password = "secure-test-password"
        self.addCleanup(
            lambda: (
                setattr(settings, "initial_admin_email", previous_admin[0]),
                setattr(settings, "initial_admin_username", previous_admin[1]),
                setattr(settings, "initial_admin_password", previous_admin[2]),
            )
        )
        init_db()

        user = UserRepo.ensure_initial_admin()

        root = Path(self.tmp.name).resolve() / str(user.id)
        self.assertTrue((root / "profile").is_dir())
        self.assertTrue((root / "workspace").is_dir())
        self.assertTrue((root / "uploads" / "original").is_dir())
        self.assertTrue((root / "rag" / "documents").is_dir())
        self.assertTrue((root / "skills" / "user").is_dir())
        self.assertTrue((root / "skills" / "audit").is_dir())


if __name__ == "__main__":
    unittest.main()
