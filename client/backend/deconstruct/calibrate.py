"""打标准确率校准工具（c-deconstruct-knowledge 批A A5）——开发期一次性。

boss 定的工作流：算法选章打标 → 大模型独立读选中章判主导场面 → 对表算命中率。
命中率 <70% → 调词族/阈值/加成项再测；≥70% → 锁定零模型选章上线。
需真 Key（本书/账号 AI 配置），不进 CI 不进运行时。

用法：python -m deconstruct.calibrate --task-id <id> [--user-id <uid>] [--limit 31]
报告落档：任务 products 旁 calibrate_report.json（分类型命中率＋混淆对＋总体）。
"""

from __future__ import annotations

import argparse
import json
import logging

from db import async_session

logger = logging.getLogger("uvicorn.error")

HIT_BAR = 70.0  # 总体命中率门槛（%）——首份报告后可由 boss 重定

_CLASSIFY_PROMPT = """阅读以下小说章节文本，从七个场面类型中判定本章的主导场面。
七类：打斗、文戏、开篇、转折、收尾、对峙、日常。
只输出一个 JSON 对象：{{"scene": "类型"}}——不要解释。
章节文本：
---
{text}
---"""


def compare_labels(
    labeled: list[tuple[str, str]], predicted: list[tuple[str, str]]
) -> dict:
    """对表（纯函数）：labeled/predicted = [(ref, 场面), ...] 同序。

    返回 {overall_hit_rate, per_type: {类型: {total, hit}}, confusion: {算法→模型: n}}。
    分类型命中率指导词族调优方向；混淆对＝算法标 X 模型判 Y 的计数。"""
    confusion: dict[str, int] = {}
    per_type: dict[str, dict[str, int]] = {}
    hits = 0
    for (ref, truth), (_pref, pred) in zip(labeled, predicted):
        per_type.setdefault(truth, {"total": 0, "hit": 0})
        per_type[truth]["total"] += 1
        if truth == pred:
            hits += 1
            per_type[truth]["hit"] += 1
        else:
            confusion[f"{truth}→{pred}"] = confusion.get(f"{truth}→{pred}", 0) + 1
    total = len(labeled) or 1
    return {
        "overall_hit_rate": round(hits / total * 100, 1),
        "hits": hits,
        "total": len(labeled),
        "per_type": per_type,
        "confusion": dict(sorted(confusion.items(), key=lambda kv: -kv[1])),
    }


def _parse_scene(text: str, valid: set[str]) -> str:
    """模型输出 → 场面值（容错：剥围栏/取首合法值；非法返回空＝不计对错）。"""
    import json as _json
    import re as _re

    m = _re.search(r"\{[^}]*\}", text, _re.DOTALL)
    if not m:
        return ""
    try:
        scene = str(_json.loads(m.group(0)).get("scene") or "")
    except ValueError:
        return ""
    return scene if scene in valid else ""


async def run_calibration(task_id: str, user_id: str, *, limit: int = 31) -> dict:
    """对指定任务的智能采样集跑校准。返回报告 dict（同时落档）。"""
    from ai_client import get_ai_client_for_user
    from deconstruct.pipeline import _load_chapters
    from models.deconstruct import DeconstructJob

    client = await get_ai_client_for_user(user_id)

    async with async_session() as db:
        task = await db.get(DeconstructJob, task_id)
        if task is None or task.user_id != user_id:
            raise ValueError("task_not_found")
        selected = json.loads(task.selected_chapters_json or "[]")
        # 章文本＝staging 源文件重建（解析确定性；拆书章节不在 chapters 表）
        all_chapters = await _load_chapters(task)
        chapters = {c["ref"]: c for c in all_chapters}

    labeled: list[tuple[str, str]] = []
    predicted: list[tuple[str, str]] = []
    from deconstruct.sampler import tag_chapter
    from kb.concepts import SCENES

    async with async_session() as db:
        for ref in selected[:limit]:
            ch = chapters.get(ref)
            if ch is None or not (ch.get("text") or "").strip():
                continue
            algo_tag = tag_chapter(ch["text"], title=ch.get("title") or "")
            if not algo_tag.label:
                continue  # 算法自己都未分类的章不进校准对表
            usage: dict = {}
            resp = await client.chat(
                model="haiku",
                system="你是小说场面分类器。只输出 JSON。",
                messages=[{"role": "user", "content": _CLASSIFY_PROMPT.format(text=ch["text"][:6000])}],
                max_tokens=64,
                usage=usage,
                operation="deconstruct_calibrate",
            )
            pred = _parse_scene(resp, set(SCENES))
            if not pred:
                continue
            labeled.append((ref, algo_tag.label))
            predicted.append((ref, pred))

    report = compare_labels(labeled, predicted)
    report["task_id"] = task_id
    report["verdict"] = "pass" if report["overall_hit_rate"] >= HIT_BAR else "tune"
    report["hit_bar"] = HIT_BAR
    logger.info(
        "event=deconstruct_calibrate task=%s hit=%s%% verdict=%s",
        task_id, report["overall_hit_rate"], report["verdict"],
    )
    return report


def main() -> None:
    import asyncio

    parser = argparse.ArgumentParser(description="打标准确率校准（开发期工具，需真 Key）")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--limit", type=int, default=31)
    args = parser.parse_args()
    report = asyncio.run(run_calibration(args.task_id, args.user_id, limit=args.limit))
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
