from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
import shutil
import sys
import time
import wave


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_NAME = "k2-fsa/OmniVoice"


class OmniVoiceLocalServiceError(RuntimeError):
    pass


def _resolve_project_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (ROOT / path).resolve()


def _to_float(value: Any, default: float) -> float:
    try:
        if value is None or value == "":
            return default
        return float(str(value).replace(",", "."))
    except Exception:
        return default


def _resolve_device(device: str = "auto") -> str:
    if device and device != "auto":
        return device
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def _load_omnivoice_class() -> Any:
    try:
        from omnivoice import OmniVoice
    except Exception:
        from OmniVoice import OmniVoice
    return OmniVoice


def _move_model_to_device(model: Any, device: str) -> Any:
    to_method = getattr(model, "to", None)
    if not callable(to_method):
        return model
    try:
        return to_method(device)
    except TypeError:
        return to_method(device=device)


def _write_array_wav(audio: Any, output_path: Path, sample_rate: int = 24000) -> None:
    try:
        import numpy as np
    except Exception as exc:
        raise OmniVoiceLocalServiceError("Saving array audio requires numpy to be installed") from exc

    array = np.asarray(audio)
    if array.size == 0:
        return
    array = np.squeeze(array)
    if array.ndim == 1:
        channels = 1
    elif array.ndim == 2:
        if array.shape[0] <= 8 and array.shape[1] > array.shape[0]:
            array = array.T
        channels = int(array.shape[1])
    else:
        raise OmniVoiceLocalServiceError(f"Unsupported audio array shape: {array.shape}")

    if array.dtype.kind == "f":
        array = np.clip(array, -1.0, 1.0)
        pcm = (array * 32767.0).astype("<i2")
    else:
        pcm = array.astype("<i2")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(int(sample_rate))
        wav.writeframes(pcm.tobytes())


def _persist_result(result: Any, output_path: Path, sample_rate: int = 24000) -> None:
    if result is None:
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(result, (bytes, bytearray)):
        output_path.write_bytes(result)
        return

    if isinstance(result, (str, Path)):
        source = _resolve_project_path(result)
        if source.exists() and source != output_path:
            shutil.copy2(source, output_path)
        return

    if isinstance(result, dict):
        result_sample_rate = int(_to_float(result.get("sample_rate", result.get("sampling_rate")), sample_rate))
        for key in ("audio", "wav", "waveform", "samples", "audio_path", "path", "output", "output_path"):
            if key in result and result[key] is not None:
                _persist_result(result[key], output_path, result_sample_rate)
                if output_path.exists() and output_path.stat().st_size > 0:
                    return
        return

    if isinstance(result, (list, tuple)):
        for item in result:
            _persist_result(item, output_path, sample_rate)
            if output_path.exists() and output_path.stat().st_size > 0:
                return
        return

    detach = getattr(result, "detach", None)
    if callable(detach):
        tensor = detach()
        cpu = getattr(tensor, "cpu", None)
        if callable(cpu):
            tensor = cpu()
        numpy_method = getattr(tensor, "numpy", None)
        if callable(numpy_method):
            _write_array_wav(numpy_method(), output_path, sample_rate)
            return

    if "numpy" in sys.modules:
        import numpy as np

        if isinstance(result, np.ndarray):
            _write_array_wav(result, output_path, sample_rate)
            return

    save_method = getattr(result, "save", None)
    if callable(save_method):
        save_method(str(output_path))
        return

    write_method = getattr(result, "write", None)
    if callable(write_method):
        write_method(str(output_path))


def _find_newest_wav(folder: Path, started_at: float) -> Path | None:
    candidates: list[Path] = []
    for root in (folder, ROOT / "runtime", ROOT / "outputs", ROOT / "output", ROOT / "temp", ROOT / "tmp"):
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
    return max(candidates, key=lambda path: path.stat().st_mtime)


def synthesize(
    text: str,
    ref_audio_path: str | Path,
    ref_text: str,
    output_path: str | Path,
    language: str = "vi",
    speed: float = 1.0,
    pitch: float = 0.0,
    model_name: str = DEFAULT_MODEL_NAME,
    local_files_only: bool = True,
    device: str = "auto",
    model_loader: Callable[..., Any] | None = None,
    verbose: bool = True,
) -> Path:
    ref_audio = _resolve_project_path(ref_audio_path)
    output = _resolve_project_path(output_path)
    if not str(text).strip():
        raise ValueError("OmniVoice text is required")
    if not ref_audio.exists():
        raise FileNotFoundError(f"OmniVoice ref_audio_path not found: {ref_audio}")
    if not ref_audio.is_file():
        raise ValueError(f"OmniVoice ref_audio_path is not a file: {ref_audio}")
    if ref_audio.stat().st_size <= 0:
        raise ValueError(f"OmniVoice ref_audio_path is empty: {ref_audio}")
    if not str(ref_text).strip():
        raise ValueError("OmniVoice ref_text is required")

    resolved_device = _resolve_device(device)
    if verbose:
        print(f"[OmniVoiceLocal] Loading model: {model_name}", flush=True)
        print(f"[OmniVoiceLocal] Using {'CUDA' if resolved_device == 'cuda' else 'CPU'}", flush=True)

    try:
        if model_loader:
            model = model_loader(model_name, local_files_only=local_files_only)
        else:
            OmniVoice = _load_omnivoice_class()
            model = OmniVoice.from_pretrained(model_name, local_files_only=local_files_only)
    except Exception as exc:
        raise OmniVoiceLocalServiceError(
            "OmniVoice package/model is not available locally. "
            "Install/cache the model or rerun with downloads explicitly allowed."
        ) from exc

    model = _move_model_to_device(model, resolved_device)
    output.parent.mkdir(parents=True, exist_ok=True)
    started_at = time.time()
    kwargs = {
        "text": str(text),
        "ref_audio_path": str(ref_audio),
        "ref_text": str(ref_text),
        "output_path": str(output),
        "language": language or "vi",
        "speed": _to_float(speed, 1.0),
        "pitch": _to_float(pitch, 0.0),
    }

    errors: list[str] = []
    for method_name in ("generate", "synthesize", "infer", "tts"):
        method = getattr(model, method_name, None)
        if not callable(method):
            continue
        try:
            if verbose:
                print(f"[OmniVoiceLocal] Generating audio", flush=True)
                print(f"[OmniVoiceLocal] Output path: {output}", flush=True)
            result = method(**kwargs)
        except TypeError as exc1:
            try:
                result = method(str(text), str(ref_audio), str(ref_text), str(output))
            except Exception as exc2:
                errors.append(f"{method_name}: {type(exc2).__name__}: {exc2}")
                continue
        except Exception as exc:
            errors.append(f"{method_name}: {type(exc).__name__}: {exc}")
            continue

        _persist_result(result, output)
        if output.exists() and output.stat().st_size > 0:
            return output

        newest_wav = _find_newest_wav(output.parent, started_at)
        if newest_wav:
            shutil.copy2(newest_wav, output)
            if output.exists() and output.stat().st_size > 0:
                return output
        errors.append(f"{method_name}: finished but no output file created")

    raise OmniVoiceLocalServiceError(
        "OmniVoice local generation failed or did not create output file. "
        f"Expected output: {output}. Errors: {errors}"
    )


class OmniVoiceLocalService:
    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        local_files_only: bool = True,
        device: str = "auto",
        model_loader: Callable[..., Any] | None = None,
        verbose: bool = False,
    ):
        self.model_name = model_name or DEFAULT_MODEL_NAME
        self.local_files_only = local_files_only
        self.device = device or "auto"
        self.model_loader = model_loader
        self.verbose = verbose

    def synthesize(
        self,
        text: str,
        ref_audio_path: str | Path,
        ref_text: str,
        output_path: str | Path,
        language: str = "vi",
        speed: float = 1.0,
        pitch: float = 0.0,
    ) -> Path:
        return synthesize(
            text,
            ref_audio_path,
            ref_text,
            output_path,
            language=language,
            speed=speed,
            pitch=pitch,
            model_name=self.model_name,
            local_files_only=self.local_files_only,
            device=self.device,
            model_loader=self.model_loader,
            verbose=self.verbose,
        )
