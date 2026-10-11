"""例句提炼（fewshot-mine）行为钉——c-fewshot-json-contract。

回归背景（2026-10-11 真机实锤）：style_fewshot_mine 模板 v2 分层迁移时把「只输出
JSON」整句迁丢，DeepSeek 等供应商对 response_format=json_object 硬性要求提示词含
「json」字样——「例句提炼」在 enforce 该规则的供应商上 400 整单拒收（GLM/Anthropic
不 enforce，开发自测未复现；fewshot-mine 此前全链零测试）。

分工：仓库不变量守卫住提示词仓（其 tests/test_json_contract.py，与模板同仓才有
CI 牙齿——C端 CI 无模板源）；本文件钉 C端 调用面三条：实发提示词（system＋user）
含 json 字样、模板声明 lines 输出契约、端点按 lines 解析返回。

桩法照 test_style_settings_v2._install_fake_distill（捕获层多记 system/json_mode）。
缺模板源环境（CI 单仓检出）：conftest 缺源转跳纪律兜底（PromptPackMissing→skip）。

Usage:
    cd client/backend
    PROMPT_PACK_DEV_DIR=<提示词仓>/prompts python -m pytest tests/test_style_fewshot_mine.py -v
"""

import os
import tempfile
import uuid

import pytest
from fastapi.testclient import TestClient

# ── Test environment ─────────────────────────────────────────────────────
_tmp_db = tempfile.NamedTemporaryFile(suffix="_test_fewshot.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_fewshot_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

from auth_local.deps import (  # noqa: E402
    require_ai_access,
    require_novel_model,
    require_project_limit,
)
from auth_local.middleware import get_current_user  # noqa: E402
from main import app  # noqa: E402

_URL = "/api/novels/{pid}/settings/ai/style/fewshot-mine"


@pytest.fixture(autouse=True)
def _override_auth_gates():
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1"}
    app.dependency_overrides[require_ai_access] = lambda: True
    app.dependency_overrides[require_novel_model] = lambda: True
    app.dependency_overrides[require_project_limit] = lambda: True
    yield
    for key in (get_current_user, require_ai_access, require_novel_model, require_project_limit):
        app.dependency_overrides.pop(key, None)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def pid(client) -> str:
    name = "例句钉" + uuid.uuid4().hex[:6]
    r = client.post("/api/novels", json={"name": name, "source": "manual"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _seed_archived_chapter(pid: str, title: str, content: str) -> None:
    """直落 Volume/Chapter/ChapterContent/Archive 四行（照 test_backup_export 手法）。"""
    import asyncio

    from sqlalchemy import select

    from db import async_session
    from models.archive import Archive
    from models.chapter import Chapter, ChapterContent
    from models.project import Novel
    from models.volume import Volume

    async def _seed():
        async with async_session() as session:
            proj = (await session.scalars(select(Novel).where(Novel.id == pid))).one()
            vol = Volume(project_id=proj.id, volume_no=1, title="第一卷")
            session.add(vol)
            await session.flush()
            ch = Chapter(
                project_id=proj.id, volume_id=vol.id, chapter_no=1, ref="vol-1-ch-1",
                title=title, status="archived", word_count=len(content), has_prose=True,
            )
            session.add(ch)
            await session.flush()
            session.add(ChapterContent(chapter_id=ch.id, prose=content))
            session.add(Archive(chapter_id=ch.id, title=title, summary="", content=content))
            await session.commit()

    asyncio.run(_seed())


def _install_fake_chat(monkeypatch, payload: str) -> list[dict]:
    """假 AI 客户端：捕获实发 system/prompt/json_mode，按序回指定文本。"""
    import settings.ai_router as ar

    calls: list[dict] = []

    class _Fake:
        async def chat(self, **kwargs):
            calls.append(
                {
                    "system": kwargs.get("system", ""),
                    "prompt": kwargs["messages"][0]["content"],
                    "json_mode": kwargs.get("json_mode"),
                }
            )
            return payload

    async def _fake(novel_id):
        return _Fake()

    monkeypatch.setattr(ar, "get_ai_client_for_novel", _fake)
    return calls


class TestFewshotMine:
    def test_request_carries_json_word_and_lines_contract(self, client, pid, monkeypatch):
        _seed_archived_chapter(pid, "第七章 夜探药庐", "他推开虚掩的门，药味先撞了上来。" * 5)
        calls = _install_fake_chat(
            monkeypatch,
            '{"lines": ["他推开虚掩的门，药味先撞了上来。", "她把账本推到桌子中间。"]}',
        )

        r = client.post(_URL.format(pid=pid), json={})

        assert r.status_code == 200, r.text
        assert r.json()["lines"] == [
            "他推开虚掩的门，药味先撞了上来。",
            "她把账本推到桌子中间。",
        ]
        # 本 change 的核心回归钉：json_object 请求的生效提示词必须含「json」字样
        # （DeepSeek 前置校验），且调用确实走了 JSON 响应模式
        call = calls[0]
        assert call["json_mode"] is True
        assert "json" in (call["system"] + call["prompt"]).lower()
        # 输出契约在 system 恒定段：lines 键＋原文摘录口径
        assert "lines" in call["system"]
        assert "原文摘录" in call["system"]
        # 归档语料真实进 user 段（标题＋正文注入，{corpus} 占位符实替换）
        assert "【第七章 夜探药庐】" in call["prompt"]
        assert "药味先撞了上来" in call["prompt"]

    def test_no_archive_400_copy_unchanged(self, client, pid, monkeypatch):
        _install_fake_chat(monkeypatch, '{"lines": ["不应被消费"]}')
        r = client.post(_URL.format(pid=pid), json={})
        assert r.status_code == 400
        assert "还没有已归档章节" in r.json()["detail"]

    def test_malformed_response_502(self, client, pid, monkeypatch):
        """lines 缺失/空 → 既有 502 口径不回灌（响应按 lines 解析的负面钉）。"""
        _seed_archived_chapter(pid, "第八章", "正文内容。" * 5)
        _install_fake_chat(monkeypatch, '{"other": ["不是例句"]}')
        r = client.post(_URL.format(pid=pid), json={})
        assert r.status_code == 502
        assert "例句提炼返回结构不对" in r.json()["detail"]
