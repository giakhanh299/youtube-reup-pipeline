from __future__ import annotations

from pathlib import Path
import shutil
import unittest
import uuid

from services.voice_registry import list_voice_files, resolve_voice_path


class VoiceRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path.cwd() / "runtime" / "test_voice_registry" / uuid.uuid4().hex
        self.root.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def test_list_voice_files_returns_allowed_audio_files(self) -> None:
        (self.root / "a.wav").write_bytes(b"a")
        (self.root / "b.mp3").write_bytes(b"b")
        (self.root / "c.txt").write_text("no", encoding="utf-8")

        self.assertEqual(list_voice_files(self.root), ["a.wav", "b.mp3"])

    def test_resolve_existing_voice(self) -> None:
        voice = self.root / "cute.wav"
        voice.write_bytes(b"voice")

        self.assertEqual(resolve_voice_path("cute.wav", self.root), voice.resolve())

    def test_rejects_path_traversal(self) -> None:
        with self.assertRaisesRegex(ValueError, "path traversal"):
            resolve_voice_path("../secret.wav", self.root)

    def test_rejects_unsupported_extension(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported voice file extension"):
            resolve_voice_path("voice.txt", self.root)

    def test_default_voice_fallback(self) -> None:
        voice = self.root / "default.flac"
        voice.write_bytes(b"voice")

        self.assertEqual(resolve_voice_path("", self.root, "default.flac"), voice.resolve())

    def test_missing_voice_has_clear_error(self) -> None:
        with self.assertRaisesRegex(FileNotFoundError, "Voice file not found"):
            resolve_voice_path("missing.wav", self.root)


if __name__ == "__main__":
    unittest.main()
