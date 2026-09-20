#!/usr/bin/env python3
# QA mock：OpenAI 兼容端点（仅本机 127.0.0.1:9999），用于隔离栈 AI 链路测试
import json, time
from http.server import HTTPServer, BaseHTTPRequestHandler

class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        if self.path.rstrip('/').endswith('/models'):
            self._send(200, {"object": "list", "data": [{"id": "qa-fake-model", "object": "model"}]})
        else:
            self._send(200, {"ok": True})
    def do_POST(self):
        n = int(self.headers.get('Content-Length', 0) or 0)
        self.rfile.read(n)
        self._send(200, {
            "id": "qa-mock-" + str(int(time.time())), "object": "chat.completion",
            "created": int(time.time()), "model": "qa-fake-model",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": "【QA模拟回复】星尘在灯芯上轻轻一颤，像是谁在很远的地方应了一声。"}}],
            "usage": {"prompt_tokens": 128, "completion_tokens": 32, "total_tokens": 160},
        })
    def log_message(self, *a):
        pass

HTTPServer(('127.0.0.1', 9999), H).serve_forever()
