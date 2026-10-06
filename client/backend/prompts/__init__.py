"""Prompt loader — reads .prompt files from this directory.

**分层协议（用户 2026-09-27 定，逐模板独立、不做跨模板共享层）**：
每个 `.prompt` 文件用两行标记切成两段——
    `<<system>>` 角色＋永久约束＋优先级＋禁止项＋输出契约（同一功能每次调用**恒定不变**）
    `<<user>>`   每次调用动态替换的内容（设定素材/前文/本次任务/临时要求）
调用方用 `load_layers(name)` 取两段，分别送 `system=` 与 `messages[0].content`。
为什么恒定段必须单独成 system：① 供应商 prompt 缓存只认恒定前缀（省钱提速）；
② 永久约束不被几千字素材稀释；③ 每个功能可以独立调自己的 system，不被别的功能牵动。
过渡期：未分层的文件 `load_layers` 返回 `("", 全文)`（向后兼容），进度由回归测试
（`test_prompt_layering`）用名单跟踪，逐族清零。

**解析序（c-prompt-pack-client，2026-10-05）**：
    ① 已装提示词包目录（`prompt_pack.resolve_dir()`——receipt 版本目录，含
       min_client_version 拒载回落；发布态的唯一来源）
    ② 包内目录（本文件所在目录——开发/测试态直读仓库单源；env
       `PROMPT_PACK_MODE=force` 时禁用本跳，e2e 强制包模式用）
    ③ 都没有 → `PromptPackMissing`（AI 端点统一转 503＋专用 reason 引导获取；
       手写正文等非模板功能不受影响）

读已装包时按 receipt 的模板 sha256 做轻量校验（(mtime_ns,size) 签名失效才重算）；
校验不过视为该文件缺失 → 走同一缺包路径（回滚自愈在同步器侧）。
"""

import os
import re

_PROMPTS_DIR = os.path.dirname(os.path.abspath(__file__))

# Only allow safe prompt names — alphanumeric, underscores, hyphens
_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")

SYSTEM_MARK = "<<system>>"
USER_MARK = "<<user>>"

# 强制包模式：e2e/联调跳过「包内目录」一跳，验证真实分发链
FORCE_PACK_ENV = "PROMPT_PACK_MODE"


class PromptPackMissing(FileNotFoundError):
    """写作能力（提示词包）未就绪——未登录/未装包/装包损坏且无回滚位。

    继承 FileNotFoundError：历史调用方 except FileNotFoundError 的降级路径不改；
    带引导语义供上层转 503＋reason（AI 端点）。
    """


def _candidates(name: str) -> list[tuple[str, str | None]]:
    """解析序候选 → [(绝对路径, 期望 sha256|None)]，按优先级排列。"""
    out: list[tuple[str, str | None]] = []
    try:
        from prompt_pack import read_receipt, resolve_dir

        version_dir = resolve_dir()
        if version_dir:
            receipt = read_receipt() or {}
            templates = receipt.get("templates")
            expect = templates.get(name) if isinstance(templates, dict) else None
            out.append((os.path.join(version_dir, f"{name}.prompt"), expect))
    except Exception:
        # 包元数据读取失败不阻断开发态回落（自愈在同步器侧；读路径只做降级）
        pass
    if os.environ.get(FORCE_PACK_ENV) != "force":
        out.append((os.path.join(_PROMPTS_DIR, f"{name}.prompt"), None))
    return out


def _read_verified(path: str, expect: str | None) -> str | None:
    """读文件；有期望哈希时做读时校验，不过返回 None（视为缺失）。"""
    if not os.path.isfile(path):
        return None
    if expect:
        from prompt_pack import verify_file

        if not verify_file(path, expect):
            return None
    with open(path, encoding="utf-8") as f:
        return f.read()


def load(name: str) -> str:
    """Load a prompt template by name (without .prompt extension).

    Raises ValueError if *name* contains unsafe characters (path traversal).
    Raises PromptPackMissing when neither the installed pack nor the bundled
    dev copy provides the template.
    """
    if not _SAFE_NAME_RE.match(name):
        raise ValueError(f"Invalid prompt name: {name!r}")
    # 纵深防御：候选路径的文件名必须恰为 {name}.prompt（realpath 归位；
    # 白名单已保证 name 不含 / 与 ..，此处对静态分析亦可证安全）
    for path, expect in _candidates(name):
        real = os.path.realpath(path)
        if os.path.basename(real) != f"{name}.prompt":
            continue
        text = _read_verified(path, expect)
        if text is not None:
            return text
    raise PromptPackMissing(f"Prompt pack missing template: {name}")


def _strip_comment_lines(text: str) -> str:
    """剥掉文件头的 `## ` 版本注释行（changelog 用，不入提示词）。"""
    lines = text.splitlines()
    i = 0
    while i < len(lines) and (not lines[i].strip() or lines[i].lstrip().startswith("##")):
        i += 1
    return "\n".join(lines[i:]).strip()


def is_layered(name: str) -> bool:
    """该模板是否已按分层协议拆好（两个标记都在）。"""
    raw = load(name)
    return SYSTEM_MARK in raw and USER_MARK in raw


def load_layers(name: str) -> tuple[str, str]:
    """分层加载 → (system, user)。

    未分层的文件返回 `("", 全文)`：迁移期向后兼容（调用方行为不变）。
    已分层的文件剥掉 `## ` 注释行后按标记切段；system 段里剩下的标记行一并去掉。
    """
    raw = load(name)
    if USER_MARK not in raw:
        return "", _strip_comment_lines(raw)
    head, _, tail = raw.partition(USER_MARK)
    system = _strip_comment_lines(head.replace(SYSTEM_MARK, ""))
    return system, _strip_comment_lines(tail)
