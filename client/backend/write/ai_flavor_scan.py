"""AI 味检查（c-deai-wizard）：修稿向导第①步的本地确定性扫描＋问题段合并＋改稿快扫。

三合一单源（CLI/端点/测试共用，禁止第二份实现）：
- ``scan_prose``：本地规则扫描——判据移植资产包 ``_precheck.py``（夜班车交付门禁）
  ＋人味二-11/12 补两条（段内句号密度／相邻段首同词）。产出 findings（blocking/
  advisory）与软指标。0 模型 0 检测额度。
- ``build_problem_segments``：两路来源合并——本地规则命中段＋朱雀判定段
  （conf ≥ 0.5，来自检测存档 ``ZhuqueResultArchive``）——去重为问题段清单，
  供向导第②步勾选、第③步逐段改写。
- ``quick_verdict``：polish 产物程序化快扫（PE 评审 E）——书级禁用词／新增结构
  红线／引号奇偶／格式泄漏为 blocking；字数带／数字守恒为 advisory。命中只降级
  不销毁（作家仍有一票）。

段号口径：**0-based 非空段序**（与 ``zhuque.segmentation.align_segments`` 的
``paragraph_index`` 同轨）；UI 展示时 +1。

改法建议（``SUGGESTED_FIX_LABELS``）为启发式映射，纯展示不喂模型——最终以
polish 第 0 步诊断为准（c-deai-wizard 评审 B 裁决：一期 hint 不喂）。
"""

from __future__ import annotations

import re

# ── 规则 id 常量（前端/测试引用同一字面量） ──────────────────────────────

RULE_LABELS: dict[str, str] = {
    "multi_period": "段内句号过密——一口气读完的动作之间应逗号连缀",
    "para_head_repeat": "相邻段落用同一个词起手",
    "canned_reaction": "疑似罐装反应句（愣了一下／沉默了几秒类）",
    "simile_word": "比喻词（仿佛／似的／好像类）",
    "not_a_but_b": "「不是A，而是B」式句",
    "trailing_tag": "台词用「某人说」收尾（尾随标签）",
    "quote_sandwich": "引语夹层（「……」某人说，「……」）",
    "dash_ban": "出现破折号",
    "ellipsis_misuse": "省略号出现在叙述句中",
    "halfwidth_punct": "半角标点",
    "nested_quotes": "嵌套双引号",
    "count_words_claim": "「这 N 个字」类具体字数表达——须逐字数对（人工核对）",
    "comma_period_ratio": "逗句比偏低（目标 ≥ 2.3）",
    "short_para_ratio": "极短段占比偏低（≥ 15% 为佳）",
}

# 改法建议映射（启发式：检测表现/规则命中 → 人味 7.5 战法提示；纯展示）
SUGGESTED_FIX_LABELS: dict[str, str] = {
    "monologue_dequote": "独白去引号化",
    "info_to_dialogue": "信息入对白",
    "merge_periods": "句号合并（一口气读完的动作间用逗号）",
    "delete_or_concretize": "删解释尾巴或换成具体动作",
    "thin_stacking": "削堆叠（删修饰与重复生理）",
    "rough_shorten": "糙短化（删修饰词与解释尾巴）",
}

_BLOCK = "blocking"
_ADVIS = "advisory"

# ── 正则（移植/改写自资产包 _precheck.py，去书内角色硬编码） ────────────

_VERBS = r"说|问|答|回|喊|叫|接|嘀咕|嘟囔|插|应|道|念|骂|劝|催"
_TAIL_TAG = re.compile(r"”[^”\n]{0,12}(?:我|他|她|你|老[\u4e00-\u9fa5]{1,2}|小[\u4e00-\u9fa5]{1,2}|[\u4e00-\u9fa5]{2,3})(?:又)?(?:"
                       + _VERBS + r")[。！？]")
_SANDWICH = re.compile(r"”[^\n”]{0,20}，\s*[“]")
_NOT_A_BUT_B = re.compile(r"不是[^。！？；\n]{1,24}[，,]\s*(?:而|是)")
_DASH = re.compile(r"——")
_SIMILE = re.compile(r"仿佛|似的|好像|宛如|如同|好比")
_CANNED = re.compile(r"愣了一下|愣了愣|沉默了几秒|沉默片刻|看着屏幕没说话")
_HALFWORD = re.compile(r"[\u4e00-\u9fa5][,.;:!?]|[,.;:!?][\u4e00-\u9fa5]")
_NESTED_QUOTE = re.compile(r"“[^“”\n]*“")
_COUNT_CLAIM = re.compile(r"[这那]【?一?】?[两三四五六七八九\d]{1,3}个字")


def split_paragraphs(prose: str) -> list[str]:
    """非空段列表（trim；与 zhuque.segmentation.split_paragraphs 同口径）。"""
    return [p.strip() for p in (prose or "").split("\n") if p.strip()]


def _first_word(para: str) -> str:
    """段首词：前 2 字（中文「同词起手」的自然粒度——人名/代词多为 1-2 字）。"""
    return para[:2] if len(para) >= 2 else ""


def scan_prose(prose: str) -> dict:
    """本地确定性扫描：返回 findings + 软指标（不调模型、不耗额度）。

    findings 的 para 为 0-based 非空段序；excerpt ≤ 40 字。
    """
    paras = split_paragraphs(prose)
    findings: list[dict] = []

    def add(rule: str, severity: str, para: int, excerpt: str, detail: str,
            count: int = 1, autofixable: bool = True) -> None:
        findings.append({
            "rule": rule,
            "severity": severity,
            "para": para,
            "excerpt": excerpt[:40],
            "detail": detail,
            "count": count,
            "autofixable": autofixable,
        })

    # 逐段规则
    for i, para in enumerate(paras):
        # 段内句号密度（advisory：>1 处即提示；整段 <30 字不判——短对白天然多句号）
        n_period = para.count("。")
        if n_period > 1 and len(para) >= 30:
            add("multi_period", _ADVIS, i, para,
                f"段内句号 {n_period} 处，一口气读完的动作间应逗号连缀", count=n_period)
        if _CANNED.search(para):
            add("canned_reaction", _BLOCK, i, para, "罐装反应句（愣了一下／沉默了几秒类）——给真反应或删")
        if m := _SIMILE.search(para):
            add("simile_word", _ADVIS, i, para, f"比喻词「{m.group(0)}」——生活化、角色化的比喻可留")
        if _NOT_A_BUT_B.search(para):
            add("not_a_but_b", _BLOCK, i, para, "「不是A，而是B」式句——拆对比框架，直接写B")
        if _TAIL_TAG.search(para):
            add("trailing_tag", _BLOCK, i, para, "台词用「某人说」收尾——改动作前置或裸台词")
        if _SANDWICH.search(para):
            add("quote_sandwich", _BLOCK, i, para, "引语夹层——同上归属处理")
        if _DASH.search(para):
            add("dash_ban", _BLOCK, i, para, "破折号——改逗号或句号")
        if "……" in para and para.strip() != "……":
            add("ellipsis_misuse", _ADVIS, i, para, "省略号在叙述句中——只留独立成段与引号内两种用法")
        if _HALFWORD.search(para):
            add("halfwidth_punct", _BLOCK, i, para, "半角标点——改中文全角")
        if _NESTED_QUOTE.search(para):
            add("nested_quotes", _BLOCK, i, para, "嵌套双引号——外层双引号内层单引号")
        if _COUNT_CLAIM.search(para):
            add("count_words_claim", _BLOCK, i, para,
                "具体字数表达——须逐字数对（AI 不会数数的高频硬伤）", autofixable=False)

    # 相邻段首同词（advisory；引号段落以外的一般段）
    for i in range(1, len(paras)):
        w_prev, w_cur = _first_word(paras[i - 1]), _first_word(paras[i])
        if w_prev and w_prev == w_cur:
            add("para_head_repeat", _ADVIS, i, paras[i],
                f"与上一段同以「{w_prev}」起手——改物件/动作/时间/对方起手")

    # 软指标（advisory，只展示）
    all_text = "".join(paras)
    n_comma, n_period_all = all_text.count("，"), all_text.count("。")
    comma_ratio = round(n_comma / n_period_all, 2) if n_period_all else None
    short_ratio = round(sum(1 for p in paras if len(p) <= 20) / len(paras), 2) if paras else None
    dialogue = sum(1 for p in paras if p.startswith("“") or p.startswith("「"))
    dialogue_ratio = round(dialogue / len(paras), 2) if paras else None

    metrics = {
        "comma_period_ratio": comma_ratio,
        "short_para_ratio": short_ratio,
        "dialogue_ratio": dialogue_ratio,
    }
    if comma_ratio is not None and comma_ratio < 2.3:
        add("comma_period_ratio", _ADVIS, 0, "",
            f"逗句比 {comma_ratio}（目标 ≥ 2.3）——随修稿抬升", autofixable=False)
    if short_ratio is not None and short_ratio < 0.15:
        add("short_para_ratio", _ADVIS, 0, "",
            f"极短段占比 {short_ratio:.0%}（≥ 15% 佳）——极短段只装信息句/短对白/情绪爆点",
            autofixable=False)

    return {
        "metrics": metrics,
        "findings": findings,
        "para_count": len(paras),
    }


# ── 两路来源合并（① AI 味检查的问题清单） ──────────────────────────────

_SUGGEST_BY_RULE = {
    "multi_period": "merge_periods",
    "para_head_repeat": "rough_shorten",
    "canned_reaction": "delete_or_concretize",
    "not_a_but_b": "rough_shorten",
    "trailing_tag": "rough_shorten",
    "quote_sandwich": "rough_shorten",
    "dash_ban": "rough_shorten",
    "ellipsis_misuse": "rough_shorten",
    "halfwidth_punct": "rough_shorten",
    "nested_quotes": "rough_shorten",
    "count_words_claim": "delete_or_concretize",
}


def _suggest_for(reasons: list[str], conf: float | None, para: str) -> str:
    if any("独白" in r or "引号" in r for r in reasons) and para.count("“") >= 2:
        return SUGGESTED_FIX_LABELS.get("monologue_dequote", "rough_shorten")
    if conf is not None and conf < 0.55:
        return "merge_periods"
    for r in reasons:
        for rule, sug in _SUGGEST_BY_RULE.items():
            if rule in r:
                return sug
    return "rough_shorten"


def build_problem_segments(
    paragraphs: list[str],
    report: dict,
    stored_segments: list[dict] | None,
) -> list[dict]:
    """合并两路来源（本地规则命中段＋朱雀判定段 conf≥0.5）→ 去重问题段清单。

    段序按 para_index（0-based）升序；source ∈ detector/rule/both。
    """
    rule_hits: dict[int, list[str]] = {}
    for f in report.get("findings", []):
        if f.get("para", 0) in rule_hits:
            rule_hits[f["para"]].append(f["rule"])
        else:
            rule_hits[f["para"]] = [f["rule"]]

    detector: dict[int, dict] = {}
    for seg in stored_segments or []:
        conf = float(seg.get("confidence", 0) or 0)
        if conf >= 0.5 and int(seg.get("label", 0)) >= 1:
            detector[int(seg.get("paragraph_index", 0))] = {
                "conf": conf, "label": int(seg.get("label", 0)),
            }

    out: list[dict] = []
    indexes = sorted(set(rule_hits) | set(detector))
    for idx in indexes:
        para = paragraphs[idx] if 0 <= idx < len(paragraphs) else ""
        conf = detector.get(idx, {}).get("conf")
        reasons: list[str] = []
        source_parts: list[str] = []
        if idx in detector:
            source_parts.append("detector")
            reasons.append(f"朱雀判定疑似 AI 腔 {conf:.0%}（整段指纹，无具体病灶定位）")
        if idx in rule_hits:
            source_parts.append("rule")
            for rule in rule_hits[idx]:
                reasons.append(RULE_LABELS.get(rule, rule))
        out.append({
            "para": idx,
            "text": para,
            "source": "both" if len(source_parts) == 2 else source_parts[0],
            "confidence": conf,
            "reasons": reasons,
            "suggested_fix": _suggest_for(reasons, conf, para),
        })
    return out


# ── polish 产物快扫（quick_verdict，PE 评审 E） ─────────────────────────

_REDLINE_AFTER = [
    ("dash", _DASH),
    ("halfwidth", _HALFWORD),
    ("trailing_tag", _TAIL_TAG),
    ("quote_sandwich", _SANDWICH),
    ("not_a_but_b", _NOT_A_BUT_B),
]
_BANNED_BLOCK = "block"
_BANNED_ADVIS = "advise"


def quick_verdict(before: str, after: str, banned_words: list[str] | None = None) -> dict:
    """polish 产物程序化快扫：blocking → 默认翻「保留原文」；advisory → 黄条提示。

    关键区分：结构红线只查「新增命中」（after 有而 before 无）——原文自带的
    红线项改后仍在＝存留提示（advisory），不算模型违约。
    """
    flags: list[dict] = []

    for word in banned_words or []:
        w = str(word).strip()
        if w and w in after:
            flags.append({"level": _BANNED_BLOCK, "kind": "banned_word", "detail": f"书级禁用词「{w}」"})

    for kind, rx in _REDLINE_AFTER:
        hit_b, hit_a = bool(rx.search(before or "")), bool(rx.search(after or ""))
        if hit_a and not hit_b:
            flags.append({"level": _BANNED_BLOCK, "kind": kind, "detail": f"新增{kind}（改前没有）"})
        elif hit_a and hit_b:
            flags.append({"level": _BANNED_ADVIS, "kind": kind, "detail": f"红线项未清（原文已有）：{kind}"})

    if (after or "").count("“") % 2 == 1 or (after or "").count("”") % 2 == 1:
        flags.append({"level": _BANNED_BLOCK, "kind": "quote_parity", "detail": "引号不成对"})

    lb, la = len(before or ""), len(after or "")
    if lb > 0:
        ratio = la / lb
        if ratio > 1.65:
            flags.append({"level": _BANNED_ADVIS, "kind": "length_swell", "detail": f"改后字数 +{round((ratio-1)*100)}%（疑似注水，请核对信息）"})
        elif ratio < 0.60:
            flags.append({"level": _BANNED_ADVIS, "kind": "length_shrink", "detail": f"改后字数 −{round((1-ratio)*100)}%（疑似信息丢失，请核对）"})

    digits_b = set(re.findall(r"\d+", before or ""))
    digits_a = set(re.findall(r"\d+", after or ""))
    lost = sorted(d for d in digits_b - digits_a if len(d) >= 2)
    if lost:
        flags.append({"level": _BANNED_ADVIS, "kind": "digits_changed", "detail": f"数字有出入（{', '.join(lost[:3])}），请核对"})

    return {"flags": flags, "blocking": any(f["level"] == _BANNED_BLOCK for f in flags)}
