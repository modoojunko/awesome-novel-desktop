"""成稿下载任务（c-manuscript-download PR3）。

走 job_runner 单飞（kind=download，与备份全局互斥）；本机后端直写用户所选目录，
不走浏览器下载。写盘策略 = `*.part` 先写后 rename（净新增失败清理：任一格式
失败时删未完成 part，已完成文件保留并逐格式行标「失败」）。
"""

import asyncio
import contextlib
import re
from pathlib import Path

from job_runner import JobError, classify_os_error, run_thread, set_job
from job_runner import start as job_start
from manuscript.content import Manuscript, build_manuscript
from manuscript.render import render_docx, render_md, render_txt

# 格式白名单（单一事实源；顺序即产物顺序）
FORMATS: dict[str, dict] = {
    "md": {"ext": ".md", "render": lambda m: render_md(m)},
    "txt": {"ext": ".txt", "render": lambda m: render_txt(m)},
    "docx": {"ext": ".docx", "render": lambda m: render_docx(m)},
}

PROBE_NAME = ".ainovel-write-probe"

# 产物扩展名（手输文件名自带时先剥掉，防 我的小说.md.md）；+ 允许重复后缀一次剥净
_ARTIFACT_EXT_RE = re.compile(r"(?:\.(?:md|txt|docx))+$", re.IGNORECASE)


def strip_artifact_ext(name: str) -> str:
    """剥掉手输文件名自带的产物扩展名——不加这步，用户输入「我的小说.md」会得到
    我的小说.md.md（md）/ 我的小说.md.docx（docx）（P3，2026-09-18）。

    「+」形式支持重复后缀一次剥净（我的小说.docx.md → 我的小说）；只认这三种
    扩展名，`.v2` / `.mdx` 之类原样保留。
    """
    return _ARTIFACT_EXT_RE.sub("", (name or "").strip())


def sanitize_filename(name: str) -> str:
    """复用备份先例（strip 非法字符与 \\r\\n、rstrip 点空格、60 字上限）。"""
    from backup.export import sanitize_book_filename

    return sanitize_book_filename(name)


def normalized_filename(raw: str, book_name: str) -> str:
    """用户手输名 → 落盘用的干净基底名（单一事实源：写盘与弹层展示同源）。

    顺序是「先 sanitize 再剥扩展名再 sanitize」：先清掉尾部 `*`/空格这类字符，
    避免 `我的小说.md*` 剥不掉扩展名（清完才露出来）；剥完可能只剩点号（`..md`），
    再过一次 sanitize 收敛成「未命名」。空输入回落默认名。
    """
    if not (raw or "").strip():
        return default_filename(book_name)
    base = strip_artifact_ext(sanitize_filename(raw))
    return sanitize_filename(base) if base.strip() else default_filename(book_name)


def default_filename(book_name: str) -> str:
    return f"{sanitize_filename(book_name)} · 主线全稿"


def start_download_job(
    target_dir: str, filename: str, formats: list[str], book_id: str, user_id: str
) -> dict | None:
    """单飞入口：已有任务在跑返回 None（路由层转 409）。"""
    steps = [
        {"format": fmt, "state": "等待", "error": None}
        for fmt in formats
        if fmt in FORMATS
    ]
    return job_start(
        "download",
        _run_thread,
        user_id,
        target_dir=target_dir,
        filename=filename,
        formats=[fmt for fmt in formats if fmt in FORMATS],
        book_id=book_id,
        steps=steps,
        files=[],
        current="",
        pct=0,
    )


def _set_step(steps: list[dict], fmt: str, state: str, error: str | None = None) -> list[dict]:
    """steps 是嵌套可变结构——按 job_runner 纪律整值替换（重建列表后一次性 set），
    并把新列表交还调用方（本地引用同步前进，防基于陈旧值重建）。"""
    next_steps = [
        {**s, "state": state, "error": error} if s["format"] == fmt else s for s in steps
    ]
    set_job(steps=next_steps)
    return next_steps


def _run_thread(payload: dict, user_id: str) -> None:
    def _body() -> None:
        asyncio.run(_download_async(payload, user_id))

    run_thread(_body)


def _write_part(target: Path, data: bytes | str) -> None:
    part = Path(str(target) + ".part")
    if isinstance(data, str):
        part.write_text(data, encoding="utf-8")
    else:
        part.write_bytes(data)
    part.replace(target)


async def _download_async(payload: dict, user_id: str) -> None:
    from db import async_session
    from models.project import Novel
    from models.user import User

    # 手输路径容错：~/ 与相对路径按本机语义展开（前端首次开放手输，旧备份只有 pick_folder）
    target_dir = Path(str(payload["target_dir"])).expanduser()
    formats: list[str] = payload["formats"]
    steps: list[dict] = list(payload["steps"])

    # ① 目录探针：可写性先行（与备份同款 probe 口径：固定名 + 立即清理；固定名让
    #    历史硬杀残渣在下次运行时被覆盖后删除＝自愈）
    set_job(phase="probe")
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        probe = target_dir / PROBE_NAME
        try:
            probe.write_text("ok")
        finally:
            # 清理不可抛：finally 里新抛的 OSError 会顶替在途异常、把归因换码
            with contextlib.suppress(OSError):
                probe.unlink(missing_ok=True)
    except OSError as e:
        # 归因与渲染阶段同源（classify_os_error）：disk_full/permission_denied/invalid_path/io_error
        raise JobError(classify_os_error(e), f"无法写入所选目录：{target_dir}") from e

    # ② 内容装配（线程内自开 session；user_id 为线程内鉴权凭据）
    set_job(phase="assemble", current="正在装配主线全稿")
    async with async_session() as db:
        user = await db.get(User, user_id)
        if user is None:
            raise JobError("user_not_found", "用户不存在")
        project = await db.get(Novel, payload["book_id"])
        if project is None or project.status == "deleted" or project.user_id != user_id:
            raise JobError("not_found", "作品不存在")
        ms: Manuscript = await build_manuscript(db, project)
        book_name = project.name  # 会话关闭前取值（防 detached 访问）

    safe_name = normalized_filename(payload["filename"], book_name)
    set_job(
        chapter_count=ms.chapter_count,
        word_count=ms.word_count,
        book_name=book_name,
        # 归一化后的基底名下发给前端：弹层进度/完成清单按它拼行名，否则用户输入
        # 「我的稿子.md」时界面显示 我的稿子.md.md 而盘上是 我的稿子.md（评审 P1）
        filename=safe_name,
    )

    # ③ 逐格式渲染写盘：part → rename；失败清理 part、行标「失败」，已完成文件保留
    set_job(phase="render")
    files: list[str] = []
    total = len(formats)
    for idx, fmt in enumerate(formats):
        spec = FORMATS[fmt]
        target = target_dir / f"{safe_name}{spec['ext']}"
        steps = _set_step(steps, fmt, "下载中")
        set_job(current=f"正在下载 {target.name}", pct=round(idx / total * 100))
        try:
            data = spec["render"](ms)
            _write_part(target, data)
        except JobError:
            steps = _set_step(steps, fmt, "失败", "Word 渲染组件不可用")
            Path(str(target) + ".part").unlink(missing_ok=True)
            raise
        except OSError as e:
            steps = _set_step(steps, fmt, "失败", str(e))
            Path(str(target) + ".part").unlink(missing_ok=True)
            raise
        except Exception as e:  # 渲染器未知异常：行标失败 + 落任务错误（不静默）
            steps = _set_step(steps, fmt, "失败", str(e))
            Path(str(target) + ".part").unlink(missing_ok=True)
            raise
        steps = _set_step(steps, fmt, "完成")
        files.append(target.name)
        set_job(files=list(files), pct=round((idx + 1) / total * 100))
    set_job(current="", pct=100)
