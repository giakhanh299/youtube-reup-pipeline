from __future__ import annotations

from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from configs.config_loader import ConfigLoader
from logs.structured_logger import StructuredLogger
from services.active_channel_state import ActiveChannelStateStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Finish the selected channel session and release the active-channel lock.")
    parser.add_argument("--force-clean", action="store_true", help="Clean configured runtime work folders before releasing the lock.")
    args = parser.parse_args()

    settings = ConfigLoader(ROOT).load_settings()
    logger = StructuredLogger(ROOT / settings.get("log_dir", "runtime/logs"))
    ActiveChannelStateStore(ROOT, settings, logger=logger).finish(force_clean=args.force_clean)
    print("active channel finished")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
