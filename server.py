#!/usr/bin/env python3
import json
import os
import hmac
from http import cookies
from datetime import datetime
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PORT = int(os.environ.get("PORT", "8890"))
BIND_HOST = os.environ.get("BIND_HOST", "127.0.0.1")
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
BOARD_FILE = DATA_DIR / "board_state.json"
BOARD_HISTORY_DIR = DATA_DIR / "board_history"
HISTORY_DIR = DATA_DIR / "history"
TOKEN_FILE = Path(os.environ.get("MONITOR_TOKEN_FILE", str(Path.home() / ".hermes" / "secrets" / "monitor_token")))
COOKIE_NAME = "monitor_auth"


def _load_token():
    token = os.environ.get("MONITOR_TOKEN", "").strip()
    if token:
        return token
    try:
        return TOKEN_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


EXPECTED_TOKEN = _load_token()


DEFAULT_BOARD = {
    "updated_at": None,
    "columns": {
        "want_to_write": [],
        "writing": [],
        "published": [],
        "ignored": [],
    },
}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self._set_auth_cookie = False
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _request_token(self, parsed=None):
        auth = self.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            return auth.split(None, 1)[1].strip()
        header_token = self.headers.get("X-Monitor-Token") or self.headers.get("X-Auth-Token")
        if header_token:
            return header_token.strip()
        cookie_header = self.headers.get("Cookie", "")
        if cookie_header:
            jar = cookies.SimpleCookie()
            try:
                jar.load(cookie_header)
                if COOKIE_NAME in jar:
                    return jar[COOKIE_NAME].value.strip()
            except Exception:
                pass
        if parsed is not None:
            query_token = parse_qs(parsed.query).get("token", [""])[0].strip()
            if query_token:
                self._set_auth_cookie = True
                return query_token
        return ""

    def _authorized(self, parsed=None):
        if not EXPECTED_TOKEN:
            return False
        supplied = self._request_token(parsed)
        return bool(supplied) and hmac.compare_digest(supplied, EXPECTED_TOKEN)

    def _require_auth(self, parsed=None):
        if self._authorized(parsed):
            return True
        self._json_response({"ok": False, "error": "Unauthorized"}, status=401)
        return False

    def _json_response(self, payload, status=200):
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_json_file(self, path: Path, status=200):
        if not path.exists():
            return self._json_response({"ok": False, "error": f"Missing file: {path.name}"}, status=404)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return self._json_response({"ok": False, "error": f"Invalid JSON in {path.name}: {exc}"}, status=500)
        return self._json_response(payload, status=status)

    def _latest_history_snapshot(self, name: str, date=None):
        if date:
            day_dir = HISTORY_DIR / date
            if not day_dir.exists():
                return None
            matches = sorted(day_dir.glob(f"*-{name}.json"))
            if not matches:
                return None
            try:
                return json.loads(matches[-1].read_text(encoding="utf-8"))
            except Exception:
                return None

        days = sorted(path for path in HISTORY_DIR.glob("*") if path.is_dir())
        for day_dir in reversed(days):
            matches = sorted(day_dir.glob(f"*-{name}.json"))
            if not matches:
                continue
            try:
                return json.loads(matches[-1].read_text(encoding="utf-8"))
            except Exception:
                continue
        return None

    def _history_payload(self):
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        history = []
        for day_dir in sorted((path for path in HISTORY_DIR.glob("*") if path.is_dir()), reverse=True):
            dashboard_files = sorted(day_dir.glob("*-dashboard.json"))
            item_files = sorted(day_dir.glob("*-items.json"))
            latest_generated_at = None
            total_events = None
            total_items = None
            if dashboard_files:
                try:
                    latest_payload = json.loads(dashboard_files[-1].read_text(encoding="utf-8"))
                    latest_generated_at = latest_payload.get("generated_at")
                    stats = latest_payload.get("stats") or {}
                    total_events = stats.get("total_events")
                    total_items = stats.get("total_items")
                except Exception:
                    latest_generated_at = None
            history.append({
                "date": day_dir.name,
                "dashboard_snapshots": len(dashboard_files),
                "item_snapshots": len(item_files),
                "latest_generated_at": latest_generated_at,
                "total_events": total_events,
                "total_items": total_items,
            })
        return {"history": history}

    def _read_board(self):
        if not BOARD_FILE.exists():
            return dict(DEFAULT_BOARD)
        try:
            data = json.loads(BOARD_FILE.read_text(encoding="utf-8"))
        except Exception:
            return dict(DEFAULT_BOARD)
        columns = data.get("columns") or {}
        normalized = {
            "updated_at": data.get("updated_at"),
            "columns": {
                "want_to_write": columns.get("want_to_write") or [],
                "writing": columns.get("writing") or [],
                "published": columns.get("published") or [],
                "ignored": columns.get("ignored") or [],
            },
        }
        return normalized

    def _write_board(self, payload):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        BOARD_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().astimezone()
        wrapped = {
            "updated_at": stamp.isoformat(timespec="seconds"),
            "columns": payload.get("columns") or DEFAULT_BOARD["columns"],
        }
        BOARD_FILE.write_text(json.dumps(wrapped, ensure_ascii=False, indent=2), encoding="utf-8")
        day_dir = BOARD_HISTORY_DIR / stamp.strftime("%Y-%m-%d")
        day_dir.mkdir(parents=True, exist_ok=True)
        history_file = day_dir / f"{stamp.strftime('%H%M%S')}.json"
        history_file.write_text(json.dumps(wrapped, ensure_ascii=False, indent=2), encoding="utf-8")
        return wrapped

    def do_GET(self):
        parsed = urlparse(self.path)
        if not self._require_auth(parsed):
            return
        query = parse_qs(parsed.query)
        date = query.get("date", [None])[0]
        if parsed.path == "/api/dashboard":
            if date:
                payload = self._latest_history_snapshot("dashboard", date=date)
                if payload is None:
                    return self._json_response({"ok": False, "error": f"No dashboard snapshot for {date}"}, status=404)
                return self._json_response(payload)
            return self._send_json_file(DATA_DIR / "dashboard.json")
        if parsed.path == "/api/items":
            if date:
                payload = self._latest_history_snapshot("items", date=date)
                if payload is None:
                    return self._json_response({"ok": False, "error": f"No items snapshot for {date}"}, status=404)
                return self._json_response(payload)
            return self._send_json_file(DATA_DIR / "items.json")
        if parsed.path == "/api/status":
            return self._send_json_file(DATA_DIR / "fetch_status.json")
        if parsed.path == "/api/token-usage":
            return self._send_json_file(DATA_DIR / "token_usage.json")
        if parsed.path == "/api/board":
            return self._json_response(self._read_board())
        if parsed.path == "/api/history":
            return self._json_response(self._history_payload())
        if parsed.path in {"", "/"}:
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if not self._require_auth(parsed):
            return
        if parsed.path != "/api/board":
            return self._json_response({"ok": False, "error": "Not found"}, status=404)
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            return self._json_response({"ok": False, "error": "Invalid JSON"}, status=400)
        board = self._write_board(payload)
        return self._json_response({"ok": True, "board": board})

    def end_headers(self):
        if self._set_auth_cookie and EXPECTED_TOKEN:
            self.send_header("Set-Cookie", f"{COOKIE_NAME}={EXPECTED_TOKEN}; Path=/; HttpOnly; SameSite=Strict")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Auth-Token, X-Monitor-Token")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()


if __name__ == "__main__":
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    httpd = ThreadingHTTPServer((BIND_HOST, PORT), Handler)
    print(f"Serving AI Hot Monitor MVP at http://{BIND_HOST}:{PORT}/ from {ROOT}", flush=True)
    httpd.serve_forever()
