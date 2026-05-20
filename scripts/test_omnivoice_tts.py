from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import shutil
import time
import numpy as np


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
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        ref_audio_path = Path(str(voice_cfg.get("ref_audio_path", "")).strip())

        if not ref_audio_path.exists():
            raise FileNotFoundError(
                f"OmniVoice ref_audio_path not found: {ref_audio_path}"
            )

        ref_text = str(voice_cfg.get("ref_text", "")).strip()

        if not ref_text:
            raise ValueError("OmniVoice ref_text is required")

        model = self._load_model()
        started_at = time.time()

        kwargs = {
            "text": text,
            "ref_audio_path": str(ref_audio_path),
            "ref_text": ref_text,
            "language": voice_cfg.get("language")
            or voice_cfg.get("language_code", "vi"),
            "speed": _to_float(
                voice_cfg.get("speed", voice_cfg.get("speaking_rate")),
                1.0,
            ),
            "pitch": _to_float(voice_cfg.get("pitch"), 0.0),
            "output_path": str(output_file),
        }

        errors: list[str] = []

        for method_name in ("synthesize", "generate", "infer", "tts"):
            method = getattr(model, method_name, None)

            if not callable(method):
                continue

            try:
                print(f"[OmniVoice] Trying method: {method_name}")
                result = method(**kwargs)

            except TypeError:
                try:
                    result = method(
                        text,
                        ref_audio_path=str(ref_audio_path),
                        ref_text=ref_text,
                        output_path=str(output_file),
                    )

                except Exception as exc:
                    errors.append(
                        f"{method_name}: {type(exc).__name__}: {exc}"
                    )
                    continue

            except Exception as exc:
                errors.append(
                    f"{method_name}: {type(exc).__name__}: {exc}"
                )
                continue

            print(f"[OmniVoice] Result type from {method_name}: {type(result)}")

            self._persist_result(result, output_file)

            if output_file.exists() and output_file.stat().st_size > 0:
                return

            newest_wav = self._find_newest_wav(
                output_file.parent,
                started_at,
            )

            if newest_wav and newest_wav.exists():
                shutil.copy2(newest_wav, output_file)

                if (
                    output_file.exists()
                    and output_file.stat().st_size > 0
                ):
                    print(
                        f"[OmniVoice] Copied generated wav from: {newest_wav}"
                    )
                    return

            errors.append(
                f"{method_name}: finished but no output file created"
            )

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
            for key in (
                "audio",
                "audio_path",
                "path",
                "output",
                "output_path",
                "wav",
            ):
                value = result.get(key)

                if value is not None:
                    self._persist_result(value, output_file)

                    if output_file.exists():
                        return

        if isinstance(result, (list, tuple)):
            print(f"[OmniVoice] List result length: {len(result)}")
            print(
                f"[OmniVoice] List item types: "
                f"{[type(x) for x in result[:5]]}"
            )

            if len(result) == 2:
                a, b = result

                if isinstance(a, int):
                    sample_rate = a
                    audio = b

                elif isinstance(b, int):
                    sample_rate = b
                    audio = a

                else:
                    sample_rate = 24000
                    audio = a

                self._write_audio_array(
                    audio,
                    output_file,
                    sample_rate,
                )
                return

            if len(result) > 0:
                try:
                    audio = np.concatenate(
                        [np.asarray(x).reshape(-1) for x in result]
                    )

                    self._write_audio_array(
                        audio,
                        output_file,
                        24000,
                    )
                    return

                except Exception:
                    pass

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

        self._write_audio_array(result, output_file, 24000)

    def _write_audio_array(
        self,
        audio: Any,
        output_file: Path,
        sample_rate: int = 24000,
    ) -> None:
        try:
            import torch

            if isinstance(audio, torch.Tensor):
                audio = audio.detach().cpu().numpy()

        except Exception:
            pass

        audio_np = np.asarray(audio)

        if audio_np.size == 0:
            return

        audio_np = audio_np.squeeze()

        if audio_np.ndim > 1:
            audio_np = audio_np.reshape(-1)

        audio_np = audio_np.astype("float32")

        try:
            import soundfile as sf

            sf.write(str(output_file), audio_np, sample_rate)
            return

        except Exception:
            pass

        try:
            from scipy.io import wavfile

            clipped = np.clip(audio_np, -1.0, 1.0)
            pcm16 = (clipped * 32767).astype("int16")

            wavfile.write(
                str(output_file),
                sample_rate,
                pcm16,
            )
            return

        except Exception as exc:
            raise OmniVoiceServiceError(
                f"Failed to write audio array to wav: {exc}"
            ) from exc

    def _find_newest_wav(
        self,
        folder: Path,
        started_at: float,
    ) -> Path | None:
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

        return max(
            candidates,
            key=lambda p: p.stat().st_mtime,
        )