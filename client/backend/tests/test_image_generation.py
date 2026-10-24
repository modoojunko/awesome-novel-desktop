"""c-image-generation：供应商 adapter wire/错误分类 + 任务状态机/逐候选 seed/hash。"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import uuid
from typing import ClassVar

os.environ.setdefault("IMAGE_DISPATCHER_OFF", "1")

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from api_configs.crypto import encrypt_api_key
from auth_local import deps as auth_deps
from auth_local.deps import require_tier_access
from auth_local.middleware import get_current_user
from db import async_session, get_db
from image_assets import adapters as image_adapters
from image_assets import generation as gen
from image_assets.adapters import (
    ImageGenerationSpec,
    ImageProviderError,
    capabilities_for,
    generate_images,
)
from main import app
from models.character import Character
from models.image_asset import (
    BookImageSettings,
    ImageAsset,
    ImageBatchItem,
    ImageConfig,
    ImageJob,
)
from models.project import Novel
from models.user import User

SUFFIX = uuid.uuid4().hex[:8]
USER_ID = f"imggen-{SUFFIX}"


def _run(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _png(color=(30, 80, 120)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color).save(buf, format="PNG")
    return buf.getvalue()


# ── Adapter wire／错误分类 ────────────────────────────────────────────────


class _Resp:
    def __init__(self, status=200, json_data=None, content=b"", headers=None):
        self.status_code = status
        self._json = json_data
        self.text = "" if json_data is None else str(json_data)
        self.content = content
        self.headers = headers or {"content-type": "image/png"}

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


class _Client:
    calls: ClassVar[list[tuple[str, str, dict | None]]] = []

    def __init__(self, *, post=None, get=None):
        self._post = post
        self._get = get

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None, headers=None):
        _Client.calls.append(("POST", url, json))
        return self._post

    async def get(self, url, follow_redirects=False):
        _Client.calls.append(("GET", url, None))
        return self._get


def _fake_http(monkeypatch, *, post=None, get=None):
    client = _Client(post=post, get=get)
    monkeypatch.setattr(image_adapters.httpx, "AsyncClient", lambda **kw: client)
    return client


def _spec(provider="volcengine", **kw):
    data = {
        "provider": provider,
        "model": "model-x",
        "prompt": "画面",
        "negative_prompt": "文字，水印",
        "kind": "cover",
        "n": 1,
        "seed": 123,
    }
    data.update(kw)
    return ImageGenerationSpec(**data)


@pytest.mark.asyncio
async def test_openai_wire_drops_seed_and_negative(monkeypatch, caplog):
    b64 = __import__("base64").b64encode(b"png").decode()
    _fake_http(monkeypatch, post=_Resp(json_data={"data": [{"b64_json": b64}]}))
    with caplog.at_level(logging.INFO, logger="image_gen"):
        out = await generate_images(
            base_url="https://api.openai.com/v1/", api_key="sk-secret-image-key",
            spec=_spec(provider="openai", capabilities=capabilities_for("openai")),
        )
    assert out[0].data == b"png"
    _method, url, payload = _Client.calls[-1]
    assert url == "https://api.openai.com/v1/images/generations"
    assert "seed" not in payload
    assert "避免出现" not in payload["prompt"]
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "event=image_call" in logged
    assert "sk-secret-image-key" not in logged
    assert "画面" not in logged


@pytest.mark.asyncio
async def test_volcengine_dashscope_minimax_wires(monkeypatch):
    b64 = __import__("base64").b64encode(b"png").decode()
    _fake_http(monkeypatch, post=_Resp(json_data={"data": [{"b64_json": b64}]}))
    await generate_images(base_url="https://ark.test/api/v3", api_key="sk", spec=_spec())
    _, url, payload = _Client.calls[-1]
    assert url.endswith("/images/generations")
    assert payload["seed"] == 123 and payload["watermark"] is False
    assert "避免出现" in payload["prompt"]

    _fake_http(
        monkeypatch,
        post=_Resp(json_data={"output": {"results": [{"url": "https://cdn.test/a.png"}]}}),
        get=_Resp(content=b"urlpng"),
    )
    _Client.calls.clear()
    await generate_images(
        base_url="https://dashscope.test/api/v1", api_key="sk",
        spec=_spec(provider="aliyun"),
    )
    _, url, payload = _Client.calls[0]
    assert url.endswith("/services/aigc/multimodal-generation/generation")
    assert payload["parameters"]["negative_prompt"] == "文字，水印"
    assert payload["parameters"]["seed"] == 123
    assert _Client.calls[1][0] == "GET"

    _fake_http(monkeypatch, post=_Resp(json_data={"data": [{"image_base64": b64}]}))
    await generate_images(
        base_url="https://minimax.test/v1", api_key="sk",
        spec=_spec(provider="minimax"),
    )
    _, url, payload = _Client.calls[-1]
    assert url.endswith("/image_generation")
    assert "negative_prompt" not in payload
    assert payload["seed"] == 123


@pytest.mark.asyncio
async def test_volcengine_size_contract_pixel_form(monkeypatch):
    """火山 size 必须是像素写法且满足面积下限：封面 960x1280、头像 1024x1024。"""
    b64 = __import__("base64").b64encode(b"png").decode()
    _fake_http(monkeypatch, post=_Resp(json_data={"data": [{"b64_json": b64}]}))
    out = await generate_images(base_url="https://ark.test/api/v3", api_key="sk", spec=_spec())
    _, _, payload = _Client.calls[-1]
    assert payload["size"] == "960x1280"
    assert out[0].native_width == 960 and out[0].native_height == 1280

    _fake_http(monkeypatch, post=_Resp(json_data={"data": [{"b64_json": b64}]}))
    await generate_images(base_url="https://ark.test/api/v3", api_key="sk", spec=_spec(kind="avatar"))
    _, _, payload = _Client.calls[-1]
    assert payload["size"] == "1024x1024"


@pytest.mark.asyncio
async def test_other_providers_size_unchanged(monkeypatch):
    """其他供应商尺寸口径与修复前逐字一致（c-image-volc-size-contract 只动火山）。"""
    b64 = __import__("base64").b64encode(b"png").decode()
    _fake_http(
        monkeypatch,
        post=_Resp(json_data={"output": {"results": [{"url": "https://cdn.test/a.png"}]}}),
        get=_Resp(content=b"urlpng"),
    )
    await generate_images(
        base_url="https://dashscope.test/api/v1", api_key="sk", spec=_spec(provider="aliyun"),
    )
    assert _Client.calls[0][2]["parameters"]["size"] == "1728*2368"

    _fake_http(monkeypatch, post=_Resp(json_data={"data": [{"b64_json": b64}]}))
    await generate_images(base_url="https://zhipu.test", api_key="sk", spec=_spec(provider="zhipu"))
    assert _Client.calls[-1][2]["size"] == "864x1152"

    _fake_http(monkeypatch, post=_Resp(json_data={"data": [{"b64_json": b64}]}))
    await generate_images(base_url="https://api.openai.com/v1", api_key="sk", spec=_spec(provider="openai"))
    assert _Client.calls[-1][2]["size"] == "1024x1536"

    _fake_http(monkeypatch, post=_Resp(json_data={"data": [{"image_base64": b64}]}))
    await generate_images(base_url="https://minimax.test/v1", api_key="sk", spec=_spec(provider="minimax"))
    assert _Client.calls[-1][2]["aspect_ratio"] == "3:4"


@pytest.mark.asyncio
async def test_provider_error_body_logged_without_secrets(monkeypatch, caplog):
    """供应商 4xx 报文落 image_call_error 留痕；不含 Key/prompt，超长截断 ≤500。"""
    _fake_http(monkeypatch, post=_Resp(status=400, json_data={
        "error": {
            "code": "InvalidParameter",
            "message": "The parameter `size` specified in the request are not valid",
            "param": "size",
        },
    }))
    with (
        caplog.at_level(logging.WARNING, logger="image_gen"),
        pytest.raises(ImageProviderError),
    ):
        await generate_images(
            base_url="https://ark.test/api/v3", api_key="sk-secret-image-key", spec=_spec(),
        )
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "event=image_call_error" in logged
    assert "InvalidParameter" in logged and "not valid" in logged
    assert "sk-secret-image-key" not in logged
    assert "画面" not in logged

    # 非 JSON 错误体退化为原文截断
    raw = _Resp(status=400)
    raw.text = "<html>Bad Request</html>"
    _fake_http(monkeypatch, post=raw)
    with (
        caplog.at_level(logging.WARNING, logger="image_gen"),
        pytest.raises(ImageProviderError),
    ):
        await generate_images(base_url="https://ark.test/api/v3", api_key="sk", spec=_spec())
    assert "Bad Request" in "\n".join(r.getMessage() for r in caplog.records)

    # 超长报文截断到 500 字符
    _fake_http(monkeypatch, post=_Resp(status=400, json_data={
        "error": {"code": "InvalidParameter", "message": "x" * 600},
    }))
    with (
        caplog.at_level(logging.WARNING, logger="image_gen"),
        pytest.raises(ImageProviderError),
    ):
        await generate_images(base_url="https://ark.test/api/v3", api_key="sk", spec=_spec())
    assert ("x" * 501) not in "\n".join(r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "body", "kind"),
    [
        (401, {"error": "bad key"}, "auth"),
        (402, {"error": "balance"}, "quota"),
        (429, {"error": "rate"}, "rate_limit"),
        (400, {"error": "content policy"}, "moderation"),
        (500, {"error": "server"}, "network"),
    ],
)
async def test_provider_error_classification(monkeypatch, status, body, kind):
    _fake_http(monkeypatch, post=_Resp(status=status, json_data=body))
    with pytest.raises(ImageProviderError) as e:
        await generate_images(base_url="https://x.test", api_key="sk", spec=_spec())
    assert e.value.kind == kind


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [
    "http://127.0.0.1/a.png",
    "http://10.1.2.3/a.png",
    "http://0.0.0.0/a.png",
])
async def test_download_url_rejects_private_ip_literals(monkeypatch, url):
    _fake_http(
        monkeypatch,
        post=_Resp(json_data={"data": [{"url": url}]}),
        get=_Resp(content=b"should-not-be-fetched"),
    )
    _Client.calls.clear()
    with pytest.raises(ImageProviderError) as e:
        await generate_images(
            base_url="https://zhipu.test", api_key="sk", spec=_spec(provider="zhipu"),
        )
    assert e.value.kind == "invalid"
    assert [call[0] for call in _Client.calls] == ["POST"]


@pytest.mark.asyncio
async def test_download_url_rejects_hostname_resolving_to_private_ip(monkeypatch):
    """只查 IP 字面量挡不住 foo.localhost / nip.io 这类域名（评审 P2）。"""
    async def _fake_resolve(host, port):
        assert host == "evil.test"
        return ["10.0.0.7"]

    monkeypatch.setattr(image_adapters, "_resolve_host", _fake_resolve)
    _fake_http(
        monkeypatch,
        post=_Resp(json_data={"data": [{"url": "https://evil.test/a.png"}]}),
        get=_Resp(content=b"should-not-be-fetched"),
    )
    _Client.calls.clear()
    with pytest.raises(ImageProviderError) as e:
        await generate_images(
            base_url="https://zhipu.test", api_key="sk", spec=_spec(provider="zhipu"),
        )
    assert e.value.kind == "invalid"
    assert [call[0] for call in _Client.calls] == ["POST"]  # 没有发起图片 GET


# ── 任务状态机／候选账 ────────────────────────────────────────────────────


async def _seed(provider="volcengine", characters=1, *, bind_config=True):
    suffix = uuid.uuid4().hex[:8]
    async with async_session() as db:
        if await db.get(User, USER_ID) is None:
            db.add(User(id=USER_ID, email=f"{USER_ID}@t.local", password_hash="*", display_name=USER_ID))
            await db.flush()
        novel = Novel(
            id=f"novel-{suffix}", user_id=USER_ID, name=f"生成测试书-{suffix}",
            slug=f"imggen-{suffix}", root_path=f"./data/imggen-{suffix}",
        )
        db.add(novel)
        await db.flush()
        char_ids = []
        for i in range(characters):
            ch = Character(
                id=f"char-{suffix}-{i}", novel_id=novel.id, seq=i + 1,
                name=f"角色{i}", role="主角" if i == 0 else "配角",
            )
            db.add(ch)
            char_ids.append(ch.id)
        cfg = ImageConfig(
            id=f"cfg-{suffix}", user_id=USER_ID, name=f"生成配置-{suffix}",
            provider=provider, base_url="https://provider.test",
            api_key=encrypt_api_key("sk-image"), default_model="model-x",
            models='["model-x"]', is_default=not bind_config,
        )
        db.add(cfg)
        await db.flush()
        db.add(BookImageSettings(
            novel_id=novel.id, style_key="ink", cover_prompt="一盏灯",
            cover_seed=77, image_config_id=cfg.id if bind_config else None,
            image_model="model-x",
        ))
        await db.commit()
        return novel.id, char_ids, cfg.id


@pytest.fixture()
def client():
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: {"id": USER_ID}
    app.dependency_overrides[require_tier_access] = lambda: True
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_tier_access, None)


async def _override_db():
    async with async_session() as session:
        yield session


@pytest.fixture()
def fake_images(monkeypatch):
    seen: list[ImageGenerationSpec] = []

    async def _fake(*, base_url, api_key, spec):
        seen.append(spec)
        return [image_adapters.GeneratedImage(_png((20 + len(seen), 70, 110)), 768, 1024)]

    monkeypatch.setattr(gen, "generate_images", _fake)
    return seen


@pytest.mark.asyncio
async def test_cover_job_two_candidates_have_distinct_seed_and_hash(fake_images):
    novel_id, _, _ = await _seed()
    job = await _create(novel_id, n=2)
    assert job["status"] == "queued"
    assert await gen.claim_job(job["id"])
    result = await gen.run_job(job["id"])
    assert result["status"] == "completed", result
    assert result["produced_count"] == 2 and result["billed_n"] == 2
    async with async_session() as db:
        rows = (await db.scalars(select(ImageAsset).where(
            ImageAsset.job_id == job["id"]
        ).order_by(ImageAsset.seed))).all()
    assert len(rows) == 2
    assert rows[0].seed == 77 and rows[1].seed == 78
    assert rows[0].seed != rows[1].seed
    assert rows[0].prompt_hash != rows[1].prompt_hash
    assert rows[0].source == "generation" and rows[0].provider == "volcengine"
    assert fake_images[0].seed == 77 and fake_images[1].seed == 78


@pytest.mark.asyncio
async def test_job_uses_effective_config_when_book_unbound(fake_images):
    """书未显式绑定时任务必须落到默认/生效配置，不能带 image_config_id=None。"""
    novel_id, _, cfg_id = await _seed(bind_config=False)
    job = await _create(novel_id, n=1)
    assert job["image_config_id"] == cfg_id
    assert await gen.claim_job(job["id"])
    result = await gen.run_job(job["id"])
    assert result["status"] == "completed", result
    assert result["produced_count"] == 1


@pytest.mark.asyncio
async def test_config_switch_creates_new_job():
    """换配置=换请求：config id 参与幂等键，不得复用旧任务（prompt_hash 不含它）。"""
    novel_id, _, _old_cfg = await _seed()
    job = await _create(novel_id, n=1)
    suffix = uuid.uuid4().hex[:8]
    async with async_session() as db:
        row = await db.get(ImageJob, job["id"])
        row.status = "failed"
        row.error_kind = "auth"
        await db.commit()
        new_cfg = ImageConfig(
            id=f"cfg-new-{suffix}", user_id=USER_ID, name=f"新配置-{suffix}",
            provider="volcengine", base_url="https://provider2.test",
            api_key=encrypt_api_key("sk-new"), default_model="model-x",
            models='["model-x"]', is_default=False,
        )
        db.add(new_cfg)
        await db.flush()
        settings = await db.get(BookImageSettings, novel_id)
        settings.image_config_id = new_cfg.id
        await db.commit()
        new_cfg_id = new_cfg.id

    again = await _create(novel_id, n=1)
    assert again["id"] != job["id"]
    assert again["image_config_id"] == new_cfg_id


async def _create(novel_id, **kw):
    async with async_session() as db:
        return await gen.create_job(
            db, user_id=USER_ID, novel_id=novel_id, kind="cover", **kw
        )


@pytest.mark.asyncio
async def test_openai_job_uses_prompt_variants_when_seed_unsupported(fake_images):
    novel_id, _, _ = await _seed(provider="openai")
    job = await _create(novel_id, n=2)
    assert await gen.claim_job(job["id"])
    result = await gen.run_job(job["id"])
    assert result["status"] == "completed", result
    assert all(spec.seed is None for spec in fake_images)
    assert fake_images[0].prompt != fake_images[1].prompt
    async with async_session() as db:
        rows = (await db.scalars(select(ImageAsset).where(
            ImageAsset.job_id == job["id"]
        ))).all()
    assert all(row.seed is None for row in rows)
    assert len({row.prompt_hash for row in rows}) == 2


@pytest.mark.asyncio
async def test_active_target_is_unique_and_failure_keeps_candidates(monkeypatch):
    novel_id, _, _ = await _seed()
    job = await _create(novel_id, n=2)
    assert await gen.claim_job(job["id"])
    with pytest.raises(gen.Conflict) as e:
        await _create(novel_id, n=1)
    assert e.value.code == "job_active_exists"

    calls = {"n": 0}

    async def _fake(*, base_url, api_key, spec):
        calls["n"] += 1
        if calls["n"] == 1:
            return [image_adapters.GeneratedImage(_png(), 768, 1024)]
        raise ImageProviderError("rate_limit", "供应商限流")

    monkeypatch.setattr(gen, "generate_images", _fake)
    result = await gen.run_job(job["id"])
    assert result["status"] == "failed" and result["error_kind"] == "rate_limit", result
    assert result["produced_count"] == 1
    async with async_session() as db:
        rows = (await db.scalars(select(ImageAsset).where(
            ImageAsset.job_id == job["id"]
        ))).all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_batch_idempotency_includes_character_set(fake_images):
    """同人数、同代表角色的不同角色集不得复用旧任务（评审 P1）。"""
    novel_id, chars, _ = await _seed(characters=3)
    async with async_session() as db:
        first = await gen.create_job(
            db, user_id=USER_ID, novel_id=novel_id, kind="avatar",
            purpose="batch", character_ids=[chars[0], chars[1]],
        )
    assert await gen.claim_job(first["id"])
    assert (await gen.run_job(first["id"]))["status"] == "completed"

    async with async_session() as db:
        second = await gen.create_job(
            db, user_id=USER_ID, novel_id=novel_id, kind="avatar",
            purpose="batch", character_ids=[chars[0], chars[2]],
        )
    assert second["id"] != first["id"]
    assert {i["character_id"] for i in second["items"]} == {chars[0], chars[2]}


@pytest.mark.asyncio
async def test_resubmit_after_cancel_requeues_the_same_job():
    """取消后同参数再提交必须重启，而不是把 cancelled 任务原样返回（评审 P2）。"""
    novel_id, _, _ = await _seed()
    job = await _create(novel_id, n=2)
    assert (await _cancel(job["id"]))["status"] == "cancelled"

    again = await _create(novel_id, n=2)
    assert again["id"] == job["id"]
    assert again["status"] == "queued"


@pytest.mark.asyncio
async def test_retry_after_interrupt_keeps_ledger_without_duplicate_calls(fake_images):
    """已完成候选在重试时跳过：不重复调供应商、账目保持 2 张（评审 P2）。"""
    novel_id, _, _ = await _seed()
    job = await _create(novel_id, n=2)
    assert await gen.claim_job(job["id"])
    assert (await gen.run_job(job["id"]))["status"] == "completed"
    assert len(fake_images) == 2

    # 模拟「候选已落库、job 终态未提交」时重启：sweep 只会把 job 置 failed。
    async with async_session() as db:
        row = await db.get(ImageJob, job["id"])
        row.status = "failed"
        row.error_kind = "interrupted"
        await db.commit()

    assert (await _retry(job["id"]))["status"] == "queued"
    assert await gen.claim_job(job["id"])
    result = await gen.run_job(job["id"])
    assert result["status"] == "completed", result
    assert result["produced_count"] == 2 and result["billed_n"] == 2
    assert len(fake_images) == 2
    async with async_session() as db:
        rows = (await db.scalars(select(ImageAsset).where(
            ImageAsset.job_id == job["id"]
        ))).all()
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_batch_partial_retry_keeps_existing_ledger(fake_images):
    """批量部分成功重试：produced/billed 以库内累计为准，不回落为本次重试数（评审 P2）。"""
    novel_id, chars, _ = await _seed(characters=2)
    async with async_session() as db:
        job = await gen.create_job(
            db, user_id=USER_ID, novel_id=novel_id, kind="avatar",
            purpose="batch", character_ids=chars,
        )
    assert await gen.claim_job(job["id"])

    from image_assets.service import create_generated_asset

    async with async_session() as db:
        items = list((await db.scalars(select(ImageBatchItem).where(
            ImageBatchItem.job_id == job["id"]
        ).order_by(ImageBatchItem.item_index))).all())
        await create_generated_asset(
            db, user_id=USER_ID, novel_id=novel_id, kind="avatar", data=_png(),
            character_id=chars[0], source="batch", job_id=job["id"],
            prompt_hash="hash-item-0",
        )
        items[0].status = "completed"
        items[0].produced_count = 1
        items[0].billed_n = 1
        items[1].status = "failed"
        items[1].error_kind = "rate_limit"
        row = await db.get(ImageJob, job["id"])
        row.status = "failed"
        row.error_kind = "rate_limit"
        row.produced_count = 1
        row.billed_n = 1
        await db.commit()

    assert (await _retry(job["id"]))["status"] == "queued"
    assert await gen.claim_job(job["id"])
    result = await gen.run_job(job["id"])
    assert result["status"] == "completed", result
    assert result["produced_count"] == 2 and result["billed_n"] == 2
    assert [i["status"] for i in result["items"]] == ["completed", "completed"]
    async with async_session() as db:
        rows = (await db.scalars(select(ImageAsset).where(
            ImageAsset.job_id == job["id"]
        ))).all()
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_cancel_queued_marks_items_and_startup_sweep_fails_running():
    novel_id, chars, _ = await _seed(characters=2)
    async with async_session() as db:
        job = await gen.create_job(
            db, user_id=USER_ID, novel_id=novel_id, kind="avatar",
            purpose="batch", character_ids=chars,
        )
    cancelled = await _cancel(job["id"])
    assert cancelled["status"] == "cancelled"
    assert [i["status"] for i in cancelled["items"]] == ["cancelled", "cancelled"]

    retried = await _retry(job["id"])
    assert retried["status"] == "queued"
    assert [i["status"] for i in retried["items"]] == ["pending", "pending"]
    assert await gen.claim_job(job["id"])
    assert await gen.startup_sweep() >= 1
    swept = await _get(job["id"])
    assert swept["status"] == "failed"
    assert swept["error_kind"] == "interrupted"


async def _cancel(job_id):
    async with async_session() as db:
        return await gen.cancel_job(db, user_id=USER_ID, job_id=job_id)


async def _retry(job_id):
    async with async_session() as db:
        return await gen.retry_job(db, user_id=USER_ID, job_id=job_id)


async def _get(job_id):
    async with async_session() as db:
        return await gen.get_job(db, user_id=USER_ID, job_id=job_id)


@pytest.mark.asyncio
async def test_batch_items_complete_and_cancel_keeps_candidates(fake_images):
    novel_id, chars, _ = await _seed(characters=2)
    async with async_session() as db:
        job = await gen.create_job(
            db, user_id=USER_ID, novel_id=novel_id, kind="avatar",
            purpose="batch", character_ids=chars,
        )
    assert job["target_type"] == "batch" and len(job["items"]) == 2
    assert await gen.claim_job(job["id"])
    result = await gen.run_job(job["id"])
    assert result["status"] == "completed", result
    assert [i["status"] for i in result["items"]] == ["completed", "completed"]
    assert result["produced_count"] == 2

    # 已完成候选归属对应角色，且逐项 hash 独立
    async with async_session() as db:
        rows = (await db.scalars(select(ImageAsset).where(
            ImageAsset.job_id == job["id"]
        ))).all()
    assert {r.character_id for r in rows} == set(chars)
    assert len({r.prompt_hash for r in rows}) == 2


def test_generation_endpoint_is_gated_and_creates_job(client, monkeypatch):
    novel_id, _, _ = _run(_seed())

    async def _fake_create(db, **kw):
        return {"id": "job-endpoint", "status": "queued", "mock": True, **kw}

    monkeypatch.setattr(gen, "create_job", _fake_create)
    r = client.post(f"/api/novels/{novel_id}/image-jobs", json={"kind": "cover", "n": 2})
    assert r.status_code == 201, r.text
    assert r.json()["data"]["mock"] is True


def test_generation_tier_matrix_standard_blocked_trial_allowed(monkeypatch):
    novel_id, _, _ = _run(_seed())

    async def _fake_create(db, **kw):
        return {"id": "job-tier", "status": "queued", **kw}

    async def _ensure():
        return None

    monkeypatch.setattr(auth_deps, "ensure_entitlement_snapshot", _ensure)
    monkeypatch.setattr(gen, "create_job", _fake_create)
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: {"id": USER_ID}

    def _permission(tier, features):
        return lambda: {
            "is_member": True, "expired": False, "tier": tier,
            "entitlement": {"v": 2, "features": features},
        }

    try:
        monkeypatch.setattr(
            auth_deps, "check_permission",
            _permission("standard", ["ai-plan", "ai-model"]),
        )
        with TestClient(app) as c:
            r = c.post(f"/api/novels/{novel_id}/image-jobs", json={"kind": "cover", "n": 2})
        assert r.status_code == 403, r.text
        assert r.json()["detail"]["reason"] == "feature_required"
        assert r.json()["detail"]["tier_required"] == "pro"

        monkeypatch.setattr(
            auth_deps, "check_permission",
            _permission("trial", ["ai-model", "image-generate"]),
        )
        with TestClient(app) as c:
            r = c.post(f"/api/novels/{novel_id}/image-jobs", json={"kind": "cover", "n": 2})
        assert r.status_code == 201, r.text
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


def test_generation_legacy_snapshot_implicit_allow_and_denies(monkeypatch):
    """旧快照缺 image-generate：未过期 trial/pro/max 隐式放行；standard/过期仍拒。"""
    novel_id, _, _ = _run(_seed())

    async def _fake_create(db, **kw):
        return {"id": "job-legacy", "status": "queued", **kw}

    async def _ensure():
        return None

    monkeypatch.setattr(auth_deps, "ensure_entitlement_snapshot", _ensure)
    monkeypatch.setattr(gen, "create_job", _fake_create)
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: {"id": USER_ID}

    def _permission(tier, features, *, is_member=True, expired=False):
        return lambda: {
            "tier": tier, "is_member": is_member, "expired": expired,
            "entitlement": {"v": 1, "features": features},
        }

    try:
        for tier in ("trial", "pro", "max", "monthly"):
            monkeypatch.setattr(
                auth_deps, "check_permission", _permission(tier, ["ai-model"]),
            )
            with TestClient(app) as c:
                r = c.post(
                    f"/api/novels/{novel_id}/image-jobs",
                    json={"kind": "cover", "n": 2},
                )
            assert r.status_code == 201, (tier, r.text)

        monkeypatch.setattr(
            auth_deps, "check_permission", _permission("standard", ["ai-model"]),
        )
        with TestClient(app) as c:
            r = c.post(f"/api/novels/{novel_id}/image-jobs", json={"kind": "cover", "n": 2})
        assert r.status_code == 403, r.text
        assert r.json()["detail"]["reason"] == "feature_required"

        monkeypatch.setattr(
            auth_deps, "check_permission",
            _permission("trial", ["ai-model"], is_member=False, expired=True),
        )
        with TestClient(app) as c:
            r = c.post(f"/api/novels/{novel_id}/image-jobs", json={"kind": "cover", "n": 2})
        assert r.status_code == 403, r.text
        assert r.json()["detail"]["reason"] == "member_required"
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
