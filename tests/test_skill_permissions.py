import unittest


class SkillPermissionsTest(unittest.TestCase):
    def test_permission_allows_only_enabled_non_shell_skills(self):
        from src.core.skill_permissions import can_execute_skill

        self.assertTrue(can_execute_skill({"name": "simple_search", "enabled": True, "requires_shell": False}))
        self.assertFalse(can_execute_skill({"name": "simple_search", "enabled": False, "requires_shell": False}))
        self.assertFalse(can_execute_skill({"name": "danger_shell", "enabled": True, "requires_shell": True}))

    def test_web_search_ignores_enabled_shell_skill(self):
        from src.core.skill_runtime import should_run_web_search

        skills = [{"name": "simple_search", "enabled": True, "requires_shell": True}]

        self.assertFalse(should_run_web_search("pesquise noticias", skills))


if __name__ == "__main__":
    unittest.main()
