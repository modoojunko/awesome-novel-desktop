"""人味检测引擎（c-renwei-check）：纯本地确定性体检，不调模型、不耗额度、不上传正文。

三合一单源：
- ``check_prose``：19 项指纹（对照 320 章真人基线）＋人味率（0-100%）＋修稿优先级
  ＋定位 findings（正则类到词 / 窗口类到段 / 整章密度类不定位）。
- 规则来源：原型参考实现 ``docs/design-c/drafts/check-renwei-demo.py``＋原
  ``ai_flavor_scan.py`` 的 blocking 规则（c-deai-wizard 时期收编，两套正则合并去重）。
- 段号口径：0-based 非空段序（与 zhuque.segmentation 和既有 problems 同轨）。

能力边界（写进报告文案，别越界承诺）：
- 数得出来的（标点/句长/词频/句式骨架）100% 确定性；
- 数不出来的语义层（逻辑硬伤/人物走形）归章节体检（AI），本引擎不碰。
"""
from __future__ import annotations

import math
import re

from write.renwei_baseline import (
    METRIC_BY_KEY,
    METRICS,
    MIN_MTLD_CHARS,
    MIN_RATE_CHARS,
    RATE_BANDS,
)
from write.renwei_lexicon import (
    ABSTRACT_WORDS,
    CONCRETE_WORDS,
    FUNC_CHARS,
    LOCATE_RULES,
    LONG_SENTENCE_CHARS,
    PARA_PERIOD_DENSE,
    RUN_TOLERANCE,
    SENSE_LISTS,
    TRANSITION_WORDS,
)

_PUNCT = "，。！？；…"
_SENT_SPLIT = re.compile(r"[。！？；…]+")


def split_paragraphs(prose: str) -> list[str]:
    """非空段列表（trim；与 zhuque.segmentation.split_paragraphs 同口径）。"""
    return [p.strip() for p in (prose or "").split("\n") if p.strip()]


def hanzi(s: str) -> list[str]:
    return re.findall(r"[\u4e00-\u9fff]", s)


def narration(paras: list[str]) -> str:
    """叙述文本：剥对白跨度（剥引号内内容，保留引号对作边界）。"""
    txt = "\n".join(paras)
    txt = re.sub(r"「[^」]*」", "「」", txt)
    txt = re.sub(r"“[^”]*”", "“”", txt)
    return txt


def sentences(text: str) -> list[str]:
    return [s for s in _SENT_SPLIT.split(text) if hanzi(s)]


def run_len_count(slen: list[int]) -> int:
    """句长趋同连串：连续 3 句相邻差 ≤3 字＝1 处。"""
    count = 0
    for i in range(len(slen) - 2):
        if (abs(slen[i] - slen[i + 1]) <= RUN_TOLERANCE
                and abs(slen[i + 1] - slen[i + 2]) <= RUN_TOLERANCE):
            count += 1
    return count


def mtld(tokens: list[str], threshold: float = 0.72) -> float:
    """MTLD（双向平均）＝总词数 / 因子数。

    标准 MTLD：顺序累积 token 类型比（TTR），跌破阈值（0.72）记一个因子并重置；
    双向各算一遍取平均。**返回值是「平均每个因子覆盖多少 token」，不是因子数**——
    返回因子数会把词汇丰富的文本算得比重复文本还低（实测反了）。
    """

    def one_direction(seq):
        if not seq:
            return 0.0
        factors, types, count = 1.0, set(), 0
        for t in seq:
            types.add(t)
            count += 1
            if len(types) / count <= threshold:
                factors += 1
                types, count = set(), 0
        if count > 0 and types:
            factors += (1 - len(types) / count) / (1 - threshold)
        return len(seq) / factors if factors > 0 else float(len(seq))

    return (one_direction(tokens) + one_direction(tokens[::-1])) / 2


def gap_stats(text: str) -> tuple[float, float]:
    """标点间距：相邻标点之间汉字数序列 →（均值, 偏度）。"""
    gaps, cur = [], 0
    for ch in text:
        if ch in _PUNCT:
            gaps.append(cur)
            cur = 0
        elif "\u4e00" <= ch <= "\u9fff":
            cur += 1
    if not gaps:
        return 0.0, 0.0
    n = float(len(gaps))
    mean = sum(gaps) / n
    var = sum((g - mean) ** 2 for g in gaps) / n
    sd = math.sqrt(var) if var > 0 else 0.0
    skew = sum((g - mean) ** 3 for g in gaps) / n / (sd ** 3) if sd > 0 else 0.0
    return mean, skew


def _count_abstract(text: str) -> int:
    """抽象名词：词表命中（口径校准：不加名词化后缀——无分词时后缀会误伤
    「刻度/性子/角度」，实测把密度从 2.0 抬到 5.9，破坏基线可比性）。"""
    return sum(text.count(w) for w in ABSTRACT_WORDS)


def _find_locate_rules(paras: list[str]) -> list[dict]:
    """正则类定位规则：命中即记段号＋摘录（before/hit/after 供前端高亮）。"""
    out: list[dict] = []
    for i, para in enumerate(paras):
        for rule_id, label, pattern, sev, why, fix in LOCATE_RULES:
            for m in re.finditer(pattern, para):
                start, end = m.start(), m.end()
                out.append({
                    "rule_id": rule_id,
                    "rule": label,
                    "sev": sev,
                    "para": i,                      # 0-based 非空段序
                    "before": para[max(0, start - 12):start],
                    "hit": m.group(0),
                    "after": para[end:end + 12],
                    "why": why,
                    "fix": fix,
                })
    return out


def _find_sentence_rules(paras: list[str]) -> list[dict]:
    """窗口类定位规则：句长趋同（定位到段）/单句超长/段内句号过密。"""
    out: list[dict] = []
    # 逐段切句，保留「第几句属于第几段」的映射（窗口命中回查段落）
    per_para: list[list[int]] = []
    for para in paras:
        narr_part = re.sub(r"[「“][^」”]*[」”]", "", para)
        per_para.append([len(hanzi(s)) for s in _SENT_SPLIT.split(narr_part) if hanzi(s)])

    flat: list[tuple[int, int]] = []      # (para_idx, sent_len)
    for pi, lens in enumerate(per_para):
        for ln in lens:
            flat.append((pi, ln))
    lens_only = [ln for _pi, ln in flat]
    for i in range(len(lens_only) - 2):
        if (abs(lens_only[i] - lens_only[i + 1]) <= RUN_TOLERANCE
                and abs(lens_only[i + 1] - lens_only[i + 2]) <= RUN_TOLERANCE):
            # 三句可能跨段：标给窗口中心那句所在段
            pi = flat[i + 1][0]
            if any(f["rule_id"] == "run_len" and f["para"] == pi for f in out):
                continue
            out.append({
                "rule_id": "run_len", "rule": "句长趋同连串", "sev": "warn", "para": pi,
                "before": "", "hit": f"连续 3 句句长 {lens_only[i]}/{lens_only[i + 1]}/{lens_only[i + 2]} 字", "after": "",
                "why": "连续 3 句长度几乎一样——真人句子忽长忽短，趋同是批量感指纹。",
                "fix": "拆一句、并两句或删一个子句——不加字；不要全砍短句。",
            })
    # 单句超长独立判定（不依赖 3 句窗口：一两句的文本同样要能判）
    for i, ln in enumerate(lens_only):
        if ln > LONG_SENTENCE_CHARS and not any(
                f["rule_id"] == "long_sent" and f["para"] == flat[i][0] for f in out):
            out.append({
                "rule_id": "long_sent", "rule": "单句超长", "sev": "warn", "para": flat[i][0],
                "before": "", "hit": f"单句 {ln} 字（上限 {LONG_SENTENCE_CHARS}）", "after": "",
                "why": "从句套从句是 AI 长句习惯。",
                "fix": "在语义完整的逗号处断句。",
            })
    # 相邻段首同词（ai_flavor_scan 收编；引号起手＝对白段豁免）
    for i in range(1, len(paras)):
        prev, cur = paras[i - 1][:2], paras[i][:2]
        if (prev and prev == cur
                and not paras[i - 1].startswith(("“", "「"))
                and not paras[i].startswith(("“", "「"))):
            out.append({
                "rule_id": "para_head_repeat", "rule": "相邻段首同词", "sev": "warn", "para": i,
                "before": "", "hit": f"与上一段同以「{prev}」起手", "after": "",
                "why": "连续两段同一个词起手，读起来机械。",
                "fix": "改物件/动作/时间/对方起手。",
            })
    for i, para in enumerate(paras):
        n_period = para.count("。")
        if n_period > PARA_PERIOD_DENSE and len(hanzi(para)) >= 30:
            out.append({
                "rule_id": "para_period_dense", "rule": "段内句号过密", "sev": "warn", "para": i,
                "before": "", "hit": f"本段 {n_period} 个句号", "after": "",
                "why": "一口气读完的动作之间应用逗号连缀。",
                "fix": "前几句用逗号连缀，末句落句号。",
            })
    return out


def _fmt(key: str, value):
    """展示值格式化（百分比/处/类/一位小数）。"""
    if value is None:
        return "—"
    if key in ("short_para", "dialogue", "hapax"):
        return f"{value:.1f}%"
    if key in ("run_len", "long_sent"):
        return f"{round(value)} 处"
    if key == "senses":
        return f"{int(value)} 类"
    return f"{value:.1f}"


def _p25_p75(metric: dict) -> str | None:
    if metric.get("p25") is None:
        return None
    key = metric["key"]
    a, b = metric["p25"], metric["p75"]
    if key == "senses":
        return f"{int(a)} ~ {int(b)} 类"
    if key == "run_len":
        return f"{a:.1f} ~ {b:.1f} 处"
    if key in ("short_para", "dialogue", "hapax"):
        return f"{a:.1f}% ~ {b:.1f}%"
    if key == "func_k":
        return f"{a:.0f} ~ {b:.0f}"
    return f"{a:.1f} ~ {b:.1f}"


def _passes(key: str, value) -> bool | None:
    """达标判定（None＝仅参考/样本不足）。"""
    if value is None:
        return None
    m = METRIC_BY_KEY[key]
    kind, target = m["kind"], m["target"]
    if kind == "ref" or target == "参考":
        return None
    if key == "period_k":
        return value <= 24
    if key == "ellipsis_k":
        return value >= 2
    if key == "q_k":
        return 3.0 <= value <= 6.5
    if key == "excl_k":
        return value <= 2
    if key == "gap_skew":
        return value <= 1.5
    if key == "short_para":
        return 15.0 <= value <= 40.0
    if key == "dialogue":
        return value >= 15.0
    if key == "run_len":
        return value == 0
    if key == "long_sent":
        return value == 0
    if key == "mtld":
        return value >= 60
    if key == "hapax":
        return value >= 42.0
    if key == "func_k":
        return value >= 195
    if key == "abstract_k":
        return value <= 4
    if key == "concrete_k":
        return value >= 8
    if key == "trans_k":
        return value <= 5
    if key == "senses":
        return value >= 4
    return None


def _rate_band(rate: float | None) -> dict:
    if rate is None:
        return {"band": "打不了分", "cls": "ref"}
    for floor, band, cls in RATE_BANDS:
        if rate >= floor:
            return {"band": band, "cls": cls}
    return {"band": "机器味重", "cls": "err"}


def _priorities(zs: dict[str, float]) -> list[dict]:
    """修稿优先级：计分项按 权重×|z| 降序取前 3（|z|≥1 且有该方向改法）。"""
    fixes = {
        "run_len": (None, "拆一句、并两句或删一个子句——不加字；不要全砍短句"),
        "short_para": ("把信息句独立成段；短对白单独成段", "两短段并一段"),
        "period_k": (None, "句号→逗号连缀并句；禁为降句号而乱断句"),
        "func_k": ("口语化：补「就/都/才/还/也」；检查是否文风生硬", None),
        "ellipsis_k": ("补省略号：独白犹豫处、话没说完处、时间跳跃处", "删冗余省略号"),
        "gap_skew": (None, "长短句交替；增逗号连缀长句"),
        "dialogue": ("补对话（信息轮次化——一箭双雕）", "插一段叙述"),
        "mtld": ("换词、增表达变化", None),
        "abstract_k": (None, "换具体物件：把「意义/价值/状态/过程」换成看得见的东西"),
        "trans_k": (None, "删「于是/接着/很快」，改跳跃转场"),
        "senses": ("补被忽略的感官（听/触/嗅），别只写「看」", None),
        "q_k": ("给人物一个真的疑问", "收敛自问自答"),
        "excl_k": (None, "叹号收敛，用动作和细节承载情绪"),
        "avg_sent": ("句子可以再放开一点", "句子收一收"),
        "sent_sd": ("长短句交替，别一个模子", "长短句交替，别一个模子"),
        "gap_mean": ("逗号连缀短句", "句子拆短"),
    }
    out = []
    for key, z in zs.items():
        m = METRIC_BY_KEY[key]
        if not m["weight"]:
            continue
        pair = fixes.get(key, (None, None))
        fix = pair[0] if z < 0 else pair[1]
        if fix and abs(z) >= 1.0:
            out.append({"k": m["label"], "w": m["weight"], "z": round(z, 1), "fix": fix})
    out.sort(key=lambda it: -(it["w"] * abs(it["z"])))
    return out[:3]


def check_prose(prose: str) -> dict:
    """本地人味体检：19 项指纹＋人味率＋优先级＋定位 findings（纯计算，无副作用）。

    返回：
    ``{chars, score, priorities, metrics[], findings[], paras}``
    - score.rate 为 None 时＝短章「打不了分」（chars < MIN_RATE_CHARS）
    - findings[].para 为 0-based 非空段序
    """
    paras = split_paragraphs(prose)
    full = "\n".join(paras)
    narr = narration(paras)
    hz = hanzi(full)
    n_hz = len(hz)
    n_narr = len(hanzi(narr))
    narr_slens = [len(hanzi(s)) for s in sentences(narr)]

    def per_k_full(n: int) -> float:
        return n * 1000.0 / n_hz if n_hz else 0.0

    def per_k_narr(n: int) -> float:
        return n * 1000.0 / n_narr if n_narr else 0.0

    gap_mean, gap_skew = gap_stats(narr)
    freq: dict[str, int] = {}
    for ch in hz:
        freq[ch] = freq.get(ch, 0) + 1

    avg = sum(narr_slens) / float(len(narr_slens)) if narr_slens else 0.0
    sd = (sum((n - avg) ** 2 for n in narr_slens) / len(narr_slens)) ** 0.5 if narr_slens else 0.0
    mtld_ok = n_hz >= MIN_MTLD_CHARS

    values = {
        "period_k": per_k_narr(narr.count("。")),
        "ellipsis_k": per_k_narr(narr.count("……")),
        "q_k": per_k_full(full.count("？")),
        "excl_k": per_k_full(full.count("！")),
        "gap_mean": gap_mean,
        "gap_skew": gap_skew,
        "short_para": sum(1 for p in paras if len(hanzi(p)) <= 20) * 100.0 / len(paras) if paras else 0.0,
        "dialogue": sum(1 for p in paras if p.startswith(("“", "「"))) * 100.0 / len(paras) if paras else 0.0,
        "avg_sent": avg,
        "sent_sd": sd,
        "run_len": run_len_count(narr_slens),
        "long_sent": sum(1 for n in narr_slens if n > LONG_SENTENCE_CHARS),
        "mtld": mtld(hz) if mtld_ok else None,
        "hapax": (sum(1 for c in freq.values() if c == 1) * 100.0 / len(freq)) if mtld_ok and freq else None,
        "func_k": per_k_full(sum(hz.count(ch) for ch in FUNC_CHARS)),
        "abstract_k": per_k_full(_count_abstract(full)),
        "concrete_k": per_k_full(sum(full.count(w) for w in CONCRETE_WORDS)),
        "trans_k": per_k_full(sum(full.count(w) for w in TRANSITION_WORDS)),
        "senses": sum(1 for words in SENSE_LISTS.values() if any(w in full for w in words)),
    }

    # 人味率：计分项 z 值（run_len 折千字对基线；其余同展示值），缺失项跳过重归一
    score_values = dict(values)
    score_values["run_len"] = values["run_len"] * 1000.0 / n_hz if n_hz else 0.0
    zs: dict[str, float] = {}
    num = den = 0.0
    for m in METRICS:
        if not m["weight"]:
            continue
        v = score_values[m["key"]]
        if v is None or m["mean"] is None:
            continue
        z = (v - m["mean"]) / m["sd"]
        zs[m["key"]] = z
        num += m["weight"] * 100.0 * math.exp(-(z * z) / 6.0)
        den += m["weight"]
    rate = (num / den) if (den and n_hz >= MIN_RATE_CHARS) else None
    band = _rate_band(rate)

    metrics = []
    for m in METRICS:
        key = m["key"]
        ok = _passes(key, values[key])
        metrics.append({
            "k": m["label"], "v": _fmt(key, values[key]), "t": m["target"],
            "h": _p25_p75(m) or "—", "w": m["weight"], "ok": ok,
        })

    findings = _find_locate_rules(paras) + _find_sentence_rules(paras)
    findings.sort(key=lambda f: (f["para"], f["sev"] != "err"))

    return {
        "chars": n_hz,
        "paras": len(paras),
        "score": None if rate is None else {"rate": round(rate, 1), "band": band["band"], "cls": band["cls"]},
        "priorities": _priorities(zs) if rate is not None else [],
        "metrics": metrics,
        "findings": findings,
        "short_chapter": n_hz < MIN_RATE_CHARS,
        "mtld_unconverged": not mtld_ok,
    }
