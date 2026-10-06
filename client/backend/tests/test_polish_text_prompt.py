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


def test_v44_tier4_and_near_copy_verdict():
    """v4.4（design D8）：策略栈补第 4 档兜底＋完成判定近拷贝判负——
    真机复判「产物≈原文」的两件套。锁特征串，防未来改提示词时静默回退。
    含提示词工程师评审整改：清单第 0 条关逃逸、逐句可查判据、档位可叠加、
    首尾即正文不变量、user 末行回指。"""
    system = _system()
    # 第 4 档：前三档不适用时的兜底杠杆（案例包终局方法论「整段重写换句式骨架」）
    # ＋评审 P1-3：也是判负后的补刀（档位可叠加非互斥）
    assert "整段重写换句式骨架" in system
    assert "第 4 档" in system
    assert "也是施完前档后仍被判近拷贝时的补刀" in system
    assert "档位可叠加不是互斥" in system
    # 策略 1 兜底指向含第 4 档（旧「第 2/3 档或原样保留」退役）
    assert "改用第 2/3/4 档" in system
    assert "改用第 2/3 档或原样保留" not in system
    # 近拷贝判负：评审 P1-2 逐句可查口径（引号外叙述句×句长结构/主谓关系＋半数阈值）
    assert "逐句检查引号外的叙述句" in system
    assert "句长结构与主谓关系照搬" in system
    assert "半数以上引号外句子照搬原句" in system
    assert "引号内字句原样不动优先于本判定" in system
    assert "对话轮次不豁免本判定" in system
    assert "只调整词句、不转换载体、不换骨架的改写，不是本任务的合格产出" in system
    # 评审 P1-1：清单第 0 条不再签发原样交回（旧「原样保留，不为改而改」退役）
    assert "原样交回只有「选区全部为既有对话」一种情形合法" in system
    assert "不为改而改 ≠ 原样交回" in system
    assert "没有命中以下任何问题的句子，原样保留" not in system
    # 评审 P2-4：调语序合法边界（伴随句长重排/主谓修饰实质变化）
    assert "调语序必须伴随句长重排或主谓/修饰关系的实质变化" in system
    # 死路出口收窄：纯既有对话选区是唯一合法回显场景
    assert "选区全部为既有对话原文、引号内字句不可动时，原样保留" in system
    assert "没有策略可施的句子，原样保留" not in system
    # 评审 P2-7①：末位结构不变量（首尾即正文，旁白必然违反）
    assert "产物的第一个字必须是正文的第一个字" in system
    # 评审 P2-7② user 层回指（近因位延伸）——在 user 模板上
    _, user_t = load_layers("polish_text")
    assert "完成判定」自检" in user_t
