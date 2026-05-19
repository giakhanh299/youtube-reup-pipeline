from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import sys
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from configs.config_loader import ConfigLoader
from services.dashboard_service import DashboardControlStore, DashboardStateBuilder


HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Pipeline Dashboard</title>
  <style>
    body { font-family: Segoe UI, Arial, sans-serif; margin: 0; background: #f6f7f9; color: #1f2933; }
    header { padding: 16px 20px; background: #17202a; color: white; }
    main { padding: 20px; display: grid; gap: 16px; }
    section { background: white; border: 1px solid #d8dee6; border-radius: 6px; padding: 14px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }
    .metric { border: 1px solid #e2e8f0; border-radius: 6px; padding: 12px; }
    .metric b { display: block; font-size: 24px; margin-top: 4px; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { text-align: left; border-bottom: 1px solid #edf2f7; padding: 8px; }
    button { border: 1px solid #94a3b8; background: #fff; border-radius: 4px; padding: 6px 10px; cursor: pointer; }
    pre { overflow: auto; max-height: 280px; background: #0f172a; color: #dbeafe; padding: 10px; border-radius: 4px; }
  </style>
</head>
<body>
  <header><h1>Pipeline Dashboard</h1></header>
  <main>
    <section><div class="grid" id="metrics"></div></section>
    <section>
      <button onclick="control('pause')">Pause</button>
      <button onclick="control('resume')">Resume</button>
    </section>
    <section><h2>Jobs</h2><div id="jobs"></div></section>
    <section><h2>Logs</h2><pre id="logs"></pre></section>
  </main>
  <script>
    async function load() {
      const data = await fetch('/api/status').then(r => r.json());
      const counts = data.queue_counts || {};
      metrics.innerHTML = Object.entries(counts).map(([k,v]) => `<div class="metric">${k}<b>${v}</b></div>`).join('');
      jobs.innerHTML = `<table><thead><tr><th>Job</th><th>Status</th><th>Account</th><th>Retry</th><th>Action</th></tr></thead><tbody>` +
        (data.jobs || []).map(j => `<tr><td>${j.job_id || ''}</td><td>${j.upload_state || j.status || ''}</td><td>${j.account_name || j.channel_key || 'default'}</td><td>${j.retry_count || 0}</td><td><button onclick="control('retry','${j.job_id || ''}')">Retry</button> <button onclick="control('skip','${j.job_id || ''}')">Skip</button></td></tr>`).join('') +
        `</tbody></table>`;
      logs.textContent = JSON.stringify(data.logs || {}, null, 2);
    }
    async function control(action, job_id='') {
      await fetch('/api/control', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action, job_id})});
      load();
    }
    load(); setInterval(load, 5000);
  </script>
</body>
</html>
"""


def make_handler(root: Path):
    state_builder = DashboardStateBuilder(root)
    control_store = DashboardControlStore(root)

    class DashboardHandler(BaseHTTPRequestHandler):
        def _json(self, payload: dict, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == "/api/status":
                self._json(state_builder.snapshot())
                return
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            if path != "/api/control":
                self._json({"error": "not found"}, 404)
                return
            length = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(length).decode("utf-8") if length else "{}"
            payload = json.loads(raw) if raw.strip() else {}
            try:
                event = control_store.record(str(payload.get("action", "")), str(payload.get("job_id", "")))
                self._json({"ok": True, "event": event.__dict__})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, 400)

        def log_message(self, format, *args) -> None:
            return None

    return DashboardHandler


def main() -> int:
    settings = ConfigLoader(ROOT).load_settings()
    host = settings.get("dashboard_host", "127.0.0.1")
    port = int(settings.get("dashboard_port", 8080))
    server = ThreadingHTTPServer((host, port), make_handler(ROOT))
    print(f"Dashboard running at http://{host}:{port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
