"""假 MiniMax（anthropic 格式流式）——驱动真等待 UI 抓「生成中」底稿用。
思考期 ~28s（thinking_delta 缓滴）→ 正文期 text_delta（~0.35s/块）→ end_turn。
端口 8102，无鉴权；请求里的 thinking 参数原样收下。
"""
import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

THINKING = [
    "这一章的落点：沈砚第一次起意探禁阁。开篇不能直接写残纸，先给抄书坊的夜——雨、瓦、他多抄的四页经注，用忙碌压住心虚。",
    "残纸的出现方式要「被动」：随风飘来，不是他去捡。坊规「捡到即焚」与「他本该焚的」之间留一拍，这一拍就是本章的戏。",
    "巡夜灯笼的逼近是外部压力，按「子时—梆子—灯笼浮上来」的顺序推进；结尾落在他吹灯装睡、残页贴心口，凉与烫并置，钩子留给下一章。",
    "节奏核对：环境两拍、物件一拍、规矩一拍、抉择两拍、压力两拍、收束一拍——总字数控制在两千八到三千二，不超。",
    "措辞提醒：禁阁不写全貌，只写「方向」；残页不解释来历，只写「不属于任何名录」。悬念靠省略，不靠人物议论。",
    "开头一句备选：「夜雨落在抄书坊的青瓦上，像无数细小的指节在敲门。」——以声起，不用天色，避免与第二章的开头重复。",
]

PROSE = (
    "夜雨落在抄书坊的青瓦上，像无数细小的指节在敲门。\n\n"
    "沈砚把最后一摞书册搬回架上，指尖在《云海潮生志》的书脊上停了停。封皮内衬的夹层里，"
    "藏着半页不属于任何名录的残纸——三日前誊抄时，它从禁阁的方向随风飘到他脚边，"
    "像一片不肯落地的灰蝶。\n\n"
    "坊规第一条：禁阁方向的物件，捡到即焚。他本该焚的。\n\n"
    "灯芯爆了个火花。沈砚回头看了一眼门房的方向，把残页重新塞进夹层，动作快得连他自己都心惊。"
    "这一晚他抄完了十二页经注，比平日多了四页——多出来的四页，是为了让自己的手忙起来，"
    "忙到不去想禁阁方向那道被人动过的封条。\n\n"
    "子时的梆子响过，巡夜的灯笼从巷口浮上来。沈砚吹了灯，在黑暗中睁着眼。怀中残页贴着心口，"
    "比想象中更凉，也更烫。"
)


def sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.endswith("/models"):
            body = json.dumps({"data": [{"id": "MiniMax-M3.1-Flash"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        self.rfile.read(n)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        w = self.wfile

        def emit(event, data, delay=0.0):
            if delay:
                time.sleep(delay)
            w.write(sse(event, data).encode("utf-8"))
            w.flush()

        emit("message_start", {
            "type": "message_start",
            "message": {"id": "msg_fake_1", "type": "message", "role": "assistant",
                        "model": "MiniMax-M3.1-Flash", "content": [],
                        "stop_reason": None,
                        "usage": {"input_tokens": 12642, "output_tokens": 0}},
        }, 1.2)
        emit("content_block_start", {
            "type": "content_block_start", "index": 0,
            "content_block": {"type": "thinking", "thinking": ""},
        })
        for para in THINKING:
            for i in range(0, len(para), 48):
                emit("content_block_delta", {
                    "type": "content_block_delta", "index": 0,
                    "delta": {"type": "thinking_delta", "thinking": para[i:i + 48]},
                }, 1.3)
        emit("content_block_stop", {"type": "content_block_stop", "index": 0})
        emit("content_block_start", {
            "type": "content_block_start", "index": 1,
            "content_block": {"type": "text", "text": ""},
        })
        step = 40
        for i in range(0, len(PROSE), step):
            emit("content_block_delta", {
                "type": "content_block_delta", "index": 1,
                "delta": {"type": "text_delta", "text": PROSE[i:i + step]},
            }, 0.35)
        emit("content_block_stop", {"type": "content_block_stop", "index": 1})
        emit("message_delta", {
            "type": "message_delta", "delta": {"stop_reason": "end_turn"},
            "usage": {"output_tokens": 4310},
        })
        emit("message_stop", {"type": "message_stop"})


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 8318), Handler).serve_forever()
