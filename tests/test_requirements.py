import unittest
from pathlib import Path


class RequirementsTest(unittest.TestCase):
    def test_pytest_is_declared_for_pytest_based_tests(self):
        requirements = Path("requirements.txt").read_text(encoding="utf-8").lower()

        self.assertIn("pytest", requirements)


if __name__ == "__main__":
    unittest.main()
