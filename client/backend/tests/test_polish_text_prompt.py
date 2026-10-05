"""polish_text.prompt v4（c-polish-prompt-anti-ai）：策略驱动升级的特征串断言。

v3.1 → v4：新增降AI策略优先级（信息轮次化第一）与死路禁令；结构红线同源成文；
检查清单节奏校准与破折号零容忍；铁律篇幅分档；优先级栈红线压过策略。
"""

from prompts import load_layers


def _system() -> str:
    system, _ = load_layers("polish_text")
    return system


def test_v4_strategy_dead_end_red_lines_present():
    system = _system()
    # 降AI策略优先级（信息轮次化第一，人物在场护栏）
    assert "## 降AI策略优先级" in system
    assert "信息轮次化" in system
    assert "不虚构对话对象" in system
    assert "场景换场" in system and "极简化" in system
    # 死路禁令（含禁用词必改例外与示例实体防护行）
    assert "## 死路" in system
    assert "书级禁用词命中时的必改除外" in system
    assert "示例中的人名与场景不得进入改写产物" in system
    # 结构红线（与「反AI结构红线注入」同源要点）
    assert "## 结构红线" in system
    assert "尾随标签" in system and "引语三明治" in system
    assert "汇报链" in system and "微闭环" in system


def test_v4_checklist_and_iron_rules_calibrated():
    system = _system()
    # 节奏校准：逗号长句默认；旧「拆长并短」退役
    assert "叙述句意思说完才打句号" in system
    assert "拆长并短" not in system
    # 对仗句表达力例外取消
    assert "确有表达力的可保留" not in system
    # 破折号零容忍（清单第 2 条不再合计三处才改）
    assert "破折号一律删除" in system
    assert "破折号、分号合计三处及以上" not in system
    # 铁律篇幅：110% 默认、信息轮次化 160%；旧「70% 属正常」退役
    assert "信息轮次化改写（叙述改对话轮次）放宽至 160%" in system
    assert "70% 左右属正常" not in system
    # 优先级栈：结构红线压过降AI策略
    assert "禁止规则（书级词表命中必改）＞结构红线＞降AI策略优先级＞本检查清单" in system


def test_v4_templates_format_safe():
    """polish 的 system/user 两段在服务层都要过 .format(**ctx)（auxiliary.polish_text）——
    模板不得含裸花括号（评审补的冒烟断言，防未来示例引入花括号炸端点）。"""
    system, user_t = load_layers("polish_text")
    ctx = {
        "writing_style": "风格",
        "anti_ai_rules": "（无）",
        "selected_text": "选段测试文本",
        "surrounding_context": "上下文",
        "recent_context": "r",
        "character_snapshots": "c",
        "active_hooks": "h",
        "_role": "一位小说家",
        "_writing_model": "haiku",
    }
    assert "选段测试文本" in user_t.format(**ctx)
    assert system.format(**ctx)
