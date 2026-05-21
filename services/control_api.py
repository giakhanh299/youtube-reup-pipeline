from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import os
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Request

from configs.config_loader import ConfigLoader, load_env_file
from logs.structured_logger import NullLogger
from services.dashboard_service import DashboardStateBuilder


ROOT = Path(__file__).resolve().parents[1]
CONTROL_ACTIONS = {"run", "pause", "resume", "retry", "render", "upload", "sheet", "logs"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_chat_ids(value: Any) -> set[str]:
    if isinstance(value, (list, tuple, set)):
        return {str(item).strip() for item in value if str(item).strip()}
    return {item.strip() for item in str(value or "").split(",") if item.strip()}


def _safe_setting(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    path_like = any(marker in text.lower() for marker in ("secret", "token", "credential", ".json", ".pickle"))
    if path_like:
        return "[configured]"
    return text


def load_control_settings(root: str | Path = ROOT) -> dict:
    root_path = Path(root)
    settings = ConfigLoader(root_path).load_settings()
    file_env = load_env_file(root_path / ".env")
    merged_env = {**file_env, **os.environ}
    for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_CHAT_IDS", "PUBLIC_WEBHOOK_URL"):
        if key in merged_env:
            settings[key] = merged_env[key]
        yt_key = f"YT_{key}"
        if yt_key in merged_env and key not in settings:
            settings[key] = merged_env[yt_key]
    return settings


@dataclass(frozen=True)
class ControlEvent:
    action: str
    job_id: str = ""
    ts: str = ""


class ControlStateStore:
    """Persists Telegram control state without storing secrets."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.state_dir = self.root / "runtime" / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.state_dir / "control_state.json"
        self.events_path = self.state_dir / "control_events.jsonl"

    def load(self) -> dict:
        if not self.state_path.exists():
            return {"paused": False, "last_action": "", "last_job_id": "", "updated_at": ""}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return {"paused": False, "last_action": "", "last_job_id": "", "updated_at": ""}

    def record(self, action: str, job_id: str = "") -> ControlEvent:
        if action not in CONTROL_ACTIONS:
            raise ValueError(f"unsupported control action: {action}")
        ts = _utc_now()
        event = ControlEvent(action=action, job_id=job_id, ts=ts)
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.__dict__, ensure_ascii=False) + "\n")
        state = self.load()
        if action == "pause":
            state["paused"] = True
        elif action == "resume":
            state["paused"] = False
        state.update({"last_action": action, "last_job_id": job_id, "updated_at": ts})
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return event


class TelegramControlHandler:
    """Handles Telegram commands with injectable action callbacks."""

    def __init__(
        self,
        root: str | Path,
        settings: dict,
        state_store: ControlStateStore | None = None,
        state_builder: DashboardStateBuilder | None = None,
        action_runner: Callable[[str, str], str] | None = None,
        logger: Any = None,
    ):
        self.root = Path(root)
        self.settings = settings
        self.state_store = state_store or ControlStateStore(root)
        self.state_builder = state_builder or DashboardStateBuilder(root)
        self.action_runner = action_runner
        self.logger = logger or NullLogger()

    def is_authorized(self, chat_id: Any) -> bool:
        allowed = _parse_chat_ids(self.settings.get("TELEGRAM_ALLOWED_CHAT_IDS"))
        return bool(allowed) and str(chat_id).strip() in allowed

    def handle(self, text: str) -> str:
        command, argument = self._parse_command(text)
        if command == "/help":
            return self.help_text()
        if command == "/status":
            return self.status_text()
        if command == "/logs":
            return self.logs_text()
        if command == "/sheet":
            self.state_store.record("sheet")
            return self.sheet_text()
        if command == "/pause":
            self.state_store.record("pause")
            return "Paused. New control state written to runtime/state/control_state.json."
        if command == "/resume":
            self.state_store.record("resume")
            return "Resumed. Control state updated."
        if command == "/retry":
            if not argument:
                return "Usage: /retry <job_id>"
            return self._run_action("retry", argument)
        if command in {"/run", "/render", "/upload"}:
            return self._run_action(command.lstrip("/"))
        return "Unknown command. Send /help for available commands."

    def _parse_command(self, text: str) -> tuple[str, str]:
        parts = str(text or "").strip().split(maxsplit=1)
        if not parts:
            return "", ""
        command = parts[0].split("@", 1)[0].lower()
        argument = parts[1].strip() if len(parts) > 1 else ""
        return command, argument

    def _run_action(self, action: str, job_id: str = "") -> str:
        self.state_store.record(action, job_id)
        if self.action_runner:
            return self.action_runner(action, job_id)
        suffix = f" for {job_id}" if job_id else ""
        return f"Queued {action}{suffix}. Control event written locally."

    def help_text(self) -> str:
        return (
            "Commands:\n"
            "/help\n/status\n/run\n/pause\n/resume\n/retry <job_id>\n"
            "/render\n/upload\n/sheet\n/logs"
        )

    def status_text(self) -> str:
        state = self.state_store.load()
        snapshot = self.state_builder.snapshot()
        counts = snapshot.get("queue_counts", {})
        return (
            f"Paused: {bool(state.get('paused'))}\n"
            f"Pending: {counts.get('pending', 0)}\n"
            f"Rendering: {counts.get('rendering', 0)}\n"
            f"Uploading: {counts.get('uploading', 0)}\n"
            f"Failed: {counts.get('failed', 0)}\n"
            f"Completed: {counts.get('completed', 0)}"
        )

    def sheet_text(self) -> str:
        return (
            f"Spreadsheet: {_safe_setting(self.settings.get('spreadsheet_id')) or '[not configured]'}\n"
            f"Queue sheet: {_safe_setting(self.settings.get('google_sheet_name') or self.settings.get('upload_sheet_name'))}\n"
            f"Render sheet: {_safe_setting(self.settings.get('render_sheet_name'))}"
        )

    def logs_text(self) -> str:
        logs = self.state_builder.snapshot().get("logs", {})
        lines = []
        for name in ("error", "scheduler", "telegram", "render", "upload"):
            events = self.state_builder.log_tail(name, 3)
            if not events:
                continue
            latest = events[-1]
            event_name = latest.get("event") or latest.get("message", "")
            lines.append(f"{name}: {event_name}")
        return "\n".join(lines) if lines else "No recent logs found."


def _extract_message(update: dict) -> tuple[str, str]:
    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat") or {}
    return str(chat.get("id", "")).strip(), str(message.get("text", "")).strip()


def telegram_webhook_response(chat_id: str, text: str) -> dict:
    return {
        "method": "sendMessage",
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }


def create_app(
    root: str | Path = ROOT,
    settings: dict | None = None,
    handler: TelegramControlHandler | None = None,
    logger: Any = None,
) -> FastAPI:
    root_path = Path(root)
    app_settings = settings or load_control_settings(root_path)
    app_logger = logger or NullLogger()
    control_handler = handler or TelegramControlHandler(root_path, app_settings, logger=app_logger)
    app = FastAPI(title="YouTube Pipeline Control API")

    @app.get("/health")
    def health() -> dict:
        return {
            "ok": True,
            "telegram_configured": bool(app_settings.get("TELEGRAM_BOT_TOKEN")),
            "allowed_chats_configured": bool(_parse_chat_ids(app_settings.get("TELEGRAM_ALLOWED_CHAT_IDS"))),
            "public_webhook_url_configured": bool(app_settings.get("PUBLIC_WEBHOOK_URL")),
        }

    @app.post("/telegram/webhook")
    async def telegram_webhook(request: Request) -> dict:
        update = await request.json()
        chat_id, text = _extract_message(update)
        if not chat_id:
            raise HTTPException(status_code=400, detail="missing Telegram chat_id")
        if not control_handler.is_authorized(chat_id):
            app_logger.telegram("telegram_unauthorized_chat", chat_id=chat_id)
            raise HTTPException(status_code=403, detail="unauthorized chat_id")
        reply = control_handler.handle(text)
        app_logger.telegram("telegram_command_handled", chat_id=chat_id, command=text.split(maxsplit=1)[0] if text else "")
        return telegram_webhook_response(chat_id, reply)

    return app


app = create_app()
