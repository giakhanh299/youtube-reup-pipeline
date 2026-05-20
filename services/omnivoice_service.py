from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
import shutil
import sys
import time


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
        local_files_only: bool = True,
        model_loader: Callable[[str], Any] | None = None,
        verbose: bool = False,
    ):
        self.model_name = model_name or "k2-fsa/OmniVoice"
        self.device = device or "auto"
        self.dtype = dtype or "auto"
        self.local_files_only = local_files_only
        self.model_loader = model_loader
        self.verbose = verbose
        self._model: Any = None

    def _log(self, message: str) -> None:
        if self.verbose:
            print(f"[OmniVoice] {message}", flush=True)

    def diagnostics(self) -> dict[str, Any]:
        info: dict[str, Any] = {
            "python": sys.version.replace("\n", " "),
            "model_name": self.model_name,
            "requested_device": self.device,
            "resolved_device": self._resolve_device(),
            "dtype": self.dtype,
        }
        try:
            import torch

            info["torch_version"] = getattr(torch, "__version__", "")
            info["cuda_available"] = bool(torch.cuda.is_available())
            info["cuda_device_count"] = int(torch.cuda.device_count()) if torch.cuda.is_available() else 0
            if torch.cuda.is_available():
                info["cuda_device_name"] = torch.cuda.get_device_name(0)
        except Exception as exc:
            info["torch_error"] = f"{type(exc).__name__}: {exc}"
        return info

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
                try:
                    from omnivoice import OmniVoice
                except Exception:
                    from OmniVoice import OmniVoice

                self._log(f"Loading model: {self.model_name}")
                model = OmniVoice.from_pretrained(self.model_name, local_files_only=self.local_files_only)
        except Exception as exc:
            raise OmniVoiceServiceError(
                "OmniVoice package/model is not available. "
                "Install the correct OmniVoice package/model and ensure it can be loaded."
            ) from exc

        device = self._resolve_device()
        self._log(f"Using device: {device}")
        to_method = getattr(model, "to", None)

        if callable(to_method):
            try:
                model = to_method(device)
            except TypeError:
                model = to_method(device=device)

        self._model = model
        callable_methods = [name for name in ("synthesize", "generate", "infer", "tts") if callable(getattr(model, name, None))]
        if not callable_methods:
            raise OmniVoiceServiceError("Loaded OmniVoice model has no supported synthesize/generate/infer/tts method")
        self._log(f"Available generation methods: {callable_methods}")
        return model

    def synthesize(self, text: str, output_file: Path, voice_cfg: dict) -> None:
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        ref_audio_path = Path(str(voice_cfg.get("ref_audio_path", "")).strip())

        if not ref_audio_path.exists():
            raise FileNotFoundError(f"OmniVoice ref_audio_path not found: {ref_audio_path}")
        if not ref_audio_path.is_file():
            raise ValueError(f"OmniVoice ref_audio_path is not a file: {ref_audio_path}")
        if ref_audio_path.stat().st_size <= 0:
            raise ValueError(f"OmniVoice ref_audio_path is empty: {ref_audio_path}")

        ref_text = str(voice_cfg.get("ref_text", "")).strip()

        if not ref_text:
            raise ValueError("OmniVoice ref_text is required")

        model = self._load_model()
        started_at = time.time()
        self._log(f"Reference audio: {ref_audio_path}")
        self._log(f"Output file: {output_file}")

        kwargs = {
            "text": text,
            "ref_audio_path": str(ref_audio_path),
            "ref_text": ref_text,
            "language": voice_cfg.get("language") or voice_cfg.get("language_code", "vi"),
            "speed": _to_float(voice_cfg.get("speed", voice_cfg.get("speaking_rate")), 1.0),
            "pitch": _to_float(voice_cfg.get("pitch"), 0.0),
            "output_path": str(output_file),
        }

        errors: list[str] = []

        for method_name in ("synthesize", "generate", "infer", "tts"):
            method = getattr(model, method_name, None)

            if not callable(method):
                continue

            try:
                self._log(f"Trying method: {method_name}")
                result = method(**kwargs)
            except TypeError as exc1:
                try:
                    result = method(
                        text,
                        ref_audio_path=str(ref_audio_path),
                        ref_text=ref_text,
                        output_path=str(output_file),
                    )
                except Exception as exc2:
                    errors.append(f"{method_name}: {type(exc2).__name__}: {exc2}")
                    continue
            except Exception as exc:
                errors.append(f"{method_name}: {type(exc).__name__}: {exc}")
                continue

            self._log(f"Result type from {method_name}: {type(result)}")
            self._persist_result(result, output_file)

            if output_file.exists() and output_file.stat().st_size > 0:
                return

            newest_wav = self._find_newest_wav(output_file.parent, started_at)

            if newest_wav and newest_wav.exists():
                shutil.copy2(newest_wav, output_file)
                if output_file.exists() and output_file.stat().st_size > 0:
                    print(f"[OmniVoice] Copied generated wav from: {newest_wav}")
                    return

            errors.append(f"{method_name}: finished but no output file created")

        raise OmniVoiceServiceError(
            "OmniVoice generation failed or did not create output file.\n"
            f"Expected output: {output_file}\n"
            f"Tried errors: {errors}"
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
                shutil.copy2(source, output_file)

            return

        if isinstance(result, dict):
            for key in ("audio", "audio_path", "path", "output", "output_path", "wav"):
                value = result.get(key)

                if value is not None:
                    self._persist_result(value, output_file)
                    if output_file.exists():
                        return

        if isinstance(result, (list, tuple)):
            for item in result:
                self._persist_result(item, output_file)
                if output_file.exists():
                    return

        save_method = getattr(result, "save", None)

        if callable(save_method):
            save_method(str(output_file))
            return

        write_method = getattr(result, "write", None)

        if callable(write_method):
            write_method(str(output_file))
            return

    def _find_newest_wav(self, folder: Path, started_at: float) -> Path | None:
        candidates: list[Path] = []

        search_roots = [
            folder,
            Path.cwd(),
            Path("runtime"),
            Path("outputs"),
            Path("output"),
            Path("temp"),
            Path("tmp"),
        ]

        for root in search_roots:
            if not root.exists():
                continue

            try:
                for wav in root.rglob("*.wav"):
                    try:
                        if wav.stat().st_mtime >= started_at:
                            candidates.append(wav)
                    except OSError:
                        pass
            except OSError:
                pass

        if not candidates:
            return None

        return max(candidates, key=lambda p: p.stat().st_mtime)
