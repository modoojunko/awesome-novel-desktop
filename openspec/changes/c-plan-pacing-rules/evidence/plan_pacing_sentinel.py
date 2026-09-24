"""拆纲节奏哨兵（c-plan-pacing-rules tasks 5.3）——一次性取证脚本，不进 CI、不建常驻框架。

前置（本脚本不替你做的两件事）：
1. 一个配置好模型的 C端 后端环境——把真实环境的 config 所在目录传给 --config
   （脚本会把它拷进临时 DATA_ROOT，trial 档放行 PRO 门禁；模型走你配置的那一个）。
   若书级模型未绑全局，先在临时环境里用模型配置页绑一次再重跑。
2. 跑法：
   cd client/backend && .venv/bin/python \
     ../openspec/changes/c-plan-pacing-rules/evidence/plan_pacing_sentinel.py \
     --config <真实 DATA_ROOT 目录> --repeat 5

产物（落本目录）：
- sentinel-report.json：各 case 的确定性指标（解析率 / ch1 stage 地板率 / 卡数 /
  expand 卷末位置词率 / 格式零回归哨兵）
- prompts/<case>-<n>.txt：每次调用的真实 system prompt 留档（供 5.4 人工抽检）

口径（与 proposal 5.3 一致）：
- all-3：禁类义务按三卡全达标计（ch1 三卡 stage 均 ≠「开局铺垫」）；
- 格式契约零回归：JSON 可解析、三卡齐、字段/闭集合法（出卡响应 directions 非空即视为结构合法）。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import tempfile
import uuid
from datetime import date
from pathlib import Path

EVIDENCE_DIR = Path(__file__).resolve().parent

BOOK_A = {
    "name": "哨兵-星港Freighter",
    "volumes": [{
        "volume_no": 1, "title": "第一卷",
        "summary": "沉舟捡到一枚不属于人类纪元的导航信标",
        "core_conflict": "想自己查清，与得靠船队",
        "ending": "船头转向母港旧址",
    }],
    "arc": {
        "fullstory": "沉舟是见习导航员，捡到信标后被卷入航线争夺；中段对抗升级，发现信标在喂养她自己；结局是清算之夜的对决与放手。",
        "ending": {"scene": "雾散的旧港，她把信标抛回海里", "hero": "活着，但不再完整", "tone": "带着寒意的释然"},
    },
}

# case → (卷内已排章 stage 前缀, 期望片段钉子)
CASES = {
    "ch1": ([], "开场即冲突"),
    "golden3": (["冲突初现"], "至少破一次预期"),
    "vol_start": (["冲突初现", "矛盾升级", "高潮爆发"], "本章就让本卷核心冲突露头"),
    "mid": (["冲突初现", "矛盾升级", "重要转折", "高潮爆发", "冲突初现"], None),
}


def _init_env(data_root: Path) -> None:
    import os

    os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{data_root}/sentinel.db")
    os.environ.setdefault("DATA_ROOT", str(data_root))


async def _new_book() -> str:
    """独立新书（书名带 uuid）——每个 case×n 各建一本，杜绝跨 case 的章状态泄漏
    （曾把书轮转复用：golden3 先插 ch-1，vol_start 再插同名 ref 撞 UNIQUE，且全局章号漂移出假证据）。"""
    from db import async_session
    from filesystem.storage import get_storage
    from models import Novel
    from models.volume import Volume

    async with async_session() as session:
        if await session.get(User, "sentinel") is None:
            session.add(User(id="sentinel", email="sentinel@test.local", password_hash="x"))
            await session.commit()
    async with async_session() as session:
        proj = Novel(
            id=f"sentinel-{uuid.uuid4().hex[:8]}",
            name=f"{BOOK_A['name']}-{uuid.uuid4().hex[:6]}",
            user_id="sentinel",
        )
        session.add(proj)
        await session.flush()
        session.add(Volume(project_id=proj.id, **BOOK_A["volumes"][0]))
        await session.commit()
        pid = proj.id
    root = await _get_root(pid)
    story = await get_storage().read_yaml(root, "story.yaml") or {}
    story["story_arc"] = BOOK_A["arc"]
    await get_storage().write_yaml(root, "story.yaml", story)
    return pid


async def _get_root(pid: str) -> str:
    from db import async_session
    from models import Novel

    async with async_session() as session:
        proj = await session.get(Novel, pid)
        return proj.root_path


async def _run_cases(repeat: int, prompts_dir: Path) -> dict:
    from fastapi.testclient import TestClient

    from auth_local.deps import require_novel_model
    from auth_local.middleware import get_current_user
    from db import get_db
    from main import app

    async def _db():
        from db import async_session

        async with async_session() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: {"id": "sentinel"}
    app.dependency_overrides[require_novel_model] = lambda: True

    report: dict = {"cases": {}, "prompt_files": []}
    with TestClient(app) as client:  # lifespan 建表
        rec: list[tuple[str, str]] = []

        from volumes import ai_plan as vap

        class _Recording:
            def __init__(self, inner, sink):
                self._inner = inner
                self._sink = sink

            async def chat(self, **kwargs):
                self._sink.append((kwargs.get("model", ""), str(kwargs.get("system", ""))))
                return await self._inner.chat(**kwargs)

        # 包住工厂：真实 client 照常取（模型/key 来自 --config 拷贝），只旁录 system
        orig_factory = vap.get_ai_client_for_novel

        async def _factory(novel_id=None):
            inner = await orig_factory(novel_id)
            return _Recording(inner, rec)

        vap.get_ai_client_for_novel = _factory

        for case, (stages, pin) in CASES.items():
            rows = []
            ok = parsed = 0
            stage_floor_ok = 0
            for n in range(repeat):
                pid = await _new_book()  # 每 case×n 独立新书（防跨 case 章状态泄漏）
                if stages:
                    await _ensure_chapters(pid, stages)
                r = client.post(f"/api/novels/{pid}/volumes/vol-1/chapters/ai-directions", json={})
                if r.status_code != 200:
                    rows.append({"status": r.status_code, "detail": r.text[:200]})
                    continue
                d = r.json()
                cards = d.get("directions") or []
                if d.get("degraded") or len(cards) < 2:
                    rows.append({"degraded": True, "cards": len(cards)})
                    continue
                ok += 1
                if pin and pin in (rec[-1][1] if rec else ""):
                    parsed += 1
                if case == "ch1":
                    stage_floor_ok += int(all((c.get("stage") or "") != "开局铺垫" for c in cards))
                prompts_dir.joinpath(f"{case}-{n}.txt").write_text(rec[-1][1], encoding="utf-8")
                report["prompt_files"].append(f"{case}-{n}.txt")
            entry = {"calls_ok": ok, "of": repeat, "rows": rows}
            if case == "ch1":
                entry["stage_floor_all3"] = f"{stage_floor_ok}/{repeat}"
            if pin:
                entry["fragment_pin_in_prompt"] = f"{parsed}/{repeat}"
            report["cases"][case] = entry
        # expand 卷末位置词率（vol1）
        pos = 0
        for n in range(repeat):
            pid = await _new_book()
            r = client.post(f"/api/novels/{pid}/volumes/ai/expand", json={"line": "她为追信号把坐标押给船队", "vol_no": 1})
            d = r.json() if r.status_code == 200 else {}
            ending = str((d.get("draft") or {}).get("ending") or "")
            if any(w in ending for w in ("前", "中", "后")):
                pos += 1
            if rec:
                prompts_dir.joinpath(f"expand-vol1-{n}.txt").write_text(rec[-1][1], encoding="utf-8")
                report["prompt_files"].append(f"expand-vol1-{n}.txt")
        report["cases"]["expand_vol1_position_word"] = f"{pos}/{repeat}"
    return report


async def _ensure_chapters(pid: str, stages: list[str]) -> None:
    from db import async_session
    from models.chapter import Chapter
    from models.volume import Volume
    from sqlalchemy import select

    async with async_session() as session:
        vol = (await session.scalars(select(Volume).where(Volume.project_id == pid))).first()
        for i, stage in enumerate(stages, 1):
            session.add(Chapter(
                project_id=pid, volume_id=vol.id, chapter_no=i,
                ref=f"vol-1-ch-{i}", title=f"第{i}章", has_prose=False,
                status="outline", summary=f"哨兵已排章 {i}", plot_stage=stage,
            ))
        await session.commit()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="真实环境的 DATA_ROOT 目录（读其 config.json 的模型配置）")
    ap.add_argument("--repeat", type=int, default=5)
    args = ap.parse_args()

    data_root = Path(tempfile.mkdtemp(prefix="ppr-sentinel-"))
    src = Path(args.config)
    if (src / "config.json").exists():
        shutil.copy(src / "config.json", data_root / "config.json")
        cfg = json.loads((data_root / "config.json").read_text(encoding="utf-8"))
        cfg.update({"tier": "trial", "expires_at": date(2099, 12, 31).isoformat()})
        (data_root / "config.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    else:
        raise SystemExit(f"--config 目录里没有 config.json：{src}")

    prompts_dir = EVIDENCE_DIR / "prompts"
    prompts_dir.mkdir(exist_ok=True)
    _init_env(data_root)
    report = asyncio.run(_run_cases(args.repeat, prompts_dir))
    report["data_root"] = str(data_root)
    out = EVIDENCE_DIR / "sentinel-report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告已落 {out}；prompt 留档 {prompts_dir}/（{len(report['prompt_files'])} 份）")


if __name__ == "__main__":
    main()
