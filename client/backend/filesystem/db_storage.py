"""DatabaseFileBackend — project_settings 表 KV 后端（ADR-001/002）。

只做 8 类单文件设定 + 字符目录的 project_settings 表 upsert/get/list/delete，
不直接处理业务。新项目种子由 seed_settings_to_db() 承担（建书调用点直呼）。
「LocalFileBackend 盘上文件存储」已退役（c-retire-local-file-storage）——
content 列唯一正规形状是 JSON dict，非 settings 路由的路径读 `{}`、写 no-op。
"""

import json
import logging

import yaml
from sqlalchemy import select

from db import async_session
from filesystem.paths import CHARACTER_DIR, CHARACTER_PREFIX, route_relative_path
from models.project_setting import ProjectSetting

logger = logging.getLogger("uvicorn.error")

_NOT_JSON = object()  # 哨兵：content 不是合法 JSON（区别于解析出 null）


def _parse_content(root_path: str, key: str, content: object) -> dict:
    """content 解析容错：JSON dict 是唯一正规形状（write_yaml 只产 JSON）。

    非 dict 一律置空并告警——包括「合法 JSON 但非 dict」（null/标量/数组）：
    调用方的 ``or {}`` 只接得住 falsy，truthy 标量照样炸消费者（评审实证
    archive/service.py update_thread_state 对 threads 连 or {} 都没有）。
    非 JSON 文本按 YAML 抢救（有损：YAML 1.1 会把 no/on、日期、007 强转，
    仅坏行才触发，可接受），救不回也给空。置空必须告警——坏行会在下次
    保存时被覆盖，无日志即无痕丢失。坏一行不得炸整本书（readiness/拆章/
    世界页全走这里，2026-09-30 实锤）。
    """

    def _empty(stage: str) -> dict:
        logger.warning(
            "settings KV 行不可解析，按空处理（root=%s key=%s stage=%s head=%.80r）",
            root_path, key, stage, content,
        )
        return {}

    if not isinstance(content, str):
        return _empty("non-str")  # 手写 SQL 塞进来的 NULL/异形（DDL NOT NULL 之外的口子）
    try:
        data = json.loads(content)
    except (ValueError, TypeError):
        data = _NOT_JSON
    if data is not _NOT_JSON:
        return data if isinstance(data, dict) else _empty("json-non-dict")
    try:
        rescued = yaml.safe_load(content)
    except Exception:  # noqa: BLE001 —— 解析边界的职责就是「绝不抛」
        return _empty("unparseable")
    if isinstance(rescued, dict):
        logger.warning(
            "settings KV 行非 JSON，已按 YAML 抢救（root=%s key=%s）——下次保存自动转正",
            root_path, key,
        )
        return rescued
    return _empty("yaml-non-dict")


class DatabaseFileBackend:
    async def read_yaml(self, root_path: str, relative_path: str) -> dict:
        key = route_relative_path(relative_path)
        if key is None:
            return {}
        async with async_session() as session:
            row = await session.get(ProjectSetting, (root_path, key))
            if row is None:
                return {}
            return _parse_content(root_path, key, row.content)

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
