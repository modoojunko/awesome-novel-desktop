"""工具注册表完整性守卫（c-writing-agent 批G：防「注册了函数体却没挂 fn」回归）。

背景：批A 曾把五个读类工具注册进 TOOL_REGISTRY 但漏挂 fn——run_tool 一律回
「未知工具」，e2e 界面测试才暴露。本测试把三类不变量钉死：
  1. 名字唯一；
  2. 每个工具都挂了 fn（封闭清单＝能力围栏的物理实现，缺 fn 即「够不着」）；
  3. 分级不变量：读类无档位 key；发散类 discipline=divergent 且档位=max；
     写类只允许白名单实体域（书内卷字段/知识库条目）。
"""

from assistant.tools import TOOL_REGISTRY, get_tool


def test_names_unique():
    names = [t.name for t in TOOL_REGISTRY]
    assert len(names) == len(set(names)), f"工具名重复：{names}"


def test_every_tool_has_fn():
    missing = [t.name for t in TOOL_REGISTRY if t.fn is None]
    assert missing == [], f"注册未挂 fn 的工具：{missing}"


def test_read_tools_are_free():
    reads = [t for t in TOOL_REGISTRY if t.kind == "read"]
    assert reads, "读类工具不应为空"
    assert all(t.feature_key == "" for t in reads), "读类工具必须免费（feature_key 空）"


def test_card_tools_have_feature_gate():
    cards = [t for t in TOOL_REGISTRY if t.kind == "card"]
    assert cards, "产卡类工具不应为空"
    for t in cards:
        assert t.feature_key in ("ai-plan", "settings-ai-fields", "assistant-diverge", "ai-generate"), t.name


def test_divergent_discipline_only_on_diverge_tools():
    for t in TOOL_REGISTRY:
        if t.discipline == "divergent":
            assert t.name.startswith("diverge_"), f"发散纪律只允许发散工具：{t.name}"
    diverge = [t for t in TOOL_REGISTRY if t.name.startswith("diverge_")]
    assert diverge and all(t.discipline == "divergent" for t in diverge)


def test_write_surface_is_fenced():
    writes = [t for t in TOOL_REGISTRY if t.kind == "write"]
    allowed = {"write_volume_fields", "kb_create_entry", "kb_update_entry"}
    names = {t.name for t in writes}
    assert names <= allowed, f"写面越界：{names - allowed}"
    # 硬地板结构性缺席：删全书/批量删章/改档位永不注册
    forbidden = {"delete_book", "batch_delete_chapters", "set_permission_tier"}
    assert not (names & forbidden), f"硬地板操作不得进入工具清单：{names & forbidden}"


def test_get_tool_strips_whitespace():
    assert get_tool("  read_progress  ") is not None
    assert get_tool("不存在的工具") is None
