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
        assert t.feature_key in ("ai-plan", "settings-ai-fields", "assistant-diverge", "ai-generate", "ai-plot"), t.name


def test_divergent_discipline_only_on_diverge_tools():
    for t in TOOL_REGISTRY:
        if t.discipline == "divergent":
            assert t.name.startswith("diverge_"), f"发散纪律只允许发散工具：{t.name}"
    diverge = [t for t in TOOL_REGISTRY if t.name.startswith("diverge_")]
    assert diverge and all(t.discipline == "divergent" for t in diverge)


def test_write_surface_is_fenced():
    writes = [t for t in TOOL_REGISTRY if t.kind == "write"]
    allowed = {
        "write_volume_fields", "kb_create_entry", "kb_update_entry",
        # 结构管理动作（c-agent-tools-expand）：写类走授权梯度，默认每写必确认
        "confirm_chapter", "unconfirm_chapter",
        "archive_chapter", "unarchive_chapter",
        "add_volume", "add_chapter",
        # 字段级页面写（c-agent-page-ops）：全过 write_gate 两层授权
        "write_chapter_fields", "write_settings_field",
    }
    names = {t.name for t in writes}
    assert names <= allowed, f"写面越界：{names - allowed}"
    # 硬地板结构性缺席：删全书/批量删章/改档位永不注册
    forbidden = {"delete_book", "batch_delete_chapters", "set_permission_tier"}
    assert not (names & forbidden), f"硬地板操作不得进入工具清单：{names & forbidden}"


def test_write_tools_have_human_preview_summary():
    """写类授权卡必须有人话摘要——作家看不懂裸 JSON（2026-11-21 实锤）。

    preview_builder 之外的兜底形状由 write_gate._preview 生成；新增写工具漏挂
    中文动作名时，卡面会退回 {"tool","args"} 裸 JSON，本钉子拦住。"""
    from assistant.write_gate import _preview

    missing = [
        t.name
        for t in TOOL_REGISTRY
        if t.kind == "write"
        and not _preview(t.name, {"chapter_ref": "vol-1-ch-2"}).get("summary")
    ]
    assert missing == [], f"授权卡缺人话摘要的写工具：{missing}"


def test_preview_builders_match_router_contract():
    """preview_builder 契约＝(args, project)——router 按两参调用（review P2 整改）。

    曾按 builder(args) 单参调，TypeError 被 _build_gate_preview 兜底吞掉→字段
    对比链整体失效、作家看裸 JSON。这里绕过兜底直接按契约调一遍：签名漂移
    当场 TypeError 红，不静默回落。约定：builder 须容忍 project=None（当「读
    不到现值」短路，两个现 builder 均如此），测试因此免 DB。"""
    import asyncio

    sample = {
        "chapter_ref": "vol-1-ch-1",
        "fields": {"summary": "x"},
        "stype": "story",
        "field": "synopsis",
        "value": "x",
    }
    broken = []
    for t in TOOL_REGISTRY:
        if t.preview_builder is None:
            continue
        try:
            out = t.preview_builder(sample, None)
        except TypeError as e:
            broken.append(f"{t.name}: {e}")
            continue
        if asyncio.iscoroutine(out):
            out.close()  # 只验签名不执行——副作用路径由 router helper 测试钉
    assert broken == [], f"preview_builder 契约漂移（须为 (args, project)）：{broken}"


def test_get_tool_strips_whitespace():
    assert get_tool("  read_progress  ") is not None
    assert get_tool("不存在的工具") is None


# ── ToolSpec schema 守卫（c-agent-harness tasks 2.4）─────────────────────────


def _schema_props(schema: dict | None) -> dict:
    assert isinstance(schema, dict), "parameters 必须是 JSON Schema 对象"
    assert schema.get("type") == "object", "parameters.type 必须 object"
    props = schema.get("properties")
    assert isinstance(props, dict), "parameters.properties 必须是对象"
    req = schema.get("required") or []
    unknown = set(req) - set(props)
    assert not unknown, f"required 引用了未声明的属性：{unknown}"
    return props


def test_every_tool_has_valid_json_schema():
    for t in TOOL_REGISTRY:
        props = _schema_props(t.parameters)
        for key, spec in props.items():
            assert isinstance(spec, dict), f"{t.name}.{key} 属性定义必须是对象"
            assert "type" in spec or "description" in spec, f"{t.name}.{key} 缺 type/description"
            if spec.get("type") == "object":
                assert isinstance(spec.get("properties", {}), dict), f"{t.name}.{key} 嵌套对象 properties 必须是对象"


def test_args_hint_derived_from_schema():
    # 单一参数源：args_hint 自 schema 派生——键集合须与 properties 一致
    for t in TOOL_REGISTRY:
        props = _schema_props(t.parameters)
        if not props:
            assert t.args_hint == "{}", f"{t.name} 空参数 schema 的 args_hint 应为 {{}}"
            continue
        assert t.args_hint.startswith("{") and t.args_hint.endswith("}"), t.name
        for key in props:
            assert f'"{key}"' in t.args_hint, f"{t.name} args_hint 缺属性 {key}：{t.args_hint}"


def test_openai_spec_shape():
    for t in TOOL_REGISTRY:
        spec = t.openai_spec()
        assert spec["type"] == "function"
        fn = spec["function"]
        assert fn["name"] == t.name
        assert fn["description"] == t.description
        assert fn["parameters"]["type"] == "object"
