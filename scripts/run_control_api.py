from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from configs.config_loader import ConfigLoader
from services.control_api import create_app, load_control_settings


def main() -> int:
    settings = load_control_settings(ROOT)
    host = str(settings.get("control_api_host", settings.get("dashboard_host", "127.0.0.1")))
    port = int(settings.get("control_api_port", 8000))
    try:
        import uvicorn
    except ImportError:
        print("ERROR: install FastAPI runtime dependencies with: pip install -r requirements.txt", file=sys.stderr)
        return 1

    uvicorn.run(create_app(ROOT, settings), host=host, port=port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
