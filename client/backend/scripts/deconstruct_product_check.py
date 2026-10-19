"""拆书产物 → 开书设定页契约校验（c-deconstruct-resilience）。

对既有任务行跑「建书映射全链」的干跑（dry-run）：不动任何书库，只验证
products_json 的模型 JSON 能否无损喂进设定页各域服务契约——
world→normalize_world、characters→role 白名单映射、mainplot→story_arc、
style→put_style 白名单键、foreshadow→hooks 描述、intro/genre→建书参数。

用法（backend 根目录）：
    python scripts/deconstruct_product_check.py --db PATH --task TASK_ID
    python scripts/deconstruct_product_check.py --db PATH --latest
退出码：0＝全部 PASS；1＝有 FAIL（契约违约，建书会丢内容）。

判据口径：字段缺失/全空、role 不在白名单映射、world 规范化后舞台+力量全空、
主线弧缺起止章、伏笔缺埋设章——这些是「开书后设定页空转」的直接来源。
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deconstruct.apply import (  # noqa: E402
    _ROLE_MAP,
    _cards,
    _data,
    _hooks_items,
    _role_normalize,
    _world_body,
)


def _load_task(db_path: str, task_id: str | None, latest: bool) -> dict | None:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        if latest:
            row = con.execute(
                "select * from deconstruct_jobs where status='completed' "
                "order by created_at desc limit 1"
            ).fetchone()
        else:
            row = con.execute(
                "select * from deconstruct_jobs where id=?", (task_id,)
            ).fetchone()
        return dict(row) if row else None
    finally:
        con.close()


class _Report:
    def __init__(self) -> None:
        self.lines: list[tuple[str, str]] = []

    def check(self, ok: bool, label: str, detail: str = "") -> None:
        mark = "PASS" if ok else "FAIL"
        self.lines.append((mark, f"{label}{(' — ' + detail) if detail else ''}"))

    def warn(self, label: str, detail: str = "") -> None:
        """资料质量问题（不进设定页，不阻断开书）——不计入退出码。"""
        self.lines.append(("WARN", f"{label}{(' — ' + detail) if detail else ''}"))

    @property
    def failed(self) -> int:
        return sum(1 for mark, _ in self.lines if mark == "FAIL")

    def render(self) -> str:
        return "\n".join(f"[{mark}] {text}" for mark, text in self.lines)


def check_task(task: dict) -> _Report:
    rep = _Report()

    class _T:  # apply 的私有函数只吃属性——套一层
        pass

    t = _T()
    t.products_json = task.get("products_json", "{}")

    # ── intro/genre：建书参数 ──
    intro = str(_data(t, "intro").get("intro", "")).strip()
    rep.check(bool(intro), "简介 → 建书 synopsis", f"{len(intro)} 字")
    genre = str(_data(t, "genre").get("genre", "")).strip()
    rep.check(bool(genre), "题材 → 建书 genre", genre[:40])

    # ── world：normalize_world 全链 ──
    world = _data(t, "world")
    body = _world_body(world)
    non_empty_factions = [f for f in body["factions"] if str(f.get("name", "")).strip()]
    rep.check(
        bool(str(body["stage"]).strip() or str(body["power"]).strip() or body["history"]),
        "世界设定 → 舞台/力量/历史非空",
        f"stage {len(str(body['stage']))} 字、power {len(str(body['power']))} 字、"
        f"history {len(body['history'])} 条、factions {len(non_empty_factions)} 方",
    )
    try:
        from settings.world_model import normalize_world

        normalized = normalize_world(body)
        has_any = any(str(normalized.get(k, "")).strip() for k in ("stage", "power", "cost")) or any(
            normalized.get(s) for s in ("history", "factions", "constraints", "extra")
        )
        rep.check(has_any, "世界设定 → normalize_world 后非空（设定页世界页有内容）")
    except Exception as e:  # noqa: BLE001 — 契约违约本身就是 FAIL
        rep.check(False, "世界设定 → normalize_world", f"抛错 {e}")

    # ── characters：role 白名单映射＋去重后非空 ──
    cards = _cards(t)
    rep.check(bool(cards), "角色设定 → 去重后角色卡非空", f"{len(cards)} 张")
    raw_roles = [str(c.get("role", "")) for c in _raw_cards(t)]
    unmapped = [r for r in raw_roles if r not in _ROLE_MAP and _role_normalize(r) == "配角"
                and not any(k in r for k in _ROLE_MAP)]
    rep.check(not unmapped, "角色 role 全部可归一到白名单（含复合 role 扫描）",
              f"无法识别：{sorted(set(unmapped)) or '无'}")
    offscreen = sorted({r for r in raw_roles if r not in _ROLE_MAP})
    if offscreen:
        rep.warn("复合 role 已按包含词归一（资料侧留痕）", f"原始值：{offscreen[:6]}")
    with_persona = sum(1 for c in cards if str(c.get("persona", "")).strip())
    rep.check(with_persona > 0, "角色 persona 非空占比", f"{with_persona}/{len(cards)}")

    # ── mainplot：arcs 起止章 ──
    mainplot = _data(t, "mainplot")
    arcs = [a for a in (mainplot.get("arcs") or []) if isinstance(a, dict)]
    ok_arcs = [a for a in arcs if str(a.get("title", "")).strip() and a.get("ch_start") and a.get("ch_end")]
    rep.check(bool(arcs), "主线剧情 → 弧线非空", f"{len(arcs)} 条")
    rep.check(len(ok_arcs) == len(arcs) and bool(arcs), "主线弧起止章齐全", f"齐全 {len(ok_arcs)}/{len(arcs)}")
    fullstory = ("；".join(
        f"{a.get('title', '')}（第{a.get('ch_start', '?')}-{a.get('ch_end', '?')}章）：{a.get('summary', '')}"
        for a in arcs
    ) or str(mainplot.get("ending", "")))[:2000]
    rep.check(len(fullstory.strip()) > 0, "主线 → story_arc.fullstory 非空", f"{len(fullstory)} 字")

    # ── style：put_style 白名单键 ──
    style = _data(t, "style")
    role_txt = str(style.get("narration", "")).strip()
    rules = [r for r in (style.get("dialogue", ""), style.get("rhythm", "")) if str(r).strip()]
    rep.check(bool(role_txt or rules), "文风 → 叙事身份/规则非空",
              f"narration {len(role_txt)} 字、rules {len(rules)} 条")
    features = [f for f in (style.get("features") or []) if isinstance(f, dict)]
    if features:
        rep.warn("文风特征条目（带例证，任务资料侧）", f"{len(features)} 条")
    else:
        rep.warn("文风特征条目为空（不进设定页 style 页，仅任务资料少一层例证）")

    # ── foreshadow：hooks 描述＋埋设章 ──
    hooks = _hooks_items(t)
    rep.check(bool(hooks), "伏笔 → hooks 非空", f"{len(hooks)} 条")
    with_plant = sum(1 for h in hooks if "埋设于第" in str(h.get("description", "")))
    rep.check(with_plant > 0, "伏笔埋设章可追溯", f"{with_plant}/{len(hooks)}")

    return rep


def _raw_cards(t) -> list[dict]:
    return [c for c in _data(t, "characters").get("characters") or [] if isinstance(c, dict)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--task", default="")
    ap.add_argument("--latest", action="store_true")
    args = ap.parse_args()

    task = _load_task(args.db, args.task or None, args.latest or bool(not args.task))
    if task is None:
        print("找不到任务行", file=sys.stderr)
        raise SystemExit(2)
    print(f"任务 {task['id']} · {task['book_name'][:40]} · {task['chapter_count']} 章 · {task['ai_model']}")
    rep = check_task(task)
    print(rep.render())
    failed = rep.failed
    print(f"\n{'全部 PASS' if failed == 0 else f'{failed} 项 FAIL'}（共 {len(rep.lines)} 项）")
    raise SystemExit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
