from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from services.control_api import TelegramControlHandler, create_app


class FakeStateStore:
    def __init__(self) -> None:
        self.state = {"paused": False}
        self.events = []

    def load(self) -> dict:
        return dict(self.state)

    def record(self, action: str, job_id: str = ""):
        self.events.append((action, job_id))
        if action == "pause":
            self.state["paused"] = True
        elif action == "resume":
            self.state["paused"] = False
        self.state["last_action"] = action
        self.state["last_job_id"] = job_id


class FakeStateBuilder:
    def snapshot(self) -> dict:
        return {
            "queue_counts": {"pending": 1, "rendering": 0, "uploading": 0, "failed": 0, "completed": 2},
            "logs": {},
        }

    def log_tail(self, _name: str, _limit: int = 50) -> list[dict]:
        return []


def build_client(settings: dict | None = None, handler: TelegramControlHandler | None = None) -> TestClient:
    return TestClient(create_app(".", settings or {"TELEGRAM_ALLOWED_CHAT_IDS": "123"}, handler=handler))


class ControlApiTests(unittest.TestCase):
    def test_health_reports_configuration_without_secret_values(self) -> None:
        client = build_client(
            {
                "TELEGRAM_BOT_TOKEN": "secret-token",
                "TELEGRAM_ALLOWED_CHAT_IDS": "123",
                "PUBLIC_WEBHOOK_URL": "https://example.com/telegram/webhook",
            }
        )

        response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["telegram_configured"])
        self.assertNotIn("secret-token", response.text)

    def test_webhook_rejects_unauthorized_chat(self) -> None:
        client = build_client({"TELEGRAM_ALLOWED_CHAT_IDS": "123"})

        response = client.post("/telegram/webhook", json={"message": {"chat": {"id": 999}, "text": "/status"}})

        self.assertEqual(response.status_code, 403)

    def test_pause_resume_write_control_state(self) -> None:
        store = FakeStateStore()
        handler = TelegramControlHandler(".", {"TELEGRAM_ALLOWED_CHAT_IDS": "123"}, state_store=store, state_builder=FakeStateBuilder())
        client = build_client(handler=handler)

        pause = client.post("/telegram/webhook", json={"message": {"chat": {"id": 123}, "text": "/pause"}})
        resume = client.post("/telegram/webhook", json={"message": {"chat": {"id": 123}, "text": "/resume"}})

        self.assertEqual(pause.status_code, 200)
        self.assertEqual(resume.status_code, 200)
        self.assertFalse(store.state["paused"])
        self.assertEqual(store.events, [("pause", ""), ("resume", "")])

    def test_retry_uses_injected_runner_and_records_job_id(self) -> None:
        calls = []

        def runner(action: str, job_id: str) -> str:
            calls.append((action, job_id))
            return f"ran {action} {job_id}"

        store = FakeStateStore()
        settings = {"TELEGRAM_ALLOWED_CHAT_IDS": "123"}
        handler = TelegramControlHandler(
            ".",
            settings,
            state_store=store,
            state_builder=FakeStateBuilder(),
            action_runner=runner,
        )
        client = build_client(settings, handler)

        response = client.post("/telegram/webhook", json={"message": {"chat": {"id": 123}, "text": "/retry job_1"}})

        self.assertEqual(response.status_code, 200)
        self.assertIn("ran retry job_1", response.json()["text"])
        self.assertEqual(calls, [("retry", "job_1")])
        self.assertEqual(store.events[-1], ("retry", "job_1"))

    def test_unknown_command_returns_help_hint(self) -> None:
        handler = TelegramControlHandler(
            ".",
            {"TELEGRAM_ALLOWED_CHAT_IDS": "123"},
            state_store=FakeStateStore(),
            state_builder=FakeStateBuilder(),
        )
        client = build_client(handler=handler)

        response = client.post("/telegram/webhook", json={"message": {"chat": {"id": 123}, "text": "/bad"}})

        self.assertEqual(response.status_code, 200)
        self.assertIn("Unknown command", response.json()["text"])


if __name__ == "__main__":
    unittest.main()
