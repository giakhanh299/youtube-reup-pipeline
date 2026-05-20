from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


class OmniVoiceServiceError(RuntimeError):
    pass


def _to_float(value: Any, default: float) -> float:
    try:
        if value is None or value == "":
            return default
        return float(str(value).replace(",", "."))
    except Exception:
        return default


class OmniVoiceService:
    """Lazy OmniVoice adapter for voice clone TTS."""

    def __init__(
        self,
        model_name: str = "k2-fsa/OmniVoice",
        device: str = "auto",
        dtype: str = "auto",
        model_loader: Callable[[str], Any] | None = None,
    ):
        self.model_name = model_name or "k2-fsa/OmniVoice"
        self.device = device or "auto"
        self.dtype = dtype or "auto"
        self.model_loader = model_loader
        self._model: Any = None

    def _resolve_device(self) -> str:
        if self.device != "auto":
            return self.device

        try:
            import torch

            return "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cpu"

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model

        try:
            if self.model_loader:
                model = self.model_loader(self.model_name)
            else:
                from omnivoice import OmniVoice

                model = OmniVoice.from_pretrained(self.model_name)
        except Exception as exc:
            raise OmniVoiceServiceError(
                "OmniVoice package/model is not available. "
                "Install the correct OmniVoice package/model and ensure it can be loaded."
            ) from exc

        device = self._resolve_device()
        to_method = getattr(model, "to", None)

        if callable(to_method):
            try:
                model = to_method(device)
            except TypeError:
                model = to_method(device=device)

        self._model = model
        return model

    def synthesize(self, text: str, output_file: Path, voice_cfg: dict) -> None:
        ref_audio_path = Path(str(voice_cfg.get("ref_audio_path", "")).strip())

        if not ref_audio_path.exists():
            raise FileNotFoundError(
                f"OmniVoice ref_audio_path not found: {ref_audio_path}"
            )

        ref_text = str(voice_cfg.get("ref_text", "")).strip()

        if not ref_text:
            raise ValueError("OmniVoice ref_text is required")

        output_file.parent.mkdir(parents=True, exist_ok=True)
        model = self._load_model()

        kwargs = {
            "text": text,
            "ref_audio_path": str(ref_audio_path),
            "ref_text": ref_text,
            "language": voice_cfg.get("language") or voice_cfg.get("language_code", "vi"),
            "speed": _to_float(
                voice_cfg.get("speed", voice_cfg.get("speaking_rate")),
                1.0,
            ),
            "pitch": _to_float(voice_cfg.get("pitch"), 0.0),
            "output_path": str(output_file),
        }

        for method_name in ("synthesize", "generate", "infer", "tts"):
            method = getattr(model, method_name, None)

            if not callable(method):
                continue

            try:
                result = method(**kwargs)
            except TypeError:
                result = method(
                    text,
                    ref_audio_path=str(ref_audio_path),
                    ref_text=ref_text,
                    output_path=str(output_file),
                )

            self._persist_result(result, output_file)

            if output_file.exists():
                return

            raise OmniVoiceServiceError(
                "OmniVoice generation finished but did not create the output file"
            )

        raise OmniVoiceServiceError(
            "Loaded OmniVoice model does not expose synthesize/generate/infer/tts"
        )

    def _persist_result(self, result: Any, output_file: Path) -> None:
        if result is None:
            return

        if isinstance(result, (bytes, bytearray)):
            output_file.write_bytes(result)
            return

        if isinstance(result, (str, Path)):
            source = Path(result)

            if source.exists() and source != output_file:
                output_file.write_bytes(source.read_bytes())

            return

        save_method = getattr(result, "save", None)

        if callable(save_method):
            save_method(str(output_file))