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
from services.omnivoice_service import OmniVoiceService
from services.tts_service import TTSService


def print_line(message: str) -> None:
    print(message, flush=True)


def runtime_diagnostics(service: OmniVoiceService, args: argparse.Namespace) -> dict:
    info = {
        "platform": platform.platform(),
        "executable": sys.executable,
        "cwd": str(Path.cwd()),
        "repo_root": str(ROOT),
        "local_omnivoice_dir_exists": LOCAL_OMNIVOICE.exists(),
        "ref_audio": str(Path(args.ref_audio).resolve()),
        "ref_audio_exists": Path(args.ref_audio).exists(),
        "output": str(Path(args.output).resolve()),
        **service.diagnostics(),
    }
    return info


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an OmniVoice clone TTS test with diagnostics.")
    parser.add_argument("--text", required=True)
    parser.add_argument("--ref-audio", required=True)
    parser.add_argument("--ref-text", required=True)
    parser.add_argument("--output", default="runtime/test/omnivoice_test.wav")
    parser.add_argument("--language", default="vi")
    parser.add_argument("--speed", default="1.0")
    parser.add_argument("--pitch", default="0")
    parser.add_argument("--model-name", default="")
    parser.add_argument("--device", default="")
    parser.add_argument("--dtype", default="")
    args = parser.parse_args()

    log_dir = ROOT / "runtime" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    crash_log = log_dir / "omnivoice_native_crash.log"
    with crash_log.open("a", encoding="utf-8") as crash_handle:
        faulthandler.enable(file=crash_handle, all_threads=True)
        try:
            print_line("OmniVoice diagnostic startup")
            settings = ConfigLoader(ROOT).load_settings()
            model_name = args.model_name or settings.get("omnivoice_model_name", "k2-fsa/OmniVoice")
            device = args.device or settings.get("omnivoice_device", "auto")
            dtype = args.dtype or settings.get("omnivoice_dtype", "auto")
            diagnostic_service = OmniVoiceService(model_name=model_name, device=device, dtype=dtype, verbose=True)
            print_line(json.dumps(runtime_diagnostics(diagnostic_service, args), ensure_ascii=False, indent=2))

            ref_audio = Path(args.ref_audio)
            if not ref_audio.exists():
                raise FileNotFoundError(f"Reference audio not found: {ref_audio}")
            if not ref_audio.is_file():
                raise ValueError(f"Reference audio is not a file: {ref_audio}")
            if ref_audio.stat().st_size <= 0:
                raise ValueError(f"Reference audio is empty: {ref_audio}")

            output = Path(args.output)
            voice_cfg = {
                "tts_engine": "omnivoice",
                "ref_audio_path": str(ref_audio),
                "ref_text": args.ref_text,
                "language": args.language,
                "speed": args.speed,
                "pitch": args.pitch,
                "omnivoice_model_name": model_name,
                "omnivoice_device": device,
                "omnivoice_dtype": dtype,
            }
            print_line("Starting OmniVoice synthesis")
            TTSService(settings=settings).create_voice(args.text, output, voice_cfg, settings.get("google_key_dir", ""))
            if not output.exists() or output.stat().st_size <= 0:
                raise RuntimeError(f"OmniVoice completed but output is missing or empty: {output}")
            print_line(f"OK OmniVoice output: {output.resolve()} ({output.stat().st_size} bytes)")
            return 0
        except BaseException as exc:
            print_line(f"ERROR {type(exc).__name__}: {exc}")
            traceback.print_exc()
            print_line(f"Native crash trace, if any, is written to: {crash_log}")
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
