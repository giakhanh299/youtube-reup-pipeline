from __future__ import annotations

from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from configs.config_loader import ConfigLoader
from services.tts_service import TTSService


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an OmniVoice clone TTS test.")
    parser.add_argument("--text", required=True)
    parser.add_argument("--ref-audio", required=True)
    parser.add_argument("--ref-text", required=True)
    parser.add_argument("--output", default="runtime/test/omnivoice_test.wav")
    parser.add_argument("--language", default="vi")
    parser.add_argument("--speed", default="1.0")
    parser.add_argument("--pitch", default="0")
    args = parser.parse_args()

    settings = ConfigLoader(ROOT).load_settings()
    voice_cfg = {
        "tts_engine": "omnivoice",
        "ref_audio_path": args.ref_audio,
        "ref_text": args.ref_text,
        "language": args.language,
        "speed": args.speed,
        "pitch": args.pitch,
    }
    output = Path(args.output)
    TTSService(settings=settings).create_voice(args.text, output, voice_cfg, settings.get("google_key_dir", ""))
    print(f"OK OmniVoice output: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
