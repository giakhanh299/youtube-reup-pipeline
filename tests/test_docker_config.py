from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DockerConfigTests(unittest.TestCase):
    def test_compose_defines_required_app_service_and_volumes(self) -> None:
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

        self.assertIn("  app:", compose)
        self.assertIn("./runtime/logs:/app/runtime/logs", compose)
        self.assertIn("./runtime/state:/app/runtime/state", compose)
        self.assertIn('command: ["python", "pipeline.py"]', compose)

    def test_dockerfile_installs_ffmpeg_and_uses_existing_entrypoint(self) -> None:
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("ffmpeg", dockerfile)
        self.assertIn('CMD ["python", "pipeline.py"]', dockerfile)

    def test_dockerignore_excludes_secrets_and_runtime_outputs(self) -> None:
        dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

        self.assertIn(".env", dockerignore)
        self.assertIn("runtime/logs", dockerignore)
        self.assertIn("service_account*.json", dockerignore)


if __name__ == "__main__":
    unittest.main()
