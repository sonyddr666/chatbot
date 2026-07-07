import inspect
import unittest
from pathlib import Path

from fastapi.params import Depends

from src.api.routes import router
from src.api.workspace_routes import router as workspace_router


class RouteSecurityTest(unittest.TestCase):
    def test_legacy_unauthenticated_websocket_file_is_removed(self):
        self.assertFalse(Path("src/api/ws_routes.py").exists())

    def test_sensitive_routes_require_current_user_dependency(self):
        sensitive_prefixes = (
            "/providers",
            "/codex",
            "/profiles",
            "/config",
            "/metrics",
            "/workspace",
            "/skills",
        )
        violations = []

        for route in [*router.routes, *workspace_router.routes]:
            path = getattr(route, "path", "")
            if not path.startswith(sensitive_prefixes):
                continue
            signature = inspect.signature(route.endpoint)
            user_param = signature.parameters.get("user")
            default = user_param.default if user_param else None
            if not isinstance(default, Depends):
                violations.append(path)

        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
