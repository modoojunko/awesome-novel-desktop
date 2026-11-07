"""批量拆书 → 写作知识库（C 端 v2 知识库，离线 CLI）。

不走界面：直接建拆书任务行 → 调 `deconstruct.pipeline.run_task` 逐本拆解 →
完成后用 `kb.deconstruct_import.collect_task_to_kb` 收进 C 端账号级知识库
（kb_entries 知识 + kb_knowledge_instances 实例，与界面「收进知识库」同一函数）。

用法（backend 根目录）：
    python scripts/kb_batch_deconstruct.py --books ~/books \
        --db data/novel-v0.45.0.db --config-id opencode-go --model deepseek-v4.1-flash \
        --prompt-pack-dir ../awesome-novel-prompts

题材优先级：manifest 逐本 > `--genre` 整批 > 所在目录名 > 拆书产物 genre 维度。
断点续跑：`<books>/.kb-batch/journal.json` 记录文件指纹＋任务 id＋实例数；
重跑跳过已完成且文件未变的书，拆一半的复用原任务行（dims 断点续拆）。
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

BOOK_EXTS = {".txt", ".md"}
DEFAULT_DIMS = ("genre", "world", "characters", "style", "techniques")
JOURNAL_NAME = "journal.json"
JOURNAL_VERSION = 1
REQUIRED_TABLES = ("users", "api_configs", "app_meta", "deconstruct_jobs", "kb_entries")
# 可复用任务行的状态：拆到一半/失败可续跑；completed 只需补收录（不重拆）
RESUMABLE = frozenset(
    {"queued", "running", "failed", "stalled", "provider_unavailable", "cancelled", "completed"}
)


@dataclass
class Book:
    path: Path
    rel: str
    name: str
    genre: str = ""


@dataclass
class BookOutcome:
    book: Book
    status: str  # done / skipped / failed
    detail: str = ""
    task_id: str = ""
    chapters: int = 0
    chars: int = 0
    entries: int = 0
    skipped_entries: int = 0
    warnings: list[str] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    elapsed_s: float = 0.0


def parse_dims(raw: str) -> list[str]:
    from models.deconstruct import DIMENSION_KEYS

    text = str(raw or "").strip()
    if not text or text == "all":
        return list(DIMENSION_KEYS)
    want = {p.strip() for p in text.split(",") if p.strip()}
    picked = [k for k in DIMENSION_KEYS if k in want]
    if not picked:
        raise ValueError(f"拆解维度不认识：{text}（可选 {'/'.join(DIMENSION_KEYS)} 或 all）")
    return picked


def _dir_genre(rel: Path) -> str:
    from genres.theme_catalog import normalize_theme

    for part in reversed(rel.parent.parts):
        genre = normalize_theme(part)
        if genre:
            return genre
    return ""


def load_manifest(path: Path) -> dict[str, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("books") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ValueError('manifest 需要 {"books": [...]} 或列表形态')  # noqa: TRY004
    out: dict[str, dict] = {}
    for row in rows:
        if isinstance(row, str):
            row = {"path": row}
        if not isinstance(row, dict) or not str(row.get("path") or "").strip():
            raise ValueError("manifest 条目缺 path")
        out[str(row["path"]).strip().replace("\\", "/")] = {
            "name": str(row.get("name") or "").strip(),
            "genre": str(row.get("genre") or "").strip(),
        }
    return out


def scan_books(root, *, manifest=None, genre=""):
    from genres.theme_catalog import normalize_theme

    problems: list[str] = []
    global_genre = normalize_theme(genre) if genre else ""
    books: list[Book] = []
    if manifest is not None:
        root = root.resolve()
        for key, meta in manifest.items():
            path = Path(key)
            if not path.is_absolute():
                path = (root / key).resolve()
            if not path.is_file():
                problems.append(f"清单里的文件不存在：{key}")
                continue
            rel = str(path.relative_to(root)) if root in path.parents else path.name
            books.append(
                Book(
                    path=path,
                    rel=rel,
                    name=meta.get("name") or path.stem,
                    genre=normalize_theme(meta["genre"]) if meta.get("genre") else global_genre,
                )
            )
        books.sort(key=lambda b: b.rel)
        return books, problems
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in BOOK_EXTS:
            continue
        rel_path = path.relative_to(root)
        books.append(
            Book(path=path, rel=str(rel_path), name=path.stem,
                 genre=global_genre or _dir_genre(rel_path))
        )
    if not books:
        problems.append(f"{root} 下没有 .txt/.md 书稿")
    return books, problems


def load_journal(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": JOURNAL_VERSION, "books": {}}
    if not isinstance(data, dict) or not isinstance(data.get("books"), dict):
        return {"version": JOURNAL_VERSION, "books": {}}
    return data


def save_journal(path: Path, journal: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(journal, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def file_fingerprint(path: Path, raw: bytes) -> dict:
    return {
        "size": len(raw),
        "mtime_ns": path.stat().st_mtime_ns,
        "sha16": hashlib.sha256(raw).hexdigest()[:16],
    }


def is_done(record, fingerprint) -> bool:
    if not isinstance(record, dict) or record.get("status") != "done":
        return False
    return (record.get("fingerprint") or {}).get("sha16") == fingerprint.get("sha16")


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass
class Ctx:
    user_id: str
    api_config_id: str
    model: str
    dims: list[str]
    allow_risk: bool
    journal_path: Path

    def record(self, book: Book, **fields) -> None:
        journal = load_journal(self.journal_path)
        row = journal["books"].setdefault(str(book.path), {})
        row.update(fields)
        row["updated_at"] = _now()
        journal["version"] = JOURNAL_VERSION
        save_journal(self.journal_path, journal)


def bootstrap_env(args) -> None:
    if args.data_root:
        os.environ["DATA_ROOT"] = str(Path(args.data_root).expanduser().resolve())
    if args.db:
        os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{Path(args.db).expanduser().resolve()}"
    if args.prompt_pack_dir:
        os.environ["PROMPT_PACK_DEV_DIR"] = str(Path(args.prompt_pack_dir).expanduser().resolve())
    if args.concurrency:
        os.environ["DECONSTRUCT_CONCURRENCY"] = str(args.concurrency)


DEV_DB_NAME = "novel-dev.db"
REQUIRED_TABLES = ("users", "api_configs", "app_meta", "deconstruct_jobs", "kb_entries")


def check_db(*, strict: bool = False) -> Path:
    from config import DATABASE_URL

    db_path = Path(DATABASE_URL.split("///")[-1])
    if strict:
        if not db_path.exists():
            raise SystemExit(f"找不到数据库：{db_path}（--db 指向的文件不存在）")
        _require_tables(db_path)
        return db_path
    if db_path.exists() and db_path.name != DEV_DB_NAME:
        _require_tables(db_path)
        return db_path
    if db_path.exists():
        _require_tables(db_path)
        return db_path
    raise SystemExit(
        f"找不到数据库：{db_path}\n用 --data-root 指向应用数据目录，或 --db 直接指定库文件。"
    )


def _require_tables(db_path) -> None:
    from config import DATABASE_URL as _u  # noqa: F401

    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=3)
        try:
            tables = {
                r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        finally:
            con.close()
    except sqlite3.Error as e:
        raise SystemExit(f"打不开数据库 {db_path}：{e}") from e
    missing = [t for t in REQUIRED_TABLES if t not in tables]
    if missing:
        raise SystemExit(f"{db_path.name} 缺表 {', '.join(missing)}——这不是当前版本的应用库。")


def check_prompts() -> None:
    from prompts import PromptPackMissing, load_layers

    try:
        load_layers("deconstruct_card")
    except PromptPackMissing as e:
        raise SystemExit(
            "找不到拆书提示词模板。用 --prompt-pack-dir 指向 awesome-novel-prompts 检出，"
            f"或先在应用里完成提示词包同步。（{e}）"
        ) from e


async def resolve_user(explicit: str) -> str:
    from sqlalchemy import select

    from db import async_session
    from models.user import User

    username = explicit.strip()
    if not username:
        from auth_local.service import get_local_config

        username = str(get_local_config().get("username") or "").strip()
    if not username:
        raise SystemExit("拿不到登录用户名：用 --user 指定（应用里登录过的账号名）。")
    from sqlalchemy import text as _t

    from db import engine as _dbg_engine
    async with _dbg_engine.connect() as _c:
        for _r in (await _c.execute(_t("PRAGMA database_list"))).fetchall():
            print(f"[dbg] attached {_r[2]}", flush=True)
        _u = (await _c.execute(_t("SELECT id FROM users"))).fetchall()
        print(f"[dbg] users: {[r[0] for r in _u]}", flush=True)
    async with async_session() as session:
        exists = await session.scalar(select(User.id).where(User.id == username))
    if not exists:
        raise SystemExit(f"库里没有用户 {username}——先打开应用登录一次，或核对 --data-root。")
    return username


async def resolve_model(user_id: str, config_hint: str, model_hint: str) -> tuple[str, str]:
    from sqlalchemy import select

    from ai_state import config_key_usable, parse_models
    from api_configs.crypto import init_crypto
    from db import async_session
    from models.api_config import ApiConfig

    async with async_session() as session:
        await init_crypto(session)
        rows = (
            await session.execute(
                select(ApiConfig).where(
                    ApiConfig.user_id == user_id, ApiConfig.status != "deleted"
                )
            )
        ).scalars().all()

    usable = [
        c
        for c in rows
        if getattr(c, "vendor", "") != "zhuque"
        and config_key_usable(c)
        and parse_models(c.models)
    ]
    if not usable:
        raise SystemExit("该账号没有可用的模型配置（要有 Key 且至少一个模型）。")

    if config_hint:
        cands = [c for c in usable if c.id == config_hint or c.name == config_hint]
        if not cands:
            listing = "；".join(f"{c.name}（{c.vendor}）" for c in usable)
            raise SystemExit(f"找不到模型配置「{config_hint}」。可用：{listing}")
        if len(cands) > 1:
            raise SystemExit(f"模型配置名「{config_hint}」重名，请改用 id。")
        cfg = cands[0]
    elif len(usable) == 1:
        cfg = usable[0]
    else:
        listing = "\n".join(
            f"  - {c.name}（{c.vendor}）：{'、'.join(parse_models(c.models))}" for c in usable
        )
        raise SystemExit("有多个可用模型配置，请用 --config-id 指定：\n" + listing)

    models = parse_models(cfg.models)
    if model_hint:
        if model_hint not in models:
            raise SystemExit(f"模型「{model_hint}」不在配置「{cfg.name}」里：{'、'.join(models)}")
        model = model_hint
    else:
        model = models[0]
    return cfg.id, model


async def _ensure_task(book, raw, parse, encoding, ctx, prev) -> tuple[str, bool]:
    from db import async_session
    from deconstruct.service import create_task
    from models.deconstruct import DeconstructJob

    task_id = str((prev or {}).get("task_id") or "")
    if task_id:
        async with async_session() as session:
            task = await session.get(DeconstructJob, task_id)
            if task is not None and task.user_id == ctx.user_id and task.status in RESUMABLE:
                if task.source_path:
                    source = Path(task.source_path)
                    source.parent.mkdir(parents=True, exist_ok=True)
                    source.write_bytes(raw)
                if task.status != "completed":
                    task.status = "running"
                    task.started_at = datetime.now(UTC).replace(tzinfo=None)
                    task.error_json = "{}"
                # 换模型续拆：run_task 读的是任务行里的配置，续跑跟随本次参数
                if ctx.api_config_id and task.api_config_id != ctx.api_config_id:
                    task.api_config_id = ctx.api_config_id
                if ctx.model and task.ai_model != ctx.model:
                    task.ai_model = ctx.model
                await session.commit()
                return task_id, True

    async with async_session() as session:
        task = await create_task(
            session,
            ctx.user_id,
            book_name=book.name,
            source_name=book.path.name,
            source_size=len(raw),
            encoding=encoding,
            parse=parse,
            api_config_id=ctx.api_config_id,
            ai_model=ctx.model,
            selected_dims=ctx.dims,
            status="running",
        )
        task_id = task.id
        source = Path(task.source_path)
    source.parent.mkdir(parents=True, exist_ok=True)
    tmp = source.with_suffix(".tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, source)
    return task_id, False


async def _load_task(task_id: str):
    from db import async_session
    from models.deconstruct import DeconstructJob

    async with async_session() as session:
        return await session.get(DeconstructJob, task_id)


def _task_error(task) -> str:
    try:
        err = json.loads(task.error_json or "{}")
    except ValueError:
        return ""
    return str(err.get("message") or err.get("error") or "") if isinstance(err, dict) else ""


async def _usage(task_id: str) -> tuple[int, int]:
    from deconstruct.service import task_stats

    try:
        stats = await task_stats(task_id)
    except Exception:  # noqa: BLE001
        return 0, 0
    return (
        sum(int(v.get("tokens_in") or 0) for v in stats.values()),
        sum(int(v.get("tokens_out") or 0) for v in stats.values()),
    )


async def process_book(book, ctx, *, force: bool) -> BookOutcome:
    outcome = BookOutcome(book=book, status="failed")
    started = time.monotonic()
    try:
        return await _process_book_inner(book, ctx, force=force, outcome=outcome)
    finally:
        outcome.elapsed_s = time.monotonic() - started


async def _process_book_inner(book, ctx, *, force, outcome) -> BookOutcome:
    from deconstruct.textparse import decode_text, parse_novel, structure_verdict

    raw = book.path.read_bytes()
    fingerprint = file_fingerprint(book.path, raw)
    journal = load_journal(ctx.journal_path)
    prev = None if force else journal["books"].get(str(book.path))

    if is_done(prev, fingerprint):
        outcome.status = "skipped"
        outcome.task_id = str(prev.get("task_id") or "")
        outcome.entries = int(prev.get("entries") or 0)
        outcome.detail = "已完成（文件未变）"
        return outcome

    if prev and (prev.get("fingerprint") or {}).get("sha16") not in (None, fingerprint["sha16"]):
        prev = None

    text, encoding = decode_text(raw)
    parse = parse_novel(text)
    verdict = structure_verdict(parse)
    outcome.chapters = len(parse["chapters"])
    outcome.chars = int(parse.get("total_chars") or 0)

    if verdict["level"] == "risk" and not ctx.allow_risk:
        outcome.status = "skipped"
        outcome.detail = "结构判定 risk（未识别章标题且超 3 万字）——--allow-risk 可强拆"
        ctx.record(book, status="skipped", fingerprint=fingerprint, detail=outcome.detail)
        return outcome

    ctx.record(book, status="running", fingerprint=fingerprint, name=book.name, genre=book.genre)
    task_id, _reused = await _ensure_task(book, raw, parse, encoding, ctx, prev)
    outcome.task_id = task_id
    ctx.record(book, status="running", task_id=task_id, fingerprint=fingerprint,
               name=book.name, genre=book.genre)

    task = await _load_task(task_id)
    if task is None:
        outcome.detail = "任务行丢失"
        ctx.record(book, status="failed", task_id=task_id, error=outcome.detail)
        return outcome
    if task.status != "completed":
        from deconstruct.pipeline import run_task

        await run_task(task_id)
        task = await _load_task(task_id)
        if task is None:
            outcome.detail = "任务行丢失"
            ctx.record(book, status="failed", task_id=task_id, error=outcome.detail)
            return outcome

    outcome.tokens_in, outcome.tokens_out = await _usage(task_id)
    if task.status != "completed":
        outcome.detail = f"拆解未完成（{task.status}）{_task_error(task)}".strip()
        ctx.record(book, status="failed", task_id=task_id, error=outcome.detail,
                   fingerprint=fingerprint)
        return outcome

    from db import async_session
    from kb.deconstruct_import import collect_task_to_kb

    async with async_session() as session:
        fresh = await session.get(type(task), task_id)
        result = await collect_task_to_kb(session, task.user_id, fresh)

    outcome.status = "done"
    outcome.entries = result["collected"]
    outcome.skipped_entries = result["skipped"]
    outcome.warnings = list(result.get("warnings") or [])
    outcome.detail = f"收录 {outcome.entries} 条，跳过 {result['skipped']} 条重复"
    if result.get("genre") and not book.genre:
        book.genre = result["genre"]
    ctx.record(
        book, status="done", task_id=task_id, fingerprint=fingerprint,
        name=book.name, genre=book.genre, entries=outcome.entries,
        error="", tokens_in=outcome.tokens_in, tokens_out=outcome.tokens_out,
    )
    return outcome


async def run_async(args, user_id, config_id, model, dims) -> int:
    books_root = Path(args.books).expanduser().resolve()
    if not books_root.is_dir():
        print(f"[fail] --books 不是目录：{books_root}", flush=True)
        return 2
    manifest = load_manifest(Path(args.manifest).expanduser()) if args.manifest else None
    books, problems = scan_books(books_root, manifest=manifest, genre=args.genre)
    for problem in problems:
        print(f"[warn] {problem}", flush=True)
    if args.limit:
        books = books[: args.limit]
    if not books:
        print("没有可处理的书籍。", flush=True)
        return 1

    if args.dry_run:
        from deconstruct.textparse import decode_text, parse_novel, structure_verdict

        print(f"计划处理 {len(books)} 本（dry-run，不写库、不调模型）：", flush=True)
        for book in books:
            raw = book.path.read_bytes()
            text, _enc = decode_text(raw)
            parse = parse_novel(text)
            verdict = structure_verdict(parse)
            print(
                f"  - {book.rel}｜{book.genre or '题材待判定'}"
                f"｜{len(parse['chapters'])} 章 / {parse['total_chars']} 字"
                f"｜结构 {verdict['level']}",
                flush=True,
            )
        return 0


    work_dir = Path(args.work_dir).expanduser() if args.work_dir else books_root / ".kb-batch"
    ctx = Ctx(
        user_id=user_id, api_config_id=config_id, model=model, dims=dims,
        allow_risk=bool(args.allow_risk), journal_path=work_dir / JOURNAL_NAME,
    )
    print(
        f"用户：{user_id}｜模型：{model}｜维度：{','.join(dims)}"
        f"｜并发：{os.environ.get('DECONSTRUCT_CONCURRENCY') or '4'}\n"
        f"待处理：{len(books)} 本｜记录：{ctx.journal_path}",
        flush=True,
    )

    outcomes: list = []
    done_genres: set = set()
    try:
        for index, book in enumerate(books, 1):
            print(f"\n[{index}/{len(books)}] {book.rel}", flush=True)
            try:
                outcome = await process_book(book, ctx, force=bool(args.force))
            except KeyboardInterrupt:
                raise
            except Exception as e:  # noqa: BLE001
                outcome = BookOutcome(book=book, status="failed", detail=f"{type(e).__name__}: {e}")
                ctx.record(book, status="failed", error=outcome.detail)
            outcomes.append(outcome)
            _print_outcome(outcome)
            if outcome.status == "done":
                done_genres.add(book.genre)
    except KeyboardInterrupt:
        print("\n已中断：进度已存入记录，重跑同一命令即可续拆。", flush=True)
        return 130

    ok = sum(1 for o in outcomes if o.status == "done")
    skipped = sum(1 for o in outcomes if o.status == "skipped")
    failed = sum(1 for o in outcomes if o.status == "failed")
    entries = sum(o.entries for o in outcomes)
    tokens_in = sum(o.tokens_in for o in outcomes)
    tokens_out = sum(o.tokens_out for o in outcomes)
    print(
        f"\n完成：{ok} 本入库（{entries} 条）｜跳过 {skipped}｜失败 {failed}"
        f"｜tokens {tokens_in}/{tokens_out}",
        flush=True,
    )
    if args.organize and done_genres:
        from db import async_session
        from kb.organize import run_organize

        for genre in sorted(done_genres):
            async with async_session() as session:
                _run, error = await run_organize(
                    session, user_id=user_id, genre=genre, trigger="batch-deconstruct"
                )
            print(f"[org ] 整理题材「{genre or '未定题材'}」— {error or '完成'}", flush=True)
    return 0 if failed == 0 else 2


def _print_outcome(outcome) -> None:
    icon = {"done": "ok", "skipped": "skip", "failed": "fail"}[outcome.status]
    head = f"[{icon:4}] {outcome.book.rel}"
    if outcome.book.genre:
        head += f" · {outcome.book.genre}"
    if outcome.chapters:
        head += f" · {outcome.chapters} 章 / {outcome.chars} 字"
    print(f"{head} — {outcome.detail}", flush=True)
    for warning in outcome.warnings[:5]:
        print(f"        ! {warning}", flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="批量拆书并写入 C 端 v2 写作知识库（离线，不走界面）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--books", required=True, help="书稿目录（递归扫 .txt/.md）")
    parser.add_argument("--manifest", help="清单 JSON（{books:[{path,name,genre}]}）")
    parser.add_argument("--genre", default="", help="整批题材")
    parser.add_argument("--data-root", help="应用数据目录（含 config.json / 库文件）")
    parser.add_argument("--db", help="直接指定库文件（优先于 --data-root）")
    parser.add_argument("--user", default="", help="账号名（默认取 config.json 的登录名）")
    parser.add_argument("--config-id", default="", help="模型配置 id 或名称")
    parser.add_argument("--model", default="", help="模型名（默认取配置里第一个）")
    parser.add_argument("--dims", default="", help="拆解维度：all 或逗号清单（默认五项）")
    parser.add_argument("--prompt-pack-dir", help="提示词仓检出目录（PROMPT_PACK_DEV_DIR）")
    parser.add_argument("--work-dir", help="记录目录（默认 <books>/.kb-batch）")
    parser.add_argument("--concurrency", type=int, default=0, help="拆书并发（默认 4）")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 本")
    parser.add_argument("--allow-risk", action="store_true", help="结构判定 risk 的书也拆")
    parser.add_argument("--organize", action="store_true", help="跑完后按题材整理一次")
    parser.add_argument("--force", action="store_true", help="无视记录全部重拆")
    parser.add_argument("--dry-run", action="store_true", help="只解析书目，不写库不调模型")
    return parser


def _dry_run(args, books_root: Path) -> int:
    from deconstruct.textparse import decode_text, parse_novel, structure_verdict

    manifest = load_manifest(Path(args.manifest).expanduser()) if args.manifest else None
    books, problems = scan_books(books_root, manifest=manifest, genre=args.genre)
    for problem in problems:
        print(f"[warn] {problem}", flush=True)
    if args.limit:
        books = books[: args.limit]
    print(f"计划处理 {len(books)} 本（dry-run，不写库、不调模型）：", flush=True)
    for book in books:
        raw = book.path.read_bytes()
        text, encoding = decode_text(raw)
        parse = parse_novel(text)
        verdict = structure_verdict(parse)
        print(
            f"  - {book.rel}｜{book.genre or '题材待判定'}"
            f"｜{len(parse['chapters'])} 章 / {parse['total_chars']} 字"
            f"｜{encoding}｜结构 {verdict['level']}",
            flush=True,
        )
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    bootstrap_env(args)
    try:
        if args.dry_run:
            if not args.books:
                print("[fail] --dry-run 需要 --books", flush=True)
                return 2
            return _dry_run(args, Path(args.books).expanduser().resolve())
        check_db(strict=bool(args.db))

        if not args.dims:
            args.dims = ",".join(DEFAULT_DIMS)
        dims = parse_dims(args.dims)
        user_id = asyncio.run(resolve_user(args.user))
        config_id, model = asyncio.run(resolve_model(user_id, args.config_id, args.model))
        return asyncio.run(run_async(args, user_id, config_id, model, dims))
    except SystemExit as e:
        print(f"[fail] {e}", flush=True)
        return 2
    except (ValueError, OSError) as e:
        print(f"[fail] {e}", flush=True)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
