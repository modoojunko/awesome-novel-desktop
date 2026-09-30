"""DatabaseFileBackend — project_settings 表 KV 后端（ADR-001/002）。

只做 8 类单文件设定 + 字符目录的 project_settings 表 upsert/get/list/delete，
不直接处理业务。init_skeleton 的 DB 种子由 seed_settings_to_db() 承担；
本地骨架委托 LocalFileBackend（见 composite_storage）。
"""

import json

import yaml
from sqlalchemy import delete, select

from db import async_session
from filesystem.paths import CHARACTER_DIR, CHARACTER_PREFIX, route_relative_path
from models.project_setting import ProjectSetting


def _parse_content(content: str) -> dict:
    """content 解析容错：JSON 是唯一正规形状（write_yaml 只产 JSON）；
    非 JSON（外部手修残留裸 YAML 等）按 YAML 抢救，仍不成才给空——
    坏一行不得炸整本书（readiness/拆章/世界页全走这里，2026-09-30 实锤）。"""
    try:
        return json.loads(content)
    except (ValueError, TypeError):
        pass
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


class DatabaseFileBackend:
    async def read_yaml(self, root_path: str, relative_path: str) -> dict:
        key = route_relative_path(relative_path)
        if key is None:
            return {}
        async with async_session() as session:
            row = await session.get(ProjectSetting, (root_path, key))
            if row is None:
                return {}
            return _parse_content(row.content)

    async def write_yaml(self, root_path: str, relative_path: str, data: dict) -> None:
        key = route_relative_path(relative_path)
        if key is None:
            return
        async with async_session() as session:
            row = await session.get(ProjectSetting, (root_path, key))
            if row is None:
                session.add(
                    ProjectSetting(
                        root_path=root_path,
                        key=key,
                        content=json.dumps(data, ensure_ascii=False),
                    )
                )
            else:
                row.content = json.dumps(data, ensure_ascii=False)
            await session.commit()

    async def delete_file(self, root_path: str, relative_path: str) -> None:
        key = route_relative_path(relative_path)
        if key is None:
            return
        async with async_session() as session:
            row = await session.get(ProjectSetting, (root_path, key))
            if row is not None:
                await session.delete(row)
                await session.commit()

    async def list_dir(self, root_path: str, relative_path: str = "") -> list[str]:
        """字符目录 → 带 .yaml 后缀的文件名列表（readiness/router 依赖 .endswith）。"""
        if relative_path != CHARACTER_DIR:
            return []
        async with async_session() as session:
            result = await session.execute(
                select(ProjectSetting.key).where(
                    ProjectSetting.root_path == root_path,
                    ProjectSetting.key.like(CHARACTER_PREFIX + "%"),
                )
            )
            keys = result.scalars().all()
        return [k[len(CHARACTER_PREFIX) :] for k in keys]

    async def delete_root(self, root_path: str) -> None:
        """清 root_path 全部行（防孤儿行，ADR-002）。"""
        async with async_session() as session:
            await session.execute(
                delete(ProjectSetting).where(ProjectSetting.root_path == root_path)
            )
            await session.commit()

    async def has_key(self, root_path: str, key: str) -> bool:
        async with async_session() as session:
            return await session.get(ProjectSetting, (root_path, key)) is not None


async def seed_settings_to_db(root_path: str) -> None:
    """新项目种子：settings 模板只进 DB 不进盘（ADR-003）。

    模板默认值 count as content（readiness 判定依赖行存在）。
    """
    from filesystem.init import SETTINGS_TEMPLATES, TEMPLATE_DIR

    backend = DatabaseFileBackend()
    for template_name, (relative_path, _key) in SETTINGS_TEMPLATES.items():
        src = TEMPLATE_DIR / template_name
        if src.exists():
            data = yaml.safe_load(src.read_text(encoding="utf-8")) or {}
        else:
            data = {}
        await backend.write_yaml(root_path, relative_path, data)
