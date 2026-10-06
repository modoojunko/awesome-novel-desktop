"""Prompt loader — 模板文本加载（发布态读已装包，开发/测试态读模板目录）。

**分层协议（用户 2026-09-27 定，逐模板独立、不做跨模板共享层）**：
每个 `.prompt` 文件用两行标记切成两段——
    `<<system>>` 角色＋永久约束＋优先级＋禁止项＋输出契约（同一功能每次调用**恒定不变**）
    `<<user>>`   每次调用动态替换的内容（设定素材/前文/本次任务/临时要求）
调用方用 `load_layers(name)` 取两段，分别送 `system=` 与 `messages[0].content`。
为什么恒定段必须单独成 system：① 供应商 prompt 缓存只认恒定前缀（省钱提速）；
② 永久约束不被几千字素材稀释；③ 每个功能可以独立调自己的 system，不被别的功能牵动。

**解析序（c-prompt-pack-client，2026-10-05；c-prompt-source-flip，2026-10-06）**：
    ① 已装提示词包目录（`prompt_pack.resolve_dir()`——receipt 版本目录，含
       min_client_version 拒载回落；发布态的唯一来源）
    ② 开发/测试态模板目录（c-prompt-source-flip 起＝`PROMPT_PACK_DEV_DIR` 指定的
       sibling 提示词仓检出，文件可带纳管注释；未设回退「包内目录」兼容历史夹具；
       frozen 发布包内无该目录，且发布态禁用本跳——发布态唯一来源恒为已装包；
       env `PROMPT_PACK_MODE=force` 时禁用本跳，e2e 强制包模式用）
    ③ 都没有 → `PromptPackMissing`（AI 端点统一转 503＋专用 reason 引导获取；
       手写正文等非模板功能不受影响）

**注释剥除收口（c-prompt-source-flip）**：`load()` 返回前剥掉文件头连续的
`## `/空行——一切读取路径（含不经 `load_layers` 的裸 `load()` 调用，如 style 家族
`.format()` 与 `volume_rules` 片段注入）都由此保证纳管注释不进模型输入；
`load_layers` 的既有剥除保留（幂等）。目录解析经 `dev_template_dir()`，与
`prompt_pack` 包状态判定同源（避免「四态卡未就绪而 AI 可用」）。

读已装包时：容器（`v{N}/pack.bin`）在**内存中**解密（钥匙绑机器+用户，见
prompt_pack/localkey.py），再按 receipt 的模板 sha256 校验文本；校验不过视为缺失 →
走同一缺包路径（回滚自愈在同步器侧）。**读路径不落任何中间明文文件**，模板文本
只存在于内存（c-prompt-pack-hardening D3）。
"""

import os
import re
import sys

_PROMPTS_DIR = os.path.dirname(os.path.abspath(__file__))

# Only allow safe prompt names — alphanumeric, underscores, hyphens
_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")

SYSTEM_MARK = "<<system>>"
USER_MARK = "<<user>>"

# 强制包模式：e2e/联调跳过「开发态模板目录」一跳，验证真实分发链
FORCE_PACK_ENV = "PROMPT_PACK_MODE"
# 开发/测试态模板目录（c-prompt-source-flip）：指向提示词仓检出（sibling），
# 文件允许携带纳管注释块（load 一律剥除）。frozen 发布态不生效。
DEV_DIR_ENV = "PROMPT_PACK_DEV_DIR"


class PromptPackMissing(FileNotFoundError):
    """写作能力（提示词包）未就绪——未登录/未装包/装包损坏且无回滚位。

    继承 FileNotFoundError：历史调用方 except FileNotFoundError 的降级路径不改；
    带引导语义供上层转 503＋reason（AI 端点）。
    """


def dev_template_dir() -> str | None:
    """开发/测试态模板目录（解析序②，与 prompt_pack 包状态判定共享）。

    优先级：`PROMPT_PACK_DEV_DIR`（显式指定，目录须存在）→ 包内目录（历史兼容）。
    frozen 发布态禁用本跳（唯一来源恒为已装包）；`PROMPT_PACK_MODE=force` 同禁。
    目录不可用返回 None（走缺包路径）。
    """
    if getattr(sys, "frozen", False):
        return None
    if os.environ.get(FORCE_PACK_ENV) == "force":
        return None
    custom = (os.environ.get(DEV_DIR_ENV) or "").strip()
    if custom:
        return custom if os.path.isdir(custom) else None
    return _PROMPTS_DIR


def _from_pack(name: str) -> str | None:
    """解析序①：已装包（内存解密＋读时校验）。不可用/缺失一律 None（走回落）。"""
    try:
        from prompt_pack import read_template
    except Exception:  # noqa: BLE001 — 包模块导入失败不阻断开发态回落
        return None
    try:
        return read_template(name)
    except Exception:  # noqa: BLE001 — 读路径只做降级，自愈在同步器侧
        return None


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


def _strip_comment_lines(text: str) -> str:
    """剥掉文件头的 `## ` 版本注释行（changelog/纳管注释用，不入提示词）。"""
    lines = text.splitlines()
    i = 0
    while i < len(lines) and (not lines[i].strip() or lines[i].lstrip().startswith("##")):
        i += 1
    return "\n".join(lines[i:]).strip()


def load(name: str) -> str:
    """Load a prompt template by name (without .prompt extension).

    Raises ValueError if *name* contains unsafe characters (path traversal).
    Raises PromptPackMissing when neither the installed pack nor the dev
    template directory provides the template.
    返回前剥掉文件头注释块——一切读取路径（含裸 load() 的 .format 消费方与
    片段注入）保证纳管注释不进模型输入。
    """
    if not _SAFE_NAME_RE.match(name):
        raise ValueError(f"Invalid prompt name: {name!r}")
    # ① 已装包（发布态唯一来源；内存解密、零中间文件）。包内文本按 receipt 原样
    # 收录、不含纳管注释，但 load_layers 的历史口径是「整段剥 ## 头」，这里统一
    # 收口剥除（注释行只可能出现在段首，幂等无害）。
    text = _strip_comment_lines(_from_pack(name) or "") or None
    if text is None:
        # ② 开发/测试态模板目录（env 指定 sibling 检出 → 回退包内目录）
        dev_dir = dev_template_dir()
        if dev_dir is not None:
            path = os.path.join(dev_dir, f"{name}.prompt")
            real = os.path.realpath(path)
            # 纵深防御：文件名必须恰为 {name}.prompt（白名单已保证 name 不含 / 与 ..）
            if os.path.basename(real) == f"{name}.prompt":
                text = _read_verified(path, None)
    if text is None:
        raise PromptPackMissing(f"Prompt pack missing template: {name}")
    return _strip_comment_lines(text)


def is_layered(name: str) -> bool:
    """该模板是否已按分层协议拆好（两个标记都在）。"""
    raw = load(name)
    return SYSTEM_MARK in raw and USER_MARK in raw


def load_layers(name: str) -> tuple[str, str]:
    """分层加载 → (system, user)。

    未分层的文件返回 `("", 全文)`：迁移期向后兼容（调用方行为不变）。
    `load()` 已剥文件头注释；system 段内残留的注释/标记行（包内文本可能是
    「标记在注释前」的形态，如 ``<<system>>\\n## 头注释\\n…``）在这里二次剥除。
    """
    raw = load(name)
    if USER_MARK not in raw:
        return "", raw.strip()
    head, _, tail = raw.partition(USER_MARK)
    system = _strip_comment_lines(head.replace(SYSTEM_MARK, ""))
    return system, tail.strip()