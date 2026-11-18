"""页签域映射（c-agent-fleet 改型：每页签独立流程）。

thread 前缀→域：ch:og＝章纲 / ch:prose＝正文 / set:*＝设定 / vol＝卷纲 /
preview＝预览 / 其余＝默认（仅共享读）。每域声明面＝全域共享读＋本域产卡/写类；
域外工具调用不执行（回喂引导）。启动校验：注册表 30 工具必须全部落在
「共享读 ∪ 至少一个域」内，漏配 fail loud（防「功能突然没了」）。
"""

from __future__ import annotations

# 全域共享（任何页签都声明）：读类＋画像＋知识库检索＋角色草案三段式
_SHARED_TOOLS = frozenset(
    {
        "read_progress",
        "read_settings",
        "read_outline",
        "read_chapter",
        "read_story_state",
        "profile_read",
        "profile_update",
        "kb_search",
        "kb_read",
        "draft_character",
        # 书级记忆（c-agent-chat-memory 批4）：记忆是书级跨页签资产，全页签域共享
        "recall_book_memory",
        "remember_book_memory",
        "forget_book_memory",
        "remember_decision",
        "read_chapter_versions",
        "read_book_structure",
        # 结构管理动作（c-agent-tools-expand）：书级操作全域共享
        "confirm_chapter", "unconfirm_chapter",
        "archive_chapter", "unarchive_chapter",
        "add_volume", "add_chapter",
    }
)

# 域内工具（按 thread 前缀）
_DOMAIN_TOOLS: dict[str, dict[str, frozenset[str]]] = {
    "ch:og": {
        "domain": "章纲",
        "label": "章纲助手",
        "tools": frozenset(
            {
                "draft_chapter_plot",
                "draft_chapter_split",
                "settings_og_fill",
                "check_consistency",
                "draft_names",
                "simulate_plot",
                "draw_plot_cards",
                "review_cast",
                "switch_tab",  # 页签切换（c-agent-nav）：章节七页签域内可见，共享集不加
            }
        ),
    },
    "ch:prose": {
        "domain": "正文",
        "label": "正文助手",
        "tools": frozenset({"switch_tab"}),  # 正文页以读为流程；生成走既有写作流不占对话
    },
    "set:": {
        "domain": "设定",
        "label": "设定助手",
        "tools": frozenset(
            {
                "settings_genre_core_promise",
                "settings_genre_forbidden_list",
                "settings_genre_cost_ratio",
                "settings_genre_battlefield",
                "settings_hooks_draft",
                "draft_worldbuilding", "check_worldbuilding", "lore_suggest",
                "settings_hooks_check",
                "settings_intro",
                "draft_arc",
                "check_consistency",
                "draft_names",
                "diverge_character_group",
                "kb_create_entry",
                "kb_update_entry",
            }
        ),
    },
    "ch:settings": {
        "domain": "设定",
        "label": "设定助手",
        "tools": frozenset({"check_consistency", "switch_tab"}),
    },
    "ch:relations": {
        "domain": "关系",
        "label": "关系助手",
        "tools": frozenset({"check_consistency", "switch_tab"}),
    },
    "ch:hooks": {
        "domain": "伏笔",
        "label": "伏笔助手",
        "tools": frozenset({"check_consistency", "switch_tab"}),
    },
    "ch:actions": {
        "domain": "操作",
        "label": "操作助手",
        "tools": frozenset({"switch_tab"}),
    },
    "ch:style": {
        "domain": "文风",
        "label": "文风助手",
        "tools": frozenset({"check_consistency", "switch_tab"}),
    },
    "vol": {
        "domain": "卷纲",
        "label": "卷纲助手",
        "tools": frozenset(
            {
                "draft_volume_plan",
                "draft_volume_expand",
                "write_volume_fields",
                "check_consistency",
                "draft_names",
                "draft_arc",
                "diverge_plot_branches",
                "diverge_character_group",
                "draft_chapter_split",
            }
        ),
    },
    "preview": {
        "domain": "预览",
        "label": "预览助手",
        "tools": frozenset(),  # 预览页只读
    },
}

# 默认域（thread 不匹配任何前缀）：仅共享读
_DEFAULT_DOMAIN = {"domain": "", "label": "助手", "tools": frozenset()}

# 工具→域归属（供轨迹标签与启动校验；一工具可属多域）
_TOOL_DOMAINS: dict[str, list[str]] | None = None


def _domain_of_thread(thread: str) -> dict:
    """thread→域定义（前缀匹配，长前缀优先：ch:og/ch:prose 先于默认）。"""
    thread = (thread or "").strip()
    for prefix, spec in _DOMAIN_TOOLS.items():
        if thread == prefix or thread.startswith(prefix):
            return spec
    return _DEFAULT_DOMAIN


def domain_of_thread(thread: str) -> str:
    """域中文名（共享读不带域；默认域＝空串）。"""
    return str(_domain_of_thread(thread)["domain"])


def domain_label_of_thread(thread: str) -> str:
    """域助手标签（轨迹组头用；默认域＝「助手」）。"""
    return str(_domain_of_thread(thread)["label"])


def tools_for_thread(thread: str) -> set[str]:
    """本线程可声明的工具集合＝共享读＋域内清单。"""
    return set(_SHARED_TOOLS) | set(_domain_of_thread(thread)["tools"])


def tool_domain(tool: str) -> str:
    """工具的域归属（多域取第一个命中；仅共享读＝空串）。轨迹标签用。"""
    global _TOOL_DOMAINS
    if _TOOL_DOMAINS is None:
        mapping: dict[str, list[str]] = {}
        for spec in _DOMAIN_TOOLS.values():
            for name in spec["tools"]:
                mapping.setdefault(str(name), []).append(str(spec["domain"]))
        _TOOL_DOMAINS = mapping
    domains = _TOOL_DOMAINS.get(tool) or []
    return domains[0] if domains else ""


def out_of_scope_guidance(tool: str, thread: str) -> str:
    """域外调用的回喂话术：指明能力归属页签。"""
    for prefix, spec in _DOMAIN_TOOLS.items():
        if tool in spec["tools"]:
            page_hint = {
                "ch:og": "章纲页签",
                "ch:prose": "正文页签",
                "set:": "设定页签",
                "vol": "卷纲页签",
                "preview": "预览页签",
            }.get(prefix, prefix)
            return (
                f"「{tool}」是{page_hint}（{spec['domain']}）的能力——这个页签"
                f"走的是「{domain_label_of_thread(thread)}」流程。切到{page_hint}"
                "再试，或直接告诉我想达成什么，我看本页签能帮到哪一步。"
            )
    if tool in _SHARED_TOOLS:
        return ""  # 共享读不会域外（理论上不可达；防御空串）
    return f"「{tool}」不在本页签的流程里。"



# 域纪律分节（每页签独立流程的纪律面；自身份单源派生——只含域纪律，身份/语气仍单源）
PAGE_DISCIPLINE: dict[str, str] = {
    "章纲": "章纲纪律：概要/角色/变化/悬念/阶段五项口径；节奏档位以书级设定为准；产物一律过目，不直接落库。",
    "正文": "正文纪律：人味红线（短句、口语、禁 AI 腔）；对话只做诊断与建议——正文生成走既有写作流，不在对话里代笔。",
    "设定": "设定纪律：题材词表口径优先；改动一律产卡过目；不得与既有设定冲突。",
    "卷纲": "卷纲纪律：六段口径（目标/冲突/结局/章数/反派类型/反派线）；写回前必过目。",
}


def discipline_of_thread(thread: str) -> str:
    """本线程的域纪律分节（默认域＝空串——只走共享读，无专属纪律）。"""
    domain = domain_of_thread(thread)
    return PAGE_DISCIPLINE.get(domain, "")


def validate_scopes(registry_names: set[str]) -> list[str]:
    """启动校验：注册表每个工具必须落在「共享读 ∪ 至少一个域」内，漏配即报。"""
    covered = set(_SHARED_TOOLS)
    for spec in _DOMAIN_TOOLS.values():
        covered |= set(spec["tools"])
    orphans = sorted(registry_names - covered)
    unknown = sorted(covered - registry_names)
    errors: list[str] = []
    if orphans:
        errors.append(f"域映射漏配（这些工具任何页签都够不着）：{orphans}")
    if unknown:
        errors.append(f"域映射引用了注册表外的工具：{unknown}")
    return errors
