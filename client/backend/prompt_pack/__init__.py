"""提示词包本地存储与解析序（c-prompt-pack-client）。

目录布局（跨版本共享——c-db-per-version 判例：库文件每版独立，包不能跟着轮换）：

    {DATA_ROOT}/prompt-pack/
        receipt.json       单源回执：version/tier/key_id/min_client_version/
                           installed_at/templates:{模板名:sha256}（tmp＋os.replace 原子写）
        highwatermark      防旧版重放高水位（与 receipt 分开存——clear-data/重建
                           receipt 不连带洗掉防重放记忆）
        key.bin            本地包密钥的封装体（Windows DPAPI blob；macOS 在 Keychain）
                           ——绑机器+用户：整目录拷到别处解不开（见 localkey.py）
        v{N}/              当前版本容器（不可变；含已验签 manifest 副本）
                           pack.bin＝nonce||AES-GCM 密文（模板表，钥匙绑机器+用户）
                           manifest.json＝非机密元数据（版本/哈希/签名）
        v{N-1}/            回滚位（读时校验失败一次即回落）
        .staging-v{N}/     安装中转（同步器专用；成功 rename 成 v{N}，失败整删）

loader 解析序（`prompts.load` 唯一消费口，本模块不读模板内容）：
    ① receipt 指向版本目录——前置闸：receipt.min_client_version 高于本机版本即拒载，
       回落其余 v{N-x} 目录（逐个过闸，防「旧 App＋新包」占位符契约断裂）
    ② 开发/测试态包内目录（env `PROMPT_PACK_MODE=force` 时禁用——e2e 强制包模式）
    ③ 都没有 → None（调用方抛 PromptPackMissing 引导）

版本比较一律走 schema_version（is_newer/version_sort_key），不新造比较器。
"""

from __future__ import annotations

import hashlib
import json
import os

from schema_version import DEV_VERSION, app_version, is_newer

PACK_DIR_NAME = "prompt-pack"
RECEIPT_NAME = "receipt.json"
HIGHWATERMARK_NAME = "highwatermark"
STAGING_PREFIX = ".staging-"


def pack_root() -> str:
    """{DATA_ROOT}/prompt-pack（运行时取 env——测试 monkeypatch 生效）。"""
    return os.path.join(os.environ.get("DATA_ROOT", "./data"), PACK_DIR_NAME)


# ── receipt ──────────────────────────────────────────────────────────────────


def read_receipt() -> dict | None:
    """读回执；缺失/损坏返回 None（损坏自愈由同步器负责重拉，读侧只降级）。"""
    path = os.path.join(pack_root(), RECEIPT_NAME)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("version") else None


def write_receipt(receipt: dict) -> None:
    """原子写回执（tmp＋os.replace，save_local_config 同款范式）。"""
    root = pack_root()
    os.makedirs(root, exist_ok=True)
    tmp = os.path.join(root, RECEIPT_NAME + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(receipt, f, ensure_ascii=False, indent=1)
    os.replace(tmp, os.path.join(root, RECEIPT_NAME))


def clear_receipt() -> None:
    """清回执回「未装」态（损坏自愈链末段；不动 highwatermark）。"""
    try:
        os.remove(os.path.join(pack_root(), RECEIPT_NAME))
    except FileNotFoundError:
        pass


# ── 高水位（防旧版重放） ─────────────────────────────────────────────────────


def read_highwatermark() -> str:
    path = os.path.join(pack_root(), HIGHWATERMARK_NAME)
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def write_highwatermark(version: str) -> None:
    root = pack_root()
    os.makedirs(root, exist_ok=True)
    tmp = os.path.join(root, HIGHWATERMARK_NAME + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(version)
    os.replace(tmp, os.path.join(root, HIGHWATERMARK_NAME))


# ── 版本目录与解析序 ─────────────────────────────────────────────────────────


def _version_dirs() -> list[str]:
    """pack 根下 v{N} 目录，新→旧排序（version_sort_key 复用；非法名忽略）。"""
    from schema_version import version_sort_key

    root = pack_root()
    try:
        names = [n for n in os.listdir(root) if n.startswith("v") and n[1:].strip()]
    except OSError:
        return []
    dirs = [os.path.join(root, n) for n in names]
    try:
        dirs.sort(key=lambda p: version_sort_key(os.path.basename(p)[1:]), reverse=True)
    except Exception:
        # 比较器对非法形态的兜底：按名字倒序（version_sort_key 自身不抛，双保险）
        dirs.sort(reverse=True)
    return [d for d in dirs if os.path.isdir(d)]


def _gate_ok(min_client_version: str | None, current: str | None) -> bool:
    """min_client_version 闸：要求版本高于本机 → 拒载。dev 构建恒过（dev 有包内兜底）。"""
    if not min_client_version:
        return True
    if current is None:
        current = app_version()
    if current == DEV_VERSION:
        return True
    return not is_newer(min_client_version, current)


def resolve_dir() -> str | None:
    """解析序①：回执目录→（不满足闸则）其余版本目录新→旧逐个过闸。无 → None。"""
    receipt = read_receipt()
    dirs = _version_dirs()
    if receipt:
        wanted = os.path.join(pack_root(), f"v{receipt['version']}")
        if os.path.isdir(wanted) and _gate_ok(receipt.get("min_client_version"), None):
            return wanted
    for d in dirs:
        if receipt and d == os.path.join(pack_root(), f"v{receipt['version']}"):
            continue  # 已被闸拒的目录不重试
        if _gate_ok(_dir_min_client_version(d), None):
            return d
    return None


def _dir_min_client_version(version_dir: str) -> str | None:
    """从版本目录内的 manifest 副本读 min_client_version（无则视为兼容）。"""
    try:
        with open(os.path.join(version_dir, "manifest.json"), encoding="utf-8") as f:
            data = json.load(f)
        v = data.get("min_client_version")
        return v if isinstance(v, str) and v else None
    except (OSError, ValueError):
        return None


# ── 读路径（内存解密；c-prompt-pack-hardening D3） ───────────────────────────


def read_all_templates() -> dict[str, str] | None:
    """解出已装版本的模板表（**内存中**，不落任何中间文件）。

    不可用（未装/闸拒/钥匙不可用/容器损坏）一律返回 None——调用方按「该版本不可用」
    回落或按未装处理；本函数不抛（读路径只降级，自愈在同步器侧）。
    顺带做旧版明文包的就地加密迁移（D5，幂等）。
    """
    from prompt_pack import container  # noqa: PLC0415 — 子模块按需导入

    try:
        version_dir = resolve_dir()
    except Exception:  # noqa: BLE001 — 包元数据读取失败不阻断回落
        return None
    if not version_dir:
        return None
    try:
        migrate_plaintext(version_dir)
        with open(os.path.join(version_dir, container.CONTAINER_NAME), "rb") as f:
            blob = f.read()
    except OSError:
        return None
    try:
        return container.open_container(blob, os.path.basename(version_dir)[1:])
    except container.ContainerInvalid:
        return None


def read_template(name: str) -> str | None:
    """取单个模板（已装包路径，内存解密＋读时哈希校验）；不可用返回 None。"""
    templates = read_all_templates()
    if templates is None:
        return None
    text = templates.get(name)
    if not isinstance(text, str):
        return None
    receipt = read_receipt() or {}
    table = receipt.get("templates")
    expect = table.get(name) if isinstance(table, dict) else None
    if isinstance(expect, str) and expect and verify_text(text, expect) is False:
        return None
    return text


def migrate_plaintext(version_dir: str) -> bool:
    """旧版明文包（v{N}/*.prompt）就地加密转换（D5，幂等）。

    返回 True＝转换完成或无需转换。**失败即按未装处理**：删掉明文与残件（同步器随后
    重下），任何路径都不得保留明文可用态（spec：存量迁移条款）。
    """
    from prompt_pack import container  # noqa: PLC0415

    try:
        names = [n for n in os.listdir(version_dir) if n.endswith(".prompt")]
    except OSError:
        return False
    if not names:
        return True
    version = os.path.basename(version_dir)[1:]
    try:
        templates: dict[str, str] = {}
        for n in names:
            with open(os.path.join(version_dir, n), encoding="utf-8") as f:
                templates[n[: -len(".prompt")]] = f.read()
        blob = container.seal(templates, version)
        tmp = os.path.join(version_dir, container.CONTAINER_NAME + ".tmp")
        with open(tmp, "wb") as f:
            f.write(blob)
        os.replace(tmp, os.path.join(version_dir, container.CONTAINER_NAME))
    except Exception as e:  # noqa: BLE001 — 含钥匙不可用：一律转「按未装」
        logger = __import__("logging").getLogger(__name__)
        logger.warning("event=pack_migrate_failed version=%s err=%s", version, type(e).__name__)
        for n in names:
            try:
                os.remove(os.path.join(version_dir, n))
            except OSError:
                pass
        return False
    for n in names:
        try:
            os.remove(os.path.join(version_dir, n))
        except OSError:
            pass
    return True


# ── 读时校验（防手改） ───────────────────────────────────────────────────────

def verify_text(text: str, expect_sha256: str) -> bool:
    """读时校验（容器内条目）：按模板**文本**哈希比对（receipt 语义不变）。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest() == expect_sha256


_sig_cache: dict[str, tuple[int, int, str]] = {}


def verify_file(path: str, expect_sha256: str) -> bool:
    """**文件形态**的读时校验（(mtime_ns,size) 命中缓存即过；变更才重算 sha256）。

    容器化后已装包的读时校验走 `verify_text`（对解密出的模板文本比对），本函数只服务
    历史/文件形态（开发态目录、测试）；不要用它去校验 `pack.bin`（那是密文，哈希对不上）。
    """
    try:
        st = os.stat(path)
    except OSError:
        return False
    sig = (st.st_mtime_ns, st.st_size)
    cached = _sig_cache.get(path)
    if cached and cached[0] == sig[0] and cached[1] == sig[1]:
        return cached[2] == expect_sha256
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    digest = h.hexdigest()
    _sig_cache[path] = (sig[0], sig[1], digest)
    return digest == expect_sha256
