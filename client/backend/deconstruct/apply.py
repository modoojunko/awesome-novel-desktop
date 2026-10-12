"""拆书出口编排（c-deconstruct-book 3.x）——建书灌设定与本地导出。

建书幂等键 = task.book_id（重复确认返回同一本书）；写入一律经既有域服务
（不直写表），清洗越界降级并入提示清单（不报错中断）：

- 简介/题材 → `novels/service.create_project(synopsis=…, genre=…)` 创建参数直入；
- 世界设定 → `settings.world_model.normalize_world/put_world_merged`（factions clamp≤6，
  越界截断进降级清单）写 `KEY_TO_PATH["world"]`；
- 角色 → `settings.character_service.create_character`（role 白名单映射；同名 409 →
  自动改名「名（拆书N）」重试，降级清单记录）；
- 主线 → story.yaml 的 story_arc.fullstory（既有消费点 write/prompt_sources.py）；
- 文风 → `settings.style_model.put_style` 白名单键（role + 手法清单）；
- 伏笔 → `settings.hooks_service.batch_create_hooks`（新书无章：章引用 FK 置空，
  章号并入文本）。

人物关系/章卷结构/写作技法不建书内表：任务详情即查看处（spec v1 明示）。
"""

from __future__ import annotations

import json
import os

from sqlalchemy.ext.asyncio import AsyncSession

from filesystem.paths import KEY_TO_PATH
from models.deconstruct import SETTING_DIMENSION_KEYS, DeconstructJob

# 角色 role 白名单映射（character_service.ROLES：主角/配角/反派/…以域内为准）
_ROLE_MAP = {"主角": "主角", "配角": "配角", "反派": "反派", "核心": "配角", "功能": "配角"}


def _products(task: DeconstructJob) -> dict[str, str]:
    try:
        return json.loads(task.products_json or "{}")
    except ValueError:
        return {}


def _selected(task: DeconstructJob) -> list[str]:
    try:
        picked = json.loads(task.selected_dims_json or "[]")
    except ValueError:
        picked = []
    return [k for k in SETTING_DIMENSION_KEYS if k in picked]


def _load_products_json(task: DeconstructJob) -> dict:
    """按维度 key 取模型 JSON（渲染前缓存于 error_json 不现实——从 md 反解不可靠，
    因此 apply 只消费 md 文本中固定 H2 结构 + 粗粒度字段，写入函数各自 clamp。"""
    return {}


async def import_book(
    db: AsyncSession, task: DeconstructJob, user_id: str
) -> tuple[dict, list[str]]:
    """建书：返回 ({book_id, name, skipped}, 降级提示清单)。幂等：book_id 已存在直接返回。"""
    from novels.service import create_project

    if task.book_id:
        return {"book_id": task.book_id, "name": task.book_name, "skipped": []}, []

    selected = _selected(task)
    products = _products(task)
    warnings: list[str] = []
    synopsis = ""
    genre = ""
    if "intro" in selected:
        synopsis = _h2_body(products, "简介.md", "intro")[:600]
    if "genre" in selected:
        genre = _h2_body(products, "题材.md", "genre").splitlines()[0][:40] if _h2_body(products, "题材.md", "genre") else ""

    project = await create_project(
        db,
        user_id,
        name=task.book_name,
        synopsis=synopsis,
        genre=genre,
        source="manual",
    )

    root = project.root_path
    from filesystem.storage import get_storage

    storage = get_storage()

    if "world" in selected:
        raw = await storage.read_yaml(root, KEY_TO_PATH["world"]) or {}
        from settings.world_model import normalize_world, put_world_merged

        body = _world_body(products)
        before = len(body.get("factions", []))
        merged = put_world_merged(raw, normalize_world(body))
        if before > 6:
            warnings.append(f"世界设定势力 {before} 方超出上限 6，已截断保留前 6 方")
        await storage.write_yaml(root, KEY_TO_PATH["world"], merged)

    if "characters" in selected:
        from settings.character_service import Conflict, create_character

        for i, card in enumerate(_cards(products), start=1):
            name = str(card.get("name") or "").strip() or f"未命名{i}"
            role = _ROLE_MAP.get(str(card.get("role", "")), "配角")
            for attempt in range(1, 6):
                try:
                    await create_character(
                        db,
                        project.id,
                        name=name,
                        role=role,
                        aliases=[],
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
        story = await storage.read_yaml(root, KEY_TO_PATH["story"]) or {}
        arc = story.get("story_arc") if isinstance(story.get("story_arc"), dict) else {}
        arc["fullstory"] = _h2_body(products, "主线剧情.md", "mainplot")[:2000]
        story["story_arc"] = arc
        await storage.write_yaml(root, KEY_TO_PATH["story"], story)

    if "style" in selected:
        from settings.style_model import put_style

        raw = await storage.read_yaml(root, KEY_TO_PATH["style"]) or {}
        body = _style_body(products)
        merged = put_style(raw, body)
        await storage.write_yaml(root, KEY_TO_PATH["style"], merged)

    if "foreshadow" in selected:
        from settings.hooks_service import batch_create_hooks

        items = _hooks_items(products)
        result = await batch_create_hooks(db, project.id, items)
        if result.get("truncated"):
            warnings.append(f"伏笔超出单次上限，已收 {result['truncated']} 条")

    task.book_id = project.id
    await db.commit()
    return (
        {"book_id": project.id, "name": project.name, "skipped": [d for d in SETTING_DIMENSION_KEYS if d not in selected]},
        warnings,
    )


def _h2_body(products: dict[str, str], filename: str, key: str) -> str:
    """取渲染 md 里 `## {key}` 段的正文（渲染器键序稳定，反解可靠）。"""
    text = products.get(filename, "")
    marker = f"\n## {key}\n"
    if marker not in text:
        return ""
    body = text.split(marker, 1)[1]
    body = body.split("\n## ", 1)[0]
    return body.strip()


def _world_body(products: dict[str, str]) -> dict:
    """从 世界设定.md 的固定 H2 反解为 WorldIn 形状（normalize 会再 clamp）。"""
    world: dict = {"no_power": "", "stage": "", "power": "", "cost": "", "history": [], "factions": [], "constraints": [], "extra": []}
    for key in ("no_power", "stage", "power", "cost"):
        body = _h2_body(products, "世界设定.md", key)
        if body:
            world[key] = body[:300]
    entries = _h2_list(products, "世界设定.md", "history")
    world["history"] = [{"name": e.split("：")[0][:30], "note": e[:200]} for e in entries]
    fac_entries = _h2_list(products, "世界设定.md", "factions")
    world["factions"] = [{"name": e.split("：")[0][:30], "note": e[:200]} for e in fac_entries]
    world["constraints"] = [{"name": e.split("：")[0][:30], "note": e[:200]} for e in _h2_list(products, "世界设定.md", "constraints")]
    world["extra"] = [{"name": e.split("：")[0][:30], "note": e[:200]} for e in _h2_list(products, "世界设定.md", "extra")]
    return world


def _h2_list(products: dict[str, str], filename: str, key: str) -> list[str]:
    text = products.get(filename, "")
    marker = f"\n## {key}\n"
    if marker not in text:
        return []
    body = text.split(marker, 1)[1].split("\n## ", 1)[0]
    return [ln.lstrip("- ").strip() for ln in body.splitlines() if ln.strip().startswith("- ")]


def _cards(products: dict[str, str]) -> list[dict]:
    cards: list[dict] = []
    for line in _h2_list(products, "角色设定.md", "characters"):
        # 行形状：**名**　role：…；plot：…；background：…
        name = line.split("**")[1].strip() if "**" in line else line.split("：")[0].strip()
        fields: dict[str, str] = {}
        for part in line.split("；"):
            if "：" in part:
                k, v = part.split("：", 1)
                fields[k.strip().strip("*")] = v.strip()
        cards.append(
            {
                "name": name[:30],
                "role": fields.get("role", "配角"),
                "plot": fields.get("plot", ""),
                "background": fields.get("background", ""),
            }
        )
    return cards


def _style_body(products: dict[str, str]) -> dict:
    body: dict = {}
    for key in ("narration", "dialogue", "rhythm"):
        text = _h2_body(products, "写作文风.md", key)
        if text:
            body[key] = text[:200]
    features = _h2_list(products, "写作文风.md", "features")
    if features:
        body["features"] = [f[:60] for f in features[:20]]
    return body


def _hooks_items(products: dict[str, str]) -> list[dict]:
    items: list[dict] = []
    for line in _h2_list(products, "伏笔.md", "hooks"):
        desc = line[:200]
        plant_ch = _chapter_no(line, "埋设")
        items.append({"description": desc, "planted_chapter_no": plant_ch, "note": ""})
    return items


def _chapter_no(line: str, keyword: str) -> int | None:
    import re

    m = re.search(rf"{keyword}[^0-9]*(\d+)", line)
    return int(m.group(1)) if m else None


def export_products(task: DeconstructJob, dest_dir: str, selected_files: list[str]) -> dict:
    """导出勾中产物＋README 到本地文件夹（物化副本；产物保留不受影响）。"""
    products = _products(task)
    if not dest_dir or not os.path.isabs(dest_dir):
        raise OSError("invalid_path", f"导出目录非法：{dest_dir!r}")
    os.makedirs(dest_dir, exist_ok=True)
    written = []
    for fn in selected_files:
        text = products.get(fn)
        if text is None:
            continue
        safe = fn.replace("/", "_").replace("\\", "_")
        with open(os.path.join(dest_dir, safe), "w", encoding="utf-8") as f:
            f.write(text)
        written.append(safe)
    readme = ["# 拆书产物目录", "", f"书名：{task.book_name}", ""]
    readme += [f"- {fn}" for fn in sorted(products)]
    with open(os.path.join(dest_dir, "README.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(readme) + "\n")
    return {"written": written, "readme": "README.md", "dest": dest_dir}
