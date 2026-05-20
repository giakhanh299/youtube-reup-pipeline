from __future__ import annotations

from pathlib import Path
import argparse
import shlex
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.render_service import RenderService


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview or run the FFmpeg render engine.")
    parser.add_argument("--input", default="runtime/test/test.mp4")
    parser.add_argument("--voice", default="runtime/test/test.mp3")
    parser.add_argument("--output", default="runtime/test/render_preview.mp4")
    parser.add_argument("--fit-mode", default="blur_bg", choices=["contain", "cover", "crop", "blur_bg"])
    parser.add_argument("--aspect", default="9:16", choices=["9:16", "16:9", "1:1"])
    parser.add_argument("--run", action="store_true", help="Run FFmpeg. Omit to print the command only.")
    args = parser.parse_args()

    sizes = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}
    width, height = sizes[args.aspect]
    cfg = {
        "fit_mode": args.fit_mode,
        "output_width": width,
        "output_height": height,
        "use_nvenc": False,
        "background_blur": args.fit_mode == "blur_bg",
    }
    service = RenderService()
    cmd = service.build_command(Path(args.input), Path(args.voice), Path(args.output), cfg)
    print(shlex.join(cmd))
    if args.run:
        service.render_video(Path(args.input), Path(args.voice), Path(args.output), cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
