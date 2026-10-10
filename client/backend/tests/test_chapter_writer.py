"""Tests for ChapterContext builder（c-write-prompt-layering 分层口径）.

system 恒定层（build_system_prompt）＝本书设定：角色/契约/题材/文风/世界观/铁律/卷纲/档案锚，
逐章字节一致；user 章级素材（to_user_material）＝章纲/条目/落点/状态/影子覆盖/伏笔/章级红线/字数。
"""

from settings.style_model import normalize_style
from write.chapter_writer import (
    WRITE_CLOSING_LINE,
    ChapterContext,
    is_legacy_write_prompt,
    legacy_prompt_kind,
    lint_assembled_prompt,
    resolve_persona,
)


class TestUserMaterial:
    """to_user_material：章级动态素材（原 to_prompt 整包退役）。"""

    def test_empty_context_returns_valid_material(self):
        ctx = ChapterContext()
        prompt = ctx.to_user_material()
        assert isinstance(prompt, str)
        assert len(prompt) > 50
        assert "## 当前章节" in prompt
        # 恒定块 SHALL NOT 回到 user 层
        assert "## 角色定位" not in prompt
        assert "## 故事背景" not in prompt
        assert "## 题材设定" not in prompt
        assert "## 文风" not in prompt
        assert "## 原则与禁忌" not in prompt

    def test_with_ladder_exit(self):
        ctx = ChapterContext()
        ctx.ladder_exit = "枪口对着林野，同僚等他放下刀"
        prompt = ctx.to_user_material()
        assert "章末落点：枪口对着林野" in prompt

    def test_with_hooks_carry_code_and_priority(self):
        """伏笔行带 [编号]＋优先级前缀，与素材包渲染器同口径（设计决策 3）。"""
        ctx = ChapterContext()
        ctx.hooks = [
            {"description": "刀身异样", "code": "H-0002", "priority_label": "高"},
            {"description": "神秘信件"},
        ]
        prompt = ctx.to_user_material()
        assert "[H-0002] 刀身异样（优先级：高）" in prompt
        assert "- 神秘信件" in prompt

    def test_with_characters(self):
        ctx = ChapterContext()
        ctx.characters = [
            {"name": "张三", "state": "正在调查", "speech": "话短句沉"},
            {"name": "李四", "state": "隐藏身份"},
        ]
        prompt = ctx.to_user_material()
        assert "- 张三：正在调查（语言特征：话短句沉）" in prompt
        assert "- 李四：隐藏身份" in prompt

    def test_with_previous_chapter_recap(self):
        ctx = ChapterContext()
        ctx.previous_chapter_recap = "上一章结尾，张三推开了那扇门。"
        prompt = ctx.to_user_material()
        assert "上一章结尾" in prompt

    def test_word_target_floor_and_expansion(self):
        """字数要求＝只设下限（目标-10%），可多不可少；不足走扩写既有场景。"""
        ctx = ChapterContext()
        ctx.word_target = 4000
        prompt = ctx.to_user_material()
        assert "写故事至少 4000 字，可以多，不可以少" in prompt
        assert "低于 3600 字不合格" in prompt
        assert "扩写既有场景" in prompt

    def test_chapter_red_lines_exclude_world_iron_rules(self):
        """世界铁律上收 system 恒定层；user 章级红线只留随章变化的承诺。"""
        ctx = ChapterContext()
        ctx.world_setting = {
            "constraints": [{"name": "血族畏光", "note": "正午直射阳光三秒焚毁"}],
        }
        ctx.required_changes = ["林野从巡护员变成被围住的疑似半血"]
        ctx.prohibitions = ["不写林野主动暴露血脉"]
        prompt = ctx.to_user_material()
        assert "本章必须完成：林野从巡护员" in prompt
        assert "禁止：不写林野主动暴露血脉" in prompt
        assert "血族畏光" not in prompt
        assert "世界铁律见指令恒定层" in prompt

    def test_shadow_override_block_in_user_not_system(self):
        """章级文风影子：基线恒定层不动，命中行进 user 覆盖块并声明优先级。"""
        ctx = ChapterContext()
        ctx.style_quant = {
            "confidence": 8,
            "baseline": {
                "syntax": {"value": "平均句长13.2字", "tolerance": 20},
                "narrative": {"value": "第三人称限知", "tolerance": 20},
            },
        }
        ctx.style_shadow = {
            "syntax": {"value": "平均句长8字", "reason": "回退章节奏加快"},
        }
        user = ctx.to_user_material()
        assert "## 本章文风覆盖" in user
        assert "覆盖指令恒定层中的文风基线" in user
        assert "约 平均句长8字（本章覆盖：回退章节奏加快）" in user
        system = ctx.build_system_prompt()
        assert "本章覆盖" not in system
        assert "约 平均句长13.2字" in system  # 基线原值保持

    def test_no_shadow_no_override_block(self):
        ctx = ChapterContext()
        assert "## 本章文风覆盖" not in ctx.to_user_material()


class TestSystemPrompt:
    """build_system_prompt：本书恒定层——恒定块齐全、空段跳过、逐章一致。"""

    def test_contract_and_arbiter_present(self):
        ctx = ChapterContext()
        system = ctx.build_system_prompt()
        assert "只输出正文本身" in system
        assert "视为已写情节" in system
        assert "未命名的次要角色用泛指" in system

    def test_anti_ai_red_lines_in_system(self):
        """c-write-prompt-anti-ai：反AI结构红线清单进恒定层（模板静态文本）。"""
        ctx = ChapterContext()
        system = ctx.build_system_prompt()
        assert "## 写法要求（反AI结构红线）" in system
        assert "结构强禁令" in system
        assert "尾随标签" in system and "引语三明治" in system
        assert "叙述句意思说完才打句号" in system
        assert "与素材的约束红线、剧情条目、章末落点冲突时，素材优先" in system
        # craft_rules 占位注入退役：旧一句话口径不得再出现在渲染产物中
        assert "按场景权重分配笔墨" not in system

    def test_persona_default_on_empty_string(self):
        """历史「你是。」缺陷：role 键存在但为空串 → 兜底默认身份。"""
        assert resolve_persona({"role": ""}) == "一位小说家"
        assert resolve_persona({}) == "一位小说家"
        assert resolve_persona({"role": "冷峻的叙事者"}) == "冷峻的叙事者"
        ctx = ChapterContext()
        ctx.style_setting = {"role": ""}
        assert "你是。" not in ctx.build_system_prompt()
        assert "一位小说家" in ctx.build_system_prompt()

    def test_premise_and_arc_in_system(self):
        ctx = ChapterContext()
        ctx.novel_title = "暗流"
        ctx.premise = "一个退役刑警调查悬案的故事"
        ctx.story_arc = "从悬案追到体制黑幕"
        system = ctx.build_system_prompt()
        assert "暗流" in system
        assert "退役刑警" in system
        assert "全书主线：从悬案追到体制黑幕" in system

    def test_genre_in_system_not_user(self):
        ctx = ChapterContext()
        ctx.genre_section = "题材：西式奇幻\n核心承诺：以弱破强的痛快"
        system = ctx.build_system_prompt()
        assert "核心承诺" in system

    def test_style_settings_render_into_system(self):
        """style-settings-v2 三区文风段随恒定层上收（ADR-006 双态仍兼容）。"""
        ctx = ChapterContext()
        ctx.style_setting = normalize_style({
            "role": "冷峻的叙事者",
            "core_principles": ["简洁", "有力"],
            "possible_mistakes": ["不要滥用形容词"],
            "depiction_techniques": {"action": "快速剪辑"},
        })
        system = ctx.build_system_prompt()
        assert "冷峻的叙事者" in system
        assert "快速剪辑" in system
        assert "简洁" in system and "有力" in system
        assert "叙事基调" not in system
        assert "文风常见错误" not in system

    def test_banned_words_in_system_and_skip_when_empty(self):
        ctx = ChapterContext()
        ctx.style_setting = {"role": "一位小说家", "banned_words": ["突然", "忽然"]}
        system = ctx.build_system_prompt()
        assert "禁止使用以下词汇：突然, 忽然" in system
        empty = ChapterContext().build_system_prompt()
        assert "禁止使用以下词汇" not in empty
        assert "## 原则与禁忌" not in empty

    def test_few_shot_examples_in_system(self):
        ctx = ChapterContext()
        ctx.style_setting = {"few_shot_examples": ["他把刀放回鞘里，像掩埋一句话。"]}
        assert "他把刀放回鞘里" in ctx.build_system_prompt()

    def test_world_full_injection_no_omission_note(self):
        """势力全量：无预算截断、无「另有 N 条从略」（设计决策 1/归属表）。"""
        ctx = ChapterContext()
        ctx.world_setting = {
            "stage": "十九世纪末煤气灯港城",
            "factions": [
                {"name": "夜巡守夜人", "note": "出售巡逻路线换取停战"},
                {"name": "圣银教团", "note": "视半血为待验圣器"},
                {"name": "血族议会", "note": "主战派与豢养派分裂"},
            ],
        }
        system = ctx.build_system_prompt()
        assert "夜巡守夜人" in system
        assert "圣银教团" in system
        assert "血族议会" in system
        assert "从略" not in system

    def test_world_iron_rules_section(self):
        ctx = ChapterContext()
        ctx.world_setting = {
            "constraints": [{"key": "血族畏光", "value": "正午直射阳光三秒焚毁"}],
        }
        system = ctx.build_system_prompt()
        assert "世界铁律·血族畏光" in system

    def test_empty_sections_dropped(self):
        """空段整节跳过：无题材/无卷纲/无角色 → 不出空节（恒定层 SHALL NOT 空节）。"""
        system = ChapterContext().build_system_prompt()
        assert "## 题材设定" not in system
        assert "## 本卷卷纲" not in system
        assert "## 人物档案" not in system

    def test_cast_anchors_full_roster_not_chapter_filtered(self):
        """c-cast-split-user-layer：system 锚＝主角/反派恒定卡；配角与未设角色不入 system。"""
        ctx = ChapterContext()
        ctx.cast_items = [
            {"name": "林野", "role": "主角", "persona": "求安稳的夜班巡护员"},
            {"name": "银铎", "role": "配角", "persona": "教团猎魔人"},
            {"name": "猎魔人", "role": "", "dossier": {"speech": "教规腔"}},
        ]
        system = ctx.build_system_prompt()
        assert "林野" in system
        assert "求安稳的夜班巡护员" in system
        assert "银铎" not in system
        assert "猎魔人" not in system
        assert "求安稳的夜班巡护员" in system

    def test_system_stable_across_chapters(self):
        """同书两章（不同出场/剧情/前情/影子）system 逐字节一致。"""
        base_quant = {
            "confidence": 8,
            "baseline": {"syntax": {"value": "平均句长13字", "tolerance": 20}},
        }
        a = ChapterContext()
        b = ChapterContext()
        a.style_quant = base_quant
        a.characters = [{"name": "张三", "state": "调查中"}]
        a.previous_chapter_recap = "上章结尾……"
        a.required_changes = ["张三黑化"]
        # 同一书级基线＋章级影子：影子只进 user 层，system 不动
        b.style_quant = base_quant
        b.style_shadow = {"syntax": {"value": "平均句长8字", "reason": "支线章"}}
        assert a.build_system_prompt() == b.build_system_prompt()

    def test_new_character_changes_system_once_user_carries_appearance(self):
        """c-cast-split-user-layer：新增配角 system 逐字节不变；出场配角走 user 层。

        旧口径（配角入 system、新增时 system 变化一次）随 c-cast-split-user-layer
        退役：极性卡（主角/反派）恒定，配角按本章素材文本匹配出场进 user。
        """
        base = ChapterContext()
        base.cast_items = [{"name": "林野", "role": "主角", "persona": "巡护员"}]
        grown = ChapterContext()
        grown.cast_items = [
            {"name": "林野", "role": "主角", "persona": "巡护员"},
            {"name": "银铎", "role": "配角", "persona": "教团猎魔人"},
        ]
        # 新增配角：system 不动（缓存前缀不受新角色影响）
        assert base.build_system_prompt() == grown.build_system_prompt()
        # 本章素材提到银铎 → user 层出「本章出场配角」卡
        onstage = ChapterContext()
        onstage.cast_items = grown.cast_items
        onstage.plot_items = ["银铎在巷口拦住林野盘问"]
        user = onstage.to_user_material()
        assert "## 本章出场配角" in user
        assert "银铎" in user
        # 未出场 → 两层都不出现
        offstage = ChapterContext()
        offstage.cast_items = grown.cast_items
        assert "银铎" not in offstage.to_user_material()

    def test_supporting_cast_matched_by_alias(self):
        """出场判定含别名：本章素材用别名提到，卡仍按出场注入。"""
        ctx = ChapterContext()
        ctx.cast_items = [
            {"name": "银铎", "role": "配角", "aliases": ["教团女人"], "persona": "猎魔人"},
        ]
        ctx.previous_tail = "教团女人收起银盘，转身离开。"
        user = ctx.to_user_material()
        assert "## 本章出场配角" in user
        assert "银铎" in user

    def test_braces_in_material_do_not_crash(self):
        """花括号素材（JSON/修辞）不崩：占位符填充 SHALL 用顺序 replace。"""
        ctx = ChapterContext()
        ctx.premise = '他的信条只有一条：{"活下去": 1}——其余都是借口'
        ctx.style_setting = {"banned_words": ["{突然}"]}
        system = ctx.build_system_prompt()
        assert '{"活下去": 1}' in system


class TestLegacyAndLint:
    """legacy 分级判定＋组装 lint（c-write-prompt-layering）。"""

    def test_legacy_headings_detected(self):
        assert is_legacy_write_prompt("## 角色定位\n你是。")
        assert is_legacy_write_prompt("## 故事背景\n故事前提：……")

    def test_legacy_polished_row_by_three_anchors(self):
        # 润色稿行：无恒定块标题但三锚同现（任务指示/红线/质感）
        polished = "## 任务指示\n写一场巷战\n## 红线\n不可违反\n## 质感\n细节克制"
        assert is_legacy_write_prompt(polished)
        # 新 user 层（含「## 当前章节」但无三锚中的「任务指示」「质感」）→ 非 legacy
        fresh = ChapterContext().to_user_material()
        assert not is_legacy_write_prompt(fresh)

    def test_plain_stored_row_not_legacy(self):
        assert not is_legacy_write_prompt("既有润色行")

    def test_legacy_kind_graded(self):
        """分级：粗组存稿旧行＝raw（建议刷新）；润色行＝polished（只信息性）。"""
        assert legacy_prompt_kind("## 角色定位\n你是。") == "raw"
        polished = "## 任务指示\n写巷战\n## 红线\n不可违反\n## 质感\n克制"
        assert legacy_prompt_kind(polished) == "polished"
        assert legacy_prompt_kind("既有润色行") == ""

    def test_polished_row_with_heading_echo_stays_polished(self):
        """评审 P2：润色产物回显【故事背景】【文风】节头（material_markdown 含这些块，
        prompt_crafting 要求产物保持分节）仍判 polished——三锚优先于节头标记，
        不把刚润色的行误判 raw 去建议刷新。"""
        echoed = (
            "## 任务指示\n第 2 章，写巷战。\n"
            "## 故事背景\n本段是《暗流》的一章。\n"
            "## 文风\n冷峻克制\n"
            "## 红线\n不可违反\n## 质感\n细节克制"
        )
        assert legacy_prompt_kind(echoed) == "polished"

    def test_lint_required_changes_uncovered(self):
        warns = lint_assembled_prompt(
            ["林野从巡护员变成被围住的疑似半血"], ["夜禁后巷口伏击战开场"], []
        )
        assert any("未获剧情条目覆盖" in w for w in warns)
        # 条目为空 → 单条告警
        warns = lint_assembled_prompt(["转变一"], [], [])
        assert any("剧情条目为空" in w for w in warns)

    def test_lint_required_changes_covered_no_warn(self):
        warns = lint_assembled_prompt(
            ["林野被同僚举枪围住"], ["同僚举枪围住林野，等他放下刀"], []
        )
        assert not any("未获剧情条目覆盖" in w for w in warns)

    def test_lint_revealed_hook_in_active_list(self):
        warns = lint_assembled_prompt([], ["条目"], [{"description": "揭：林野得知灭门真相"}])
        assert any("混入已兑现记录" in w for w in warns)


def test_closing_line_constant():
    """收尾重申行：同词不同句（与模板铁律 1 措辞异形，防被当回声）。"""
    assert "仅正文" in WRITE_CLOSING_LINE
    assert "Markdown" in WRITE_CLOSING_LINE
    assert "章末落点" in WRITE_CLOSING_LINE
    assert "不写一个字" in WRITE_CLOSING_LINE
