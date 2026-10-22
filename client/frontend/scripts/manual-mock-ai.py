"""本地 mock Anthropic Messages API（手册截图专用，9100 端口）。

伺服：
  GET  /v1/models        → 404（让探活降级为 max_tokens=1 最小请求）
  POST /v1/messages      → stream=true 走 SSE 分块吐正文；否则回最小 JSON 消息
用途：手册截图要拍「生成弹窗→流式写入→完成」全链，又不打真模型、不花钱。
启动：client/backend/.venv/bin/uvicorn mock_ai:app --port 9100 （cwd=本目录）
"""

import asyncio
import json
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI()

CALL_N = {"n": 0}
THINKING = [
    "先看这一章要落到哪个落点：残页、巡夜灯笼、第一次起念探禁阁。",
    "开头不要交代身世，直接从更漏声切进场景；让克制的好奇压过恐惧。",
    "对白留白，环境声压过人声；结尾把灯笼停在坊门外，留下悬而未决的一拍。",
]
POLISH_TEXT = (
    "## 当前章节\n章纲：沈砚夜班誊书时发现禁阁封条被人动过，捡到半页来历不明的残纸；巡夜灯笼逼近，"
    "他把残页藏进书夹层，第一次起了探禁阁的念头。\n本章位置：全书第 1 章（首章）\n"
    "章末落点：沈砚吹灯装睡，残页贴着心口；窗外巡夜灯笼停在了坊门外。\n\n"
    "叙事目标：\n- 读者情绪（离场感受）：紧张\n"
    "润色说明：补足感官细节（更漏、薄冰、灯影），节奏三收一放，突出「克制的好奇」这条情绪主线；"
    "对白留白，环境声压过人声。"
)

# 续《云海剑歌》第一章的演示正文（mock，不参与任何真实产品数据）
SCRIPT = (
    "更漏声里，沈砚听见了另一种声音——极轻，像纸页在风里翻动，却又从房梁上来。"
    "他没有睁眼。坊里的老人说过，禁阁的东西认得克制的人：你越是装作不知，它越以为你没看见。"
    "可那一页残纸偏偏在他怀里发烫，一阵一阵，像有人隔着衣衫按住他的心口，提醒他：你捡到我了。"
    "灯笼的光从窗纸上漫进来，青白色，停了三息，又移开了。巡夜人走远了，脚步声碾过巷口的薄冰。"
    "沈砚在黑暗里慢慢吐出一口气，把《云海潮生志》的书脊按得更紧了些。"
    "夹层里，那半页残纸的边缘硌着他的掌心，一列细小的字迹浮上来，又被他用手心盖住——"
    "那不是经注，也不是任何一部的书名。四个字，笔锋瘦硬，像是勿忙间以指为笔写下的："
    "禁阁第三层，灯下无人。"
)


@app.get("/v1/models")
async def models():
    return {"data": [{"id": "mock-v4", "type": "model"}, {"id": "mock-v4-pro", "type": "model"}]}


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.post("/v1/messages")
async def messages(req: Request):
    body = await req.json()
    CALL_N["n"] += 1
    is_polish = CALL_N["n"] == 1
    if not body.get("stream"):
        text = (POLISH_TEXT if is_polish else SCRIPT) if int(body.get("max_tokens") or 0) > 8 else "好"
        return {
            "id": "msg_mock_1",
            "type": "message",
            "role": "assistant",
            "model": body.get("model", "mock"),
            "content": [{"type": "text", "text": text}],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 100, "output_tokens": len(text)},
        }

    async def gen():
        # MOCK_FIRST_DELAY：首块前静默 N 秒（手册/原型要拍「等待首字」阶段行时用）
        delay = float(os.environ.get("MOCK_FIRST_DELAY", "0") or 0)
        if delay:
            await asyncio.sleep(delay)
        yield _sse("message_start", {
            "type": "message_start",
            "message": {"id": "msg_mock_1", "type": "message", "role": "assistant",
                        "content": [], "model": body.get("model", "mock"),
                        "stop_reason": None, "stop_sequence": None,
                        "usage": {"input_tokens": 1200, "output_tokens": 1}},
        })
        # 思考档（c-prose-paper 抽检用）：请求带 thinking 时先吐一个 thinking 块，
        # 让「思考面板 → 收起条 → 回看抽屉」三态在真界面上可见（不参与真实产品数据）
        text_index = 0
        if body.get("thinking"):
            yield _sse("content_block_start", {
                "type": "content_block_start", "index": 0,
                "content_block": {"type": "thinking", "thinking": ""},
            })
            for seg in THINKING:
                yield _sse("content_block_delta", {
                    "type": "content_block_delta", "index": 0,
                    "delta": {"type": "thinking_delta", "thinking": seg},
                })
                await asyncio.sleep(0.3)
            yield _sse("content_block_stop", {"type": "content_block_stop", "index": 0})
            text_index = 1

        yield _sse("content_block_start", {
            "type": "content_block_start", "index": text_index,
            "content_block": {"type": "text", "text": ""},
        })
        src = POLISH_TEXT if is_polish else SCRIPT
        chunk = ""
        for ch in src:
            chunk += ch
            if len(chunk) >= 14:
                yield _sse("content_block_delta", {
                    "type": "content_block_delta", "index": text_index,
                    "delta": {"type": "text_delta", "text": chunk},
                })
                chunk = ""
                await asyncio.sleep(0.22)
        if chunk:
            yield _sse("content_block_delta", {
                "type": "content_block_delta", "index": text_index,
                "delta": {"type": "text_delta", "text": chunk},
            })
        yield _sse("content_block_stop", {"type": "content_block_stop", "index": text_index})
        yield _sse("message_delta", {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn", "stop_sequence": None},
            "usage": {"output_tokens": len(SCRIPT)},
        })
        yield _sse("message_stop", {"type": "message_stop"})

    return StreamingResponse(
        gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
