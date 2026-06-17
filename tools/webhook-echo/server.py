"""
Plan 1 임시 webhook echo 서버.
Grafana가 보내는 webhook payload를 콘솔과 디스크에 기록한다.
Plan 2부터는 ai-bot이 이 역할을 대체한다.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from datetime import datetime, timezone

LOG_FILE = "/tmp/webhook-echo.log"


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        auth = self.headers.get("Authorization", "")

        record = {
            "received_at": datetime.now(timezone.utc).isoformat(),
            "path": self.path,
            "authorization": auth,
            "body": json.loads(body) if body else None,
        }

        line = json.dumps(record, ensure_ascii=False)
        print(line, flush=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, format, *args):
        # 기본 access log 끔 (우리 record가 더 자세함)
        return


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "9000"))
    httpd = HTTPServer(("0.0.0.0", port), Handler)
    print(f"webhook-echo listening on :{port}", flush=True)
    httpd.serve_forever()
