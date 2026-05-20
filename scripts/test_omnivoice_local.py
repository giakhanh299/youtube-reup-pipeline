from __future__ import annotations

from pathlib import Path
import argparse
import faulthandler
import json
import platform
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOCAL_OMNIVOICE = ROOT / "OmniVoice"
if LOCAL_OMNIVOICE.exists() and str(LOCAL_OMNIVOICE) not in sys.path:
    sys.path.insert(0, str(LOCAL_OMNIVOICE))

from configs.config_loader import ConfigLoader
from services.omnivoice_local_service import _resolve_device, _resolve_project_path, synthesize


def print_line(message: str) -> None:
    print(message, flush=True)


def runtime_diagnostics(args: argparse.Namespace, model_name: str, local_files_only: bool) -> dict:
    ref_audio = _resolve_project_path(args.ref_audio)
    output = _resolve_project_path(args.output)
    info = {
        "platform": platform.platform(),
        "executable": sys.executable,
        "cwd": str(Path.cwd()),
        "repo_root": str(ROOT),
        "local_omnivoice_dir_exists": LOCAL_OMNIVOICE.exists(),
        "model_name": model_name,
        "local_files_only": local_files_only,
        "device": _resolve_device(args.device or "auto"),
        "ref_audio": str(ref_audio),
        "ref_audio_exists": ref_audio.exists(),
        "output": str(output),
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local OmniVoice synthesis from cached model files by default.")
    parser.add_argument("--text", required=True)
    parser.add_argument("--ref-audio", required=True)
    parser.add_argument("--ref-text", required=True)
    parser.add_argument("--output", default="runtime/test/omnivoice_test.wav")
    parser.add_argument("--language", default="")
    parser.add_argument("--speed", default="1.0")
    parser.add_argument("--pitch", default="0")
    parser.add_argument("--allow-download", action="store_true")
    parser.add_argument("--model-name", default="")
    parser.add_argument("--device", default="")
    args = parser.parse_args()

    log_dir = ROOT / "runtime" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    crash_log = log_dir / "omnivoice_native_crash.log"
    with crash_log.open("a", encoding="utf-8") as crash_handle:
        faulthandler.enable(file=crash_handle, all_threads=True)
        try:
            print_line("OmniVoice local diagnostic startup")
            settings = ConfigLoader(ROOT).load_settings()
            model_name = args.model_name or settings.get("omnivoice_model_name", "k2-fsa/OmniVoice")
            local_files_only = not args.allow_download
            language = args.language or settings.get("omnivoice_default_language", "vi")
            print_line(json.dumps(runtime_diagnostics(args, model_name, local_files_only), ensure_ascii=False, indent=2))
            output = synthesize(
                args.text,
                args.ref_audio,
                args.ref_text,
                args.output,
                language=language,
                speed=args.speed,
                pitch=args.pitch,
                model_name=model_name,
                local_files_only=local_files_only,
                device=args.device or settings.get("omnivoice_device", "auto"),
                verbose=True,
            )
            print_line(f"OK OmniVoice output: {output.resolve()} ({output.stat().st_size} bytes)")
            return 0
        except BaseException as exc:
            print_line(f"ERROR {type(exc).__name__}: {exc}")
            traceback.print_exc()
            print_line(f"Native crash trace, if any, is written to: {crash_log}")
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
