"""归档服务残件（c-chapter-dossier 后）——摘要生成、AI 记账、threads 状态。

归档主流程（受理→提取→收口）已迁 archive/dossier.py；本模块保留三件被
多方引用的零件。门禁豁免（ai_client.py grep ④）：本文件是 try/except 降级
路径（摘要失败降级正文前 200 字），非 require_novel_model 门控对象。
"""

from filesystem.storage import get_storage


def _validate_ref(ref: str) -> str:
    if ".." in ref or "/" in ref:
        raise ValueError("Invalid chapter reference")
    return ref


async def _record_ai_usage(
    novel_id: str, operation: str, usage: dict, *, force: bool = False
) -> None:
    """归档链 AI 调用记账（ai-client capability 需求 2）：自开 session，
    从 Novel 行取 user/模型口径；记账失败不影响归档主流程。"""
    try:
        from api_configs.usage import record_usage
        from db import async_session
        from models.project import Novel

        async with async_session() as session:
            novel = await session.get(Novel, novel_id)
            if novel is None:
                return
            await record_usage(
                session,
                user_id=novel.user_id,
                project_id=novel_id,
                api_config_id=novel.ai_config_id,
                operation=operation[:50],
                model=novel.ai_model or "haiku",
                tokens_in=usage.get("tokens_in", 0),
                tokens_out=usage.get("tokens_out", 0),
                force=force,
            )
    except Exception:  # noqa: BLE001, S110 — 记账失败不影响归档
        pass


async def make_archive_summary(novel_id: str, full_text: str, ai_summary: bool = True) -> str:
    """归档摘要：AI 200 字；模型未就绪/调用失败/用户关摘要 → 正文前 200 字降级。"""
    summary = full_text[:200]
    if not ai_summary:
        return summary
    usage: dict = {}
    # 函数内动态解析：本模块常在后台线程首次懒导入，模块级 import 会把当时的
    # monkeypatch/绑定永久钉进命名空间（测试互污染实锤）；ai_client 属性随取随用
    from ai_client import get_ai_client_for_novel

    try:
        client = await get_ai_client_for_novel(novel_id)
    except Exception:  # noqa: BLE001 — 模型未就绪：调用未发生，不记账
        return summary
    try:
        from prompts import load_layers

        _s_sum, _u_sum = load_layers("archive_summary")
        summary_text = await client.chat(
            model="haiku",
            system=_s_sum,
            messages=[{"role": "user", "content": _u_sum.format(full_text=full_text)}],
            max_tokens=200,
            usage=usage,
        )
        await _record_ai_usage(novel_id, "archive_summary", usage)
        if summary_text:
            summary = summary_text[:200]
    except Exception:  # noqa: BLE001, S110 — AI 摘要可选，失败降级为正文前 200 字
        await _record_ai_usage(novel_id, "archive_summary_fail", usage, force=True)
    return summary


async def update_thread_state(root_path: str, chapter: dict, summary: str):
    threads = await get_storage().read_yaml(root_path, "threads.yaml")
    thread_name = chapter.get("thread", "主线")

    if "threads" not in threads:
        threads["threads"] = {}
    if thread_name not in threads["threads"]:
        threads["threads"][thread_name] = {}

    t = threads["threads"][thread_name]
    t["pov"] = chapter.get("pov_character", t.get("pov", "未知"))
    t["last_chapter"] = f"vol-{chapter.get('volume')}-ch-{chapter.get('chapter')}"
    t["current_state"] = summary
    t["emotional_temperature"] = (chapter.get("memo") or {}).get(
        "emotion_curve", "medium"
    )

    await get_storage().write_yaml(root_path, "threads.yaml", threads)
