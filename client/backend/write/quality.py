import re


async def run_quality_checks(root_path: str, full_text: str) -> dict:
    # banned-words-into-style：禁用词/句式单源自文风 KV，统一迁移感知读路径
    # （存量书不进设定页直接体检也先完成迁移，不假通过）
    from settings.style_model import read_style_migrated

    style = await read_style_migrated(root_path)
    banned_words = [str(w) for w in (style.get("banned_words") or [])]
    tic_list = style.get("tic_patterns") or []

    results = {"passed": True, "checks": {}}

    # 1. Anti-AI fatigue words
    fatigue_hits = [w for w in banned_words if w in full_text]
    results["checks"]["fatigue_words"] = {
        "passed": len(fatigue_hits) == 0,
        "hits": fatigue_hits,
    }

    # 2. Forbidden sentence patterns
    pattern_hits = {}
    over_threshold = {}
    for p in tic_list:
        pt = p["pattern"] if isinstance(p, dict) else p
        try:
            matches = re.findall(pt, full_text)
        except re.error:
            # 存量毒数据兜底：非法正则跳过该项（写边界已拒绝新增，评审 P1-3）
            continue
        if matches:
            name = p.get("name", pt) if isinstance(p, dict) else pt
            pattern_hits[name] = len(matches)
            if len(matches) > p.get("threshold", 3):
                over_threshold[name] = len(matches)
    results["checks"]["structural_tic_patterns"] = {
        "passed": len(pattern_hits) == 0,
        "hits": pattern_hits,
        "over_threshold": over_threshold,
    }

    # 3. Dialogue ratio
    dialogue_chars = 0
    for m in re.finditer(r'[""“”「」]([^""“”「」]*?)[""“”「」]', full_text):
        dialogue_chars += len(m.group(1))
    total = len(full_text.replace("\n", "").replace(" ", ""))
    dialogue_ratio = dialogue_chars / total if total > 0 else 0
    results["checks"]["dialogue_ratio"] = {
        "passed": 0.05 <= dialogue_ratio <= 0.7,
        "value": round(dialogue_ratio, 3),
    }

    # 4. Description ratio
    env_hits = len(
        re.findall(
            r"(天[空气]|阳光|风|雨|雪|灯|暗|影|气味|声音|温度|寒冷|炎热|潮湿)",
            full_text,
        )
    )
    desc_estimate = env_hits * 30 / total if total > 0 else 0
    results["checks"]["description_ratio"] = {
        "passed": desc_estimate > 0.03,
        "value": round(desc_estimate, 3),
    }

    # 5. Continuity — placeholder
    results["checks"]["continuity"] = {
        "passed": True,
        "note": "skipped in v1",
    }

    # 6. 叙事自查（七条规则确定性扫描，ai-prompt-crafting 并入对照集）
    issues = run_narrative_self_check(full_text)
    results["checks"]["narrative_rules"] = {
        "passed": not issues,
        "issues": issues,
    }

    results["passed"] = all(c["passed"] for c in results["checks"].values())
    return results


# ── 叙事自查（提示性质；只做确定性可判定的规则）───────────────────────────

_SENTENCE_SPLIT = re.compile(r"[^。！？\n]+[。！？]?")

_COGNITIVE_VERBS = re.compile(
    r"意识到|感觉到|感到|察觉|注意到|意识到|发觉|心想|暗想|明白过?来?"
)
_PERCEPTION_LEAD = re.compile(r"^(他|她|它|我)(看到|听见|听到|闻到|感到|注意到|发现)")
_CAUSAL_WORDS = re.compile(r"因为|所以|由于|因此|于是")
_LABEL_WORDS = re.compile(
    r"强大的|美丽的|漂亮的|可怕的|诡异的|神秘的|惊人的|无与伦比的|难以言喻的"
)
_MARKDOWN_LEFT = re.compile(r"^#{1,6}\s|^\*\*|^\-\-\-$|^```|以下是.{0,6}(正文|本章)|本章完")
_SEQUENCE_LEAD = re.compile(r"^(然后|接着|随后|之后|这时|紧接着)")


def _sentences(full_text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.findall(full_text) if s.strip()]


def _excerpt(paragraphs: list[str], pattern: re.Pattern) -> list[str]:
    """按段落命中正则 → 原句摘录（≤3 条/规则）。"""
    hits = []
    for para in paragraphs:
        if pattern.search(para):
            hits.append(para.strip()[:60])
            if len(hits) >= 3:
                break
    return hits


def run_narrative_self_check(full_text: str) -> list[dict]:
    """七条叙事规则的确定性对照（提示性质，不阻断）。

    可判定子集：认知动词节制（>2 次/章）、先出感知信号（段首「他/她+感知动词」）、
    因果自然呈现（连接词密度）、用具体体验（泛化标签词）、写作铁律纯正文
    （Markdown/引导语残留）、叙事自然有温度（连续流水账段）。
    对话符合角色无确定性判据，由作者自查，不入扫描。
    """
    issues: list[dict] = []
    if not full_text.strip():
        return issues
    paragraphs = [p for p in full_text.split("\n") if p.strip()]

    # 1. 认知动词节制：全章 >2 次即报，附命中原句
    cognitive_hits = [s for s in _sentences(full_text) if _COGNITIVE_VERBS.search(s)]
    if len(cognitive_hits) > 2:
        issues.append(
            {
                "rule": "认知动词节制（每章 ≤2 次）",
                "excerpts": [s[:60] for s in cognitive_hits[:3]],
            }
        )

    # 2. 先出感知信号：段首直接「他/她 + 感知动词」缺前置感官信号
    perception_lead = _excerpt(paragraphs, _PERCEPTION_LEAD)
    if perception_lead:
        issues.append(
            {"rule": "先出感知信号（段首宜先给感官细节）", "excerpts": perception_lead}
        )

    # 3. 因果自然呈现：连接词 >8 次或每 200 字 >1 个即报
    causal_count = len(_CAUSAL_WORDS.findall(full_text))
    if causal_count > 8 or causal_count > len(full_text) / 200:
        causal_hits = _excerpt(paragraphs, _CAUSAL_WORDS)
        issues.append(
            {
                "rule": "因果自然呈现（因果连接词过密）",
                "excerpts": causal_hits,
            }
        )

    # 4. 用具体体验：泛化标签词直接命中
    label_hits = _excerpt(paragraphs, _LABEL_WORDS)
    if label_hits:
        issues.append({"rule": "用具体体验（泛化标签词）", "excerpts": label_hits})

    # 5. 写作铁律·纯正文：Markdown/引导语残留
    md_hits = _excerpt(paragraphs, _MARKDOWN_LEFT)
    if md_hits:
        issues.append({"rule": "写作铁律（Markdown/引导语残留）", "excerpts": md_hits})

    # 6. 叙事自然有温度：连续 ≥3 段以时序词开头（流水账）
    run = 0
    ledger_paragraphs: list[str] = []
    for para in paragraphs:
        if _SEQUENCE_LEAD.match(para.strip()):
            run += 1
            ledger_paragraphs.append(para.strip()[:60])
        else:
            if run >= 3:
                break
            run = 0
            ledger_paragraphs = []
    if run >= 3:
        issues.append(
            {
                "rule": "叙事自然有温度（连续流水账段落）",
                "excerpts": ledger_paragraphs[:3],
            }
        )

    return issues
