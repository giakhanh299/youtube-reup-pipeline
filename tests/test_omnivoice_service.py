from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from repositories.sheet_repository import SheetRepository
from processors.sheet_client import SheetConfig
from services.omnivoice_service import OmniVoiceService, OmniVoiceServiceError
from services.tts_service import TTSService


class FakeOmniVoiceModel:
    def __init__(self):
        self.device = ""
        self.calls = []

    def to(self, device):
        self.device = device
        return self

    def synthesize(self, **kwargs):
        self.calls.append(kwargs)
        Path(kwargs["output_path"]).write_bytes(b"wav")


class OmniVoiceServiceTests(unittest.TestCase):
    def test_synthesize_uses_reference_audio_and_writes_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            ref = Path(temp) / "ref.wav"
            out = Path(temp) / "out.wav"
            ref.write_bytes(b"ref")
            model = FakeOmniVoiceModel()
            service = OmniVoiceService(model_loader=lambda _name: model, device="cpu")

            service.synthesize(
                "xin chao",
                out,
                {
                    "ref_audio_path": str(ref),
                    "ref_text": "mau giong",
                    "language": "vi",
                    "speed": "1.2",
                    "pitch": "0.5",
                },
            )

            self.assertEqual(out.read_bytes(), b"wav")
            self.assertEqual(model.device, "cpu")
            self.assertEqual(model.calls[0]["language"], "vi")
            self.assertEqual(model.calls[0]["speed"], 1.2)

    def test_missing_reference_audio_fails_clearly(self) -> None:
        service = OmniVoiceService(model_loader=lambda _name: FakeOmniVoiceModel())

        with self.assertRaisesRegex(FileNotFoundError, "ref_audio_path not found"):
            service.synthesize("text", Path("out.wav"), {"ref_audio_path": "missing.wav", "ref_text": "ref"})

    def test_empty_reference_audio_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            ref = Path(temp) / "ref.wav"
            ref.write_bytes(b"")
            service = OmniVoiceService(model_loader=lambda _name: FakeOmniVoiceModel())

            with self.assertRaisesRegex(ValueError, "ref_audio_path is empty"):
                service.synthesize("text", Path(temp) / "out.wav", {"ref_audio_path": str(ref), "ref_text": "ref"})

    def test_model_without_generation_method_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            ref = Path(temp) / "ref.wav"
            ref.write_bytes(b"ref")
            service = OmniVoiceService(model_loader=lambda _name: object())

            with self.assertRaisesRegex(OmniVoiceServiceError, "no supported"):
                service.synthesize("text", Path(temp) / "out.wav", {"ref_audio_path": str(ref), "ref_text": "ref"})

    def test_diagnostics_include_device_information(self) -> None:
        service = OmniVoiceService(device="cpu", dtype="float32")

        diagnostics = service.diagnostics()

        self.assertEqual(diagnostics["requested_device"], "cpu")
        self.assertEqual(diagnostics["resolved_device"], "cpu")
        self.assertEqual(diagnostics["dtype"], "float32")

    def test_missing_package_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            ref = Path(temp) / "ref.wav"
            ref.write_bytes(b"ref")
            service = OmniVoiceService(model_loader=lambda _name: (_ for _ in ()).throw(ImportError("missing")))

            with self.assertRaisesRegex(OmniVoiceServiceError, "OmniVoice package/model is not available"):
                service.synthesize("text", Path(temp) / "out.wav", {"ref_audio_path": str(ref), "ref_text": "ref"})

    def test_tts_service_routes_omnivoice_engine(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            ref = Path(temp) / "ref.wav"
            out = Path(temp) / "out.wav"
            ref.write_bytes(b"ref")

            with patch("services.tts_service.OmniVoiceService") as service_cls:
                service_cls.return_value.synthesize.side_effect = lambda _text, output, _cfg: output.write_bytes(b"wav")
                TTSService(settings={"omnivoice_device": "cpu"}).create_voice(
                    "text",
                    out,
                    {"tts_engine": "omnivoice", "ref_audio_path": str(ref), "ref_text": "ref"},
                    "",
                )

                self.assertEqual(out.read_bytes(), b"wav")
                service_cls.return_value.synthesize.assert_called_once()

    def test_sheet_repository_normalizes_omnivoice_voice_fields(self) -> None:
        repository = SheetRepository(SheetConfig("", ""), Path.cwd())

        voice = repository.normalize_voice(
            {
                "tts_engine": "omnivoice",
                "language": "vi",
                "speed": "1.25",
                "pitch": "0.5",
                "ref_text": "sample",
                "ref_audio_path": "runtime/ref.wav",
            }
        )

        self.assertEqual(voice["tts_engine"], "omnivoice")
        self.assertEqual(voice["language"], "vi")
        self.assertEqual(voice["speed"], 1.25)
        self.assertEqual(voice["ref_text"], "sample")


if __name__ == "__main__":
    unittest.main()
