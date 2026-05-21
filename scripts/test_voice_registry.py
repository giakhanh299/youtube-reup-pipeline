from __future__ import annotations

from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from configs.config_loader import ConfigLoader
from services.voice_registry import list_voice_files, resolve_voice_path


def main() -> int:
    parser = argparse.ArgumentParser(description="List and resolve local OmniVoice reference voices.")
    parser.add_argument("--voice", default="", help="Voice filename under runtime/voices")
    args = parser.parse_args()

    settings = ConfigLoader(ROOT).load_settings()
    voices_dir = ROOT / settings.get("voices_dir", "runtime/voices")
    default_voice_name = settings.get("default_voice_name", "")
    voices_dir.mkdir(parents=True, exist_ok=True)

    voices = list_voice_files(voices_dir)
    print(f"voices_dir: {voices_dir.resolve()}")
    print("available voices:")
    if voices:
        for voice in voices:
            print(f"- {voice}")
    else:
        print("- none")

    voice_name = args.voice or default_voice_name
    if voice_name:
        resolved = resolve_voice_path(voice_name, voices_dir, default_voice_name)
        print(f"resolved voice: {resolved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
