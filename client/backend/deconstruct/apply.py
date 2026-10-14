"""拆书出口编排（c-deconstruct-book 3.x）——建书灌设定与本地导出。

建书幂等键 = task.book_id（**项目创建成功即先落 book_id**，后续任一写入失败重试
不再重复建书，评审 P1-7）；写入一律经既有域服务，清洗越界降级并入提示清单（不中断）：

- 简介/题材 → `novels/service.create_project(synopsis=…, genre=…)` 创建参数直入；
- 世界设定 → `settings.world_model.normalize_world/put_world_merged`（factions clamp≤6，
  截断进降级清单）；no_power 仅在文本含「无超凡/原文未明确」时置真（评审 P1-2）；
- 角色 → `settings.character_service.create_character`（role 白名单映射：核心→配角；
  同名 409 → 自动改名「名（拆书N）」重试，降级清单记录）；
- 主线 → story.yaml 的 story_arc.fullstory＝各弧拼接（评审 P0-1：直读模型 JSON）；
- 文风 → `settings.style_model.put_style` 白名单键（role=叙事身份；rules=对话/节奏条目）；
- 伏笔 → `settings.hooks_service.batch_create_hooks`（新书无章：章号并入描述文本）。

产物消费 **模型 JSON**（products_json[dim].data）——md 只是渲染展示，不做反解
（评审 P0-1：渲染键来自模型契约，反解会静默丢维度）。人物关系/章卷结构/写作技法
不建书内表：任务详情即查看处（spec v1 明示）。
"""

from __future__ import annotations

import json
import os

from sqlalchemy.ext.asyncio import AsyncSession

from filesystem.paths import KEY_TO_PATH
from models.deconstruct import SETTING_DIMENSION_KEYS, DeconstructJob

# 角色 role 白名单映射（character_model.ROLES = 主角/配角/反派/路人）
_ROLE_MAP = {"主角": "主角", "反派": "反派", "核心": "配角", "配角": "配角", "功能": "配角", "路人": "路人"}


def _raw(task: DeconstructJob) -> dict:
    try:
        return json.loads(task.products_json or "{}")
    except ValueError:
        return {}


def _data(task: DeconstructJob, dim: str) -> dict:
    obj = _raw(task).get(dim)
    return obj.get("data") if isinstance(obj, dict) else {}


def _md_map(task: DeconstructJob) -> dict[str, str]:
    out: dict[str, str] = {}
    for obj in _raw(task).values():
        if isinstance(obj, dict) and obj.get("file"):
            out[obj["file"]] = obj.get("md", "")
    return out


def _selected(task: DeconstructJob) -> list[str]:
    try:
        picked = json.loads(task.selected_dims_json or "[]")
    except ValueError:
        picked = []
    return [k for k in SETTING_DIMENSION_KEYS if k in picked]


def _files(task: DeconstructJob) -> list[str]:
    return [obj.get("file", "") for obj in _raw(task).values() if isinstance(obj, dict)]


async def import_book(
    db: AsyncSession, task: DeconstructJob, user_id: str
) -> tuple[dict, list[str]]:
    """建书：返回 ({book_id, name, skipped}, 降级提示清单)。幂等：book_id 已存在直接返回。"""
    from novels.service import create_project

    if task.book_id:
        return {"book_id": task.book_id, "name": task.book_name, "skipped": []}, []

    selected = _selected(task)
    warnings: list[str] = []
    synopsis = str(_data(task, "intro").get("intro", ""))[:600] if "intro" in selected else ""
    genre = str(_data(task, "genre").get("genre", ""))[:40] if "genre" in selected else ""

    project = await create_project(
        db,
        user_id,
        name=task.book_name,
        synopsis=synopsis,
        genre=genre,
        source="manual",
    )
    # 幂等键先落（评审 P1-7）：后续任一写入失败，重试不再重复建书
    task.book_id = project.id
    await db.commit()

    root = project.root_path
    from filesystem.storage import get_storage

    storage = get_storage()

    if "world" in selected:
        data = _data(task, "world")
        raw = await storage.read_yaml(root, KEY_TO_PATH["world"]) or {}
        from settings.world_model import normalize_world, put_world_merged

        no_power_txt = str(data.get("no_power", ""))
        body = {
            # 评审 P1-2 口径：仅当模型输出含「无超凡/原文未明确」才置真，不凭空断言力量体系
            "no_power": "无超凡" in no_power_txt or "原文未明确" in no_power_txt,
            "stage": str(data.get("stage", ""))[:300],
            "power": [
                {"name": str(i.get("name", ""))[:40], "note": str(i.get("rule", ""))[:200]}
                for i in (data.get("power") or []) if isinstance(i, dict)
            ],
            "cost": [
                {"name": str(i.get("name", ""))[:40], "note": str(i.get("rule", i.get("note", "")))[:200]}
                for i in (data.get("cost") or []) if isinstance(i, dict)
            ],
            "history": [
                {"name": str(i.get("name", ""))[:40], "note": f"{i.get('note', '')}（{i.get('evidence_ch', '原文未明确')}）"}
                for i in (data.get("history") or []) if isinstance(i, dict)
            ],
            "factions": [
                {"name": str(i.get("name", ""))[:40], "note": f"{i.get('note', '')}（{i.get('evidence_ch', '原文未明确')}）"}
                for i in (data.get("factions") or []) if isinstance(i, dict)
            ],
            "constraints": [
                {"name": str(i.get("name", ""))[:40], "note": str(i.get("note", ""))[:200]}
                for i in (data.get("constraints") or []) if isinstance(i, dict)
            ],
            "extra": [
                {"name": str(i.get("name", ""))[:40], "note": str(i.get("note", ""))[:200]}
                for i in (data.get("extra") or []) if isinstance(i, dict)
            ],
        }
        fac_before = len(body["factions"])
        merged = put_world_merged(raw, normalize_world(body))
        if fac_before > 6:
            warnings.append(f"世界设定势力 {fac_before} 方超出上限 6，已截断保留前 6 方")
        await storage.write_yaml(root, KEY_TO_PATH["world"], merged)

    if "characters" in selected:
        from settings.character_service import Conflict, create_character

        for i, card in enumerate(_cards(task), start=1):
            name = str(card.get("name") or "").strip() or f"未命名{i}"
            role = _ROLE_MAP.get(str(card.get("role", "")), "配角")
            for attempt in range(1, 6):
                try:
                    await create_character(
                        db,
                        project.id,
                        name=name,
                        role=role,
                        dossier={
                            "plot": str(card.get("plot", ""))[:300],
                            "background": str(card.get("background", ""))[:300],
                        },
                    )
                    break
                except Conflict:
                    if attempt == 5:
                        warnings.append(f"角色「{name}」多次同名冲突，已跳过")
                        break
                    name = f"{name}（拆书{attempt}）"

    if "mainplot" in selected:
        data = _data(task, "mainplot")
        story = await storage.read_yaml(root, KEY_TO_PATH["story"]) or {}
        arc = story.get("story_arc") if isinstance(story.get("story_arc"), dict) else {}
        arcs = [
            f"{a.get('title', '')}（第{a.get('ch_start', '?')}-{a.get('ch_end', '?')}章）：{a.get('summary', '')}"
            for a in (data.get("arcs") or []) if isinstance(a, dict)
        ]
        arc["fullstory"] = ("；".join(arcs) or str(data.get("ending", "")) or "原文未明确")[:2000]
        story["story_arc"] = arc
        await storage.write_yaml(root, KEY_TO_PATH["story"], story)

    if "style" in selected:
        from settings.style_model import put_style

        data = _data(task, "style")
        raw = await storage.read_yaml(root, KEY_TO_PATH["style"]) or {}
        body = {
            "role": str(data.get("narration", ""))[:500],
            "rules": [
                str(r)[:200]
                for r in ([data.get("dialogue", ""), data.get("rhythm", "")] if data.get("dialogue") or data.get("rhythm") else [])
            ],
        }
        await storage.write_yaml(root, KEY_TO_PATH["style"], put_style(raw, body))

    if "foreshadow" in selected:
        from settings.hooks_service import batch_create_hooks

        items = _hooks_items(task)
        result = await batch_create_hooks(db, project.id, items)
        if result.get("truncated"):
            warnings.append(f"伏笔超出单次上限，已收 {result['truncated']} 条")

    return (
        {
            "book_id": project.id,
            "name": project.name,
            "skipped": [d for d in SETTING_DIMENSION_KEYS if d not in selected],
        },
        warnings,
    )


def _cards(task: DeconstructJob) -> list[dict]:
    cards: list[dict] = []
    for c in _data(task, "characters").get("characters") or []:
        if not isinstance(c, dict):
            continue
        cards.append(
            {
                "name": str(c.get("name", ""))[:30],
                "role": str(c.get("role", "配角")),
                "plot": f"{c.get('plot', '')}（{c.get('evidence_ch', '原文未明确')}）",
                "background": str(c.get("background", ""))[:300],
            }
        )
    return cards


def _hooks_items(task: DeconstructJob) -> list[dict]:
    items: list[dict] = []
    for h in _data(task, "foreshadow").get("hooks") or []:
        if not isinstance(h, dict):
            continue
        desc = str(h.get("desc", ""))[:300]
        plant = h.get("plant_ch")
        if plant not in (None, "原文未明确"):
            desc = f"{desc}（埋设于第{plant}章）"
        items.append({"description": desc, "planned_volume_no": None})
    return items


def _sha256(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_manifest(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def export_products(
    task: DeconstructJob, dest_dir: str, selected_files: list[str], graph: dict | None = None
) -> dict:
    """导出到本地文件夹：勾中 md＋图谱三件套（固定附带）＋README＋`导出清单.json`。

    评审纪律：**内存装配先行**——全部内容在内存成形后才落笔（渲染异常零写入）；
    清单（sha256 账）最后写：磁盘文件与清单不符（手改/外来）者，本导出先转 `.bak-时间戳` 再写。
    """
    from datetime import UTC, datetime

    from deconstruct.render import render_html, render_svg

    products = _md_map(task)
    if not dest_dir or not os.path.isabs(dest_dir):
        raise OSError("invalid_path", f"导出目录非法：{dest_dir!r}")

    payload: dict[str, str] = {}
    written: list[str] = []
    for fn in selected_files:
        text = products.get(fn)
        if text is None:
            continue
        safe = fn.replace("/", "_").replace("\\", "_")
        payload[safe] = text
        written.append(safe)
    graph_files: list[str] = []
    if graph is not None:
        trio = {
            "图谱.json": json.dumps(graph, ensure_ascii=False, indent=2) + "\n",
            "图谱.html": render_html(graph),
            "图谱.svg": render_svg(graph),
        }
        payload.update(trio)
        graph_files = list(trio)

    readme = ["# 拆书产物目录", "", f"书名：{task.book_name}", "", "## Markdown 产物（可勾选）"]
    readme += [f"- {fn}" for fn in sorted(products)]
    if graph is not None:
        readme += ["", "## 知识图谱（固定附带，不参与勾选）"]
        readme += ["- 图谱.json（唯一机器正身）", "- 图谱.html（双击浏览器打开，离线可用）", "- 图谱.svg（静态图）"]
    readme += [
        "",
        (
            "> 本目录内文件均为导出副本：手改不会回流应用；需要更新请回任务重新导出"
            "（被改过的旧文件将转 .bak-时间戳 备份保留）。"
        ),
    ]
    payload["README.md"] = "\n".join(readme) + "\n"

    os.makedirs(dest_dir, exist_ok=True)
    manifest_path = os.path.join(dest_dir, "导出清单.json")
    recorded = _load_manifest(manifest_path).get("files")
    recorded = recorded if isinstance(recorded, dict) else {}
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    backups: list[str] = []
    for name, content in payload.items():
        target = os.path.join(dest_dir, name)
        if os.path.exists(target):
            disk_text: str | None
            try:
                with open(target, encoding="utf-8") as f:
                    disk_text = f.read()
            except OSError:
                disk_text = None
            if disk_text is None or recorded.get(name) != _sha256(disk_text):
                bak = f"{name}.bak-{stamp}"
                os.replace(target, os.path.join(dest_dir, bak))
                backups.append(bak)
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
    manifest = {
        "task": task.id,
        "book": task.book_name,
        "contract": "deconstruct-graph/6" if graph is not None else "document-only",
        "exported_at": datetime.now(UTC).replace(tzinfo=None).isoformat(),
        "files": {name: _sha256(text) for name, text in payload.items()},
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return {
        "written": written,
        "graph": graph_files,
        "readme": "README.md",
        "dest": dest_dir,
        "backups": backups,
    }
