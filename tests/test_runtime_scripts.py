from __future__ import annotations

import importlib
import unittest


class RuntimeScriptsTests(unittest.TestCase):
    def test_runtime_scripts_import_without_side_effects(self) -> None:
        check_runtime = importlib.import_module("scripts.check_runtime")
        docker_smoke_test = importlib.import_module("scripts.docker_smoke_test")

        self.assertTrue(callable(check_runtime.main))
        self.assertTrue(callable(docker_smoke_test.main))

    def test_docker_smoke_required_modules_include_current_entrypoint(self) -> None:
        docker_smoke_test = importlib.import_module("scripts.docker_smoke_test")

        self.assertIn("pipeline", docker_smoke_test.REQUIRED_MODULES)
        self.assertIn("workers.upload_worker", docker_smoke_test.REQUIRED_MODULES)


if __name__ == "__main__":
    unittest.main()
