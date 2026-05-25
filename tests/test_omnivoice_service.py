from __future__ import annotations

from pathlib import Path
import shutil
import unittest
import uuid
from unittest.mock import patch

from repositories.sheet_repository import SheetRepository
from processors.sheet_client import SheetConfig
from services.omnivoice_local_service import OmniVoiceLocalService, synthesize
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


class FakeGenerateModel:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def to(self, device):
        self.device = device
        return self

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


class OmniVoiceServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_roots: list[Path] = []

    def tearDown(self) -> None:
        for root in self.temp_roots:
            shutil.rmtree(root, ignore_errors=True)

    def _temp_root(self) -> Path:
        root = Path.cwd() / "runtime" / "test_omnivoice_service" / uuid.uuid4().hex
        root.mkdir(parents=True, exist_ok=True)
        self.temp_roots.append(root)
        return root

    def test_synthesize_uses_reference_audio_and_writes_output(self) -> None:
        temp = self._temp_root()
        ref = temp / "ref.wav"
        out = temp / "out.wav"
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
        temp = self._temp_root()
        ref = temp / "ref.wav"
        ref.write_bytes(b"")
        service = OmniVoiceService(model_loader=lambda _name: FakeOmniVoiceModel())

        with self.assertRaisesRegex(ValueError, "ref_audio_path is empty"):
            service.synthesize("text", temp / "out.wav", {"ref_audio_path": str(ref), "ref_text": "ref"})

    def test_model_without_generation_method_fails_clearly(self) -> None:
        temp = self._temp_root()
        ref = temp / "ref.wav"
        ref.write_bytes(b"ref")
        service = OmniVoiceService(model_loader=lambda _name: object())

        with self.assertRaisesRegex(OmniVoiceServiceError, "no supported"):
            service.synthesize("text", temp / "out.wav", {"ref_audio_path": str(ref), "ref_text": "ref"})

    def test_diagnostics_include_device_information(self) -> None:
        service = OmniVoiceService(device="cpu", dtype="float32")

        diagnostics = service.diagnostics()

        self.assertEqual(diagnostics["requested_device"], "cpu")
        self.assertEqual(diagnostics["resolved_device"], "cpu")
        self.assertEqual(diagnostics["dtype"], "float32")

    def test_missing_package_fails_clearly(self) -> None:
        temp = self._temp_root()
        ref = temp / "ref.wav"
        ref.write_bytes(b"ref")
        service = OmniVoiceService(model_loader=lambda _name: (_ for _ in ()).throw(ImportError("missing")))

        with self.assertRaisesRegex(OmniVoiceServiceError, "OmniVoice package/model is not available"):
            service.synthesize("text", temp / "out.wav", {"ref_audio_path": str(ref), "ref_text": "ref"})

    def test_tts_service_routes_omnivoice_engine(self) -> None:
        temp = self._temp_root()
        ref = temp / "ref.wav"
        out = temp / "out.wav"
        ref.write_bytes(b"ref")

        with patch("services.tts_service.OmniVoiceLocalService") as service_cls:
            service_cls.return_value.synthesize.side_effect = lambda _text, _ref, _ref_text, output, **_kwargs: output.write_bytes(b"wav")
            TTSService(settings={"omnivoice_device": "cpu", "voice_engine": "omnivoice_local"}).create_voice(
                "text",
                out,
                {"ref_audio_path": str(ref), "ref_text": "ref"},
            )

            self.assertEqual(out.read_bytes(), b"wav")
            service_cls.return_value.synthesize.assert_called_once()

    def test_tts_service_prefers_local_omnivoice_model_path(self) -> None:
        temp = self._temp_root()
        ref = temp / "ref.wav"
        out = temp / "out.wav"
        ref.write_bytes(b"ref")

        with patch("services.tts_service.OmniVoiceLocalService") as service_cls:
            service_cls.return_value.synthesize.side_effect = lambda _text, _ref, _ref_text, output, **_kwargs: output.write_bytes(b"wav")

            TTSService(
                settings={
                    "voice_engine": "omnivoice_local",
                    "omnivoice_model_path": r"D:\models\OmniVoice",
                    "omnivoice_model_name": "k2-fsa/OmniVoice",
                }
            ).create_voice(
                "text",
                out,
                {"ref_audio_path": str(ref), "ref_text": "ref"},
            )

            self.assertEqual(out.read_bytes(), b"wav")
            self.assertEqual(service_cls.call_args.kwargs["model_name"], r"D:\models\OmniVoice")

    def test_tts_service_default_omnivoice_does_not_require_google_key_dir(self) -> None:
        temp = self._temp_root()
        ref = temp / "ref.wav"
        out = temp / "out.wav"
        ref.write_bytes(b"ref")

        with patch("services.tts_service.OmniVoiceLocalService") as service_cls:
            service_cls.return_value.synthesize.side_effect = lambda _text, _ref, _ref_text, output, **_kwargs: output.write_bytes(b"wav")

            TTSService(settings={}).create_voice("text", out, {"ref_audio_path": str(ref), "ref_text": "ref"})

        self.assertEqual(out.read_bytes(), b"wav")

    def test_local_service_resolves_relative_paths_from_project_root(self) -> None:
        temp = self._temp_root()
        ref = temp / "ref.wav"
        out = temp / "nested" / "out.wav"
        ref.write_bytes(b"ref")
        model = FakeGenerateModel(b"wav")

        result = synthesize(
            "text",
            ref.relative_to(Path.cwd()),
            "ref",
            out.relative_to(Path.cwd()),
            model_loader=lambda _name, **_kwargs: model,
            device="cpu",
            verbose=False,
        )

        self.assertEqual(result, out.resolve())
        self.assertEqual(out.read_bytes(), b"wav")
        self.assertEqual(Path(model.calls[0]["ref_audio_path"]), ref.resolve())

    def test_local_service_creates_output_parent_from_tuple_result(self) -> None:
        temp = self._temp_root()
        ref = temp / "ref.wav"
        source = temp / "source.wav"
        out = temp / "missing" / "out.wav"
        ref.write_bytes(b"ref")
        source.write_bytes(b"wav")
        model = FakeGenerateModel((None, {"audio_path": str(source)}))

        OmniVoiceLocalService(model_loader=lambda _name, **_kwargs: model, device="cpu").synthesize(
            "text",
            ref,
            "ref",
            out,
        )

        self.assertEqual(out.read_bytes(), b"wav")

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
