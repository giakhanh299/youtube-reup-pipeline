from __future__ import annotations

from pathlib import Path
import importlib
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_runtime import main as check_runtime_main


REQUIRED_MODULES = [
    "pipeline",
    "configs.config_loader",
    "logs.structured_logger",
    "repositories.sheet_repository",
    "repositories.queue_persistence",
    "services.text_service",
    "services.tts_service",
    "services.render_service",
    "services.scheduler_service",
    "services.dashboard_service",
    "processors.folder_processor",
    "processors.queue_processor",
    "processors.sheet_upload_processor",
    "processors.douyin_render_processor",
    "integrations.selenium.browser_manager",
    "integrations.telegram.notifier",
    "integrations.youtube.youtube_api_uploader",
    "workers.upload_worker",
    "workers.multi_account_upload_worker",
    "scripts.scheduler_daemon",
    "scripts.dashboard",
    "scripts.export_sheet_snapshot",
]


def main() -> int:
    print("Docker smoke test starting")
    for module_name in REQUIRED_MODULES:
        importlib.import_module(module_name)
        print(f"OK import: {module_name}")

    check_runtime_main()
    print("Docker smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
