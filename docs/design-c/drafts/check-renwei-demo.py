#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check-renwei-demo.py —— 人味检测原型：演示文本指标计算器（数字诚实钉）。

从 src.html 的 data-rw-demo 编辑器块提取演示正文（.chapter-head 章题段不计），
按《可量化标准总表_2026-10-10》《人类样本指标参考_320章_2026-10-10》
《人味率算法与纠正指南_2026-10-10》三份文档计算 19 项指纹＋人味率，
打印可直接粘贴回 src.html RW 数据块的 JSON 片段。

--assert 模式把计算结果与 src.html 内嵌 RW 数值逐项对拍（数值容差 0.05，
百分比容差 0.5 个点，区间串逐字对拍），并校验每条 findings 摘录确为对应段落
子串、zq 演示种子各段号落在正文段数内——文案改动后忘重算会在这里红。

口径（演示约定，已在设计说明登记；实现阶段以资产包 `_人味指纹.py` 为准复核）：
  · 句号/省略号/句长三族按「叙述文本」计（剥去「…」对白跨度）——真人基线
    句号 12.4/千字与对白行 29.3% 两条基线只有在叙述口径下同时成立。问号/叹号
    按全文计（对白承载）。
  · 标点间距＝相邻两个标点（，。！？；…）之间的汉字数；均值/偏度按篇计算。
  · 人味率（《人味率算法与纠正指南》§1.1，/6 映射为准）：对计分指标
    s_i = 100·exp(−z_i²/6)，人味率 = Σ(w_i·s_i)/Σ(w_i)。权重按 §1.2 权重表：
    3＝句长连串/极短段%/句号千/虚词千；2＝省略号/间距偏度/对话行/抽象名词/MTLD
    （感官类数在伪代码中为 2，本表从 §1.2 正文表：感官仅显示——权重口径以
    设计说明拍板为准）；1＝问号/叹号/间距均值/句长均值/句长SD；
    不计分仅显示＝单句超长/Hapax/具体名词/转场词/感官类数（长度或题材敏感）。
    判读：≥70 很像人 ｜ 55-70 边缘 ｜ 40-55 偏机器 ｜ <40 机器味重。
  · 人味率只对 ≥1500 字的完整章节计算（§五.1：短片段指标天然失真，算出的分
    偏低且不可信）；不足时输出「样本不足」，只看不计分项绝对值。
  · 句长/标点三族对白剥离后按叙述文本计（同上）。
  · 词表（演示用最小真实词表，实现阶段以资产包 _人味指纹.py 全量词表替换）：
    虚词字   的了着就都也在是有和与不没这那把被让给向从对便才只还又再很
    抽象名词 问题/信任/放心/服从/选择/意义/价值/方式/过程/状态/事实/情况/
             结果/原因/目的/规矩/反应/情绪/感觉/节奏
    具体名词 门/窗/桌/烟/钥匙/碗/刀/绳/水/风（家庭与自然常物；题材专有物不入）
    转场词   于是/接着/然后/很快/后来/随即/立刻/顿时/终于/只见
    感官     视(看/盯/望/光/影/亮/暗) 听(听/声/响/沙沙/吱呀/梆)
             触(凉/热/冷/湿/麻/疼/摸/按/攥/刮/贴) 嗅(腥/臭/香/味/呛)
             味(咸/甜/苦/辣/酸)

用法：
  python3 docs/design-c/drafts/check-renwei-demo.py            # 打印计算结果与待粘贴 JSON
  python3 docs/design-c/drafts/check-renwei-demo.py --assert   # 与 src.html 内嵌值对拍
"""
import io
import json
import math
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DRAFTS = os.path.join(ROOT, "docs", "design-c", "drafts")
SRC = os.path.join(DRAFTS, "ai-novel-c端-人味检测-原型.src.html")
MIN_MTLD_CHARS = 2000
MIN_RATE_CHARS = 1500

FUNC_CHARS = "的了着就都也在是有和与不没这那把被让给向从对便才只还又再很"
ABSTRACT_WORDS = ["问题", "信任", "放心", "服从", "选择", "意义", "价值", "方式",
                  "过程", "状态", "事实", "情况", "结果", "原因", "目的", "规矩",
                  "反应", "情绪", "感觉", "节奏"]
CONCRETE_WORDS = ["门", "窗", "桌", "烟", "钥匙", "碗", "刀", "绳", "水", "风"]
TRANSITION_WORDS = ["于是", "接着", "然后", "很快", "后来", "随即", "立刻", "顿时",
                    "终于", "只见"]
SENSE_LISTS = {
    "视": ["看", "盯", "望", "光", "影", "亮", "暗"],
    "听": ["听", "声", "响", "沙沙", "吱呀", "梆"],
    "触": ["凉", "热", "冷", "湿", "麻", "疼", "摸", "按", "攥", "刮", "贴"],
    "嗅": ["腥", "臭", "香", "味", "呛"],
    "味": ["咸", "甜", "苦", "辣", "酸"],
}
PUNCT = "，。！？；…"

# 指标契约：key / 展示名 / 达标线 / 真人基线（均值, SD；None＝无基线）/
# 人类 P25-P75（人类样本指标参考_320章）/ 权重（人味率算法 §1.2；0＝不计分仅显示）
ROWS = [
    ("period_k",   "句号 / 千字",                 "≤ 24",      (12.4, 5.2),   (9.1, 11.6, 14.7), 3),
    ("ellipsis_k", "省略号 / 千字",               "≥ 2",       (17.3, 12.9),  (6.9, 16.2, 25.9), 2),
    ("q_k",        "问号 / 千字",                 "3.0 – 6.5", (4.5, 1.8),    (3.1, 4.3, 5.6),   1),
    ("excl_k",     "叹号 / 千字",                 "≤ 2",       (2.9, 2.9),    (1.2, 2.2, 3.7),   1),
    ("gap_mean",   "标点间距均值（字）",          "参考",      (8.9, 1.2),    (8.0, 8.9, 9.8),   1),
    ("gap_skew",   "标点间距偏度",               "≤ 1.5",     (0.63, 0.34),  (0.40, 0.57, 0.77), 2),
    ("short_para", "极短段占比",                 "15% – 40%", (24.4, 8.6),   (18.6, 23.6, 30.4), 3),
    ("dialogue",   "对话行占比",                 "≥ 15%",     (29.3, 12.5),  (19.6, 29.5, 38.3), 2),
    ("avg_sent",   "平均句长（字）",             "参考",      (29.6, 9.7),   (23.2, 27.9, 34.1), 1),
    ("sent_sd",    "句长 SD",                    "参考",      (29.1, 8.2),   (23.5, 27.9, 32.9), 1),
    ("run_len",    "句长趋同连串",               "0 处",      (0.42, 0.51),  (0.0, 0.33, 0.64), 3),
    ("long_sent",  "单句 > 60 字",               "0 处",      None,          None,               0),
    ("mtld",       "MTLD 词汇丰富度",            "≥ 60",      (73.8, 10.0),  (66.8, 73.2, 80.3), 2),
    ("hapax",      "Hapax 率（只出现一次的字）", "≥ 42%",     (45.2, 2.6),   (43.4, 45.2, 47.0), 0),
    ("func_k",     "虚词 / 千字",                 "≥ 195",     (208.0, 14.0), (199.0, 210.0, 219.0), 3),
    ("abstract_k", "抽象名词 / 千字",             "≤ 4",       (1.9, 1.2),    (1.0, 1.8, 2.6),   2),
    ("concrete_k", "具体名词 / 千字",             "≥ 8",       (17.2, 5.7),   (12.9, 17.0, 21.1), 0),
    ("trans_k",    "转场词 / 千字",               "≤ 5",       (3.0, 1.6),    (1.8, 2.9, 4.2),   0),
    ("senses",     "感官覆盖类数",               "≥ 4 类",    (4.6, 0.6),    (4.0, 5.0, 5.0),   0),
]
PCT_ROWS = {"short_para", "dialogue", "hapax"}
ROW_BY_KEY = {r[0]: r for r in ROWS}

# 纠正指南（§2）：按指标与方向给改法；None＝该方向无害/无动作
FIXES = {
    "run_len":    (None, "拆一句、并两句或删一个子句——不加字；不要全砍短句"),
    "short_para": ("把信息句独立成段；短对白单独成段", "两短段并一段"),
    "period_k":   (None, "句号→逗号连缀并句；禁为降句号而乱断句"),
    "func_k":     ("口语化：补「就/都/才/还/也」；检查是否文风生硬", None),
    "ellipsis_k": ("补省略号：独白犹豫处、话没说完处、时间跳跃处", "删冗余省略号（勿滥用）"),
    "gap_skew":   (None, "长短句交替；增逗号连缀长句"),
    "dialogue":   ("补对话（信息轮次化——一箭双雕）", "插一段叙述"),
    "mtld":       ("换词、增表达变化", None),
    "abstract_k": (None, "换具体物件：把「意义/价值/状态/过程」换成看得见的东西"),
    "trans_k":    (None, "删「于是/接着/很快」，改跳跃转场"),
    "senses":     ("补被忽略的感官（听/触/嗅），别只写「看」", None),
}


def read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def hanzi(s):
    return re.findall(r"[\u4e00-\u9fff]", s)


def narration(paras):
    """叙述文本：剥对白跨度（引号内容整体移除，保留引号对作边界）。"""
    txt = "\n".join(paras)
    txt = re.sub(r"「[^」]*」", "「」", txt)
    txt = re.sub(r"“[^”]*”", "“”", txt)
    return txt


def extract_chapters(src):
    """data-rw-demo 编辑器块 → {key: [para, …]}（章题段不计；保序）。"""
    out = {}
    for m in re.finditer(r'<div class="editor[^"]*" contenteditable="true" data-rw-demo="(\w+)"[^>]*>(.*?)<!-- /rw-editor -->', src, re.S):
        key, body = m.group(1), m.group(2)
        paras = []
        for pm in re.finditer(r"<p([^>]*)>(.*?)</p>", body, re.S):
            attrs, text = pm.group(1), re.sub(r"<[^>]+>", "", pm.group(2))
            if "chapter-head" in attrs:
                continue
            paras.append(text.strip())
        out[key] = paras
    return out


def sentences(text):
    """句切分：。！？；…… 为界；返回去标点汉字数列表。"""
    out = []
    for s in re.split(r"[。！？；…]+", text):
        n = len(hanzi(s))
        if n:
            out.append(n)
    return out


def run_len_count(slen):
    """句长趋同连串：连续 3 句相邻差 ≤3 字＝1 处（滑窗计数）。"""
    c = 0
    for i in range(len(slen) - 2):
        if abs(slen[i] - slen[i + 1]) <= 3 and abs(slen[i + 1] - slen[i + 2]) <= 3:
            c += 1
    return c


def mtld(tokens, threshold=0.72):
    def one_direction(seq):
        factors, types, count = 0.0, set(), 0
        for t in seq:
            types.add(t)
            count += 1
            if len(types) / count <= threshold:
                factors += 1
                types, count = set(), 0
        if count > 0:
            factors += (1 - len(types) / count) / (1 - threshold)
        return factors

    return (one_direction(tokens) + one_direction(tokens[::-1])) / 2


def gap_stats(text):
    """标点间距：相邻标点之间的汉字数序列 →（均值, 偏度）。"""
    gaps = []
    cur = 0
    for ch in text:
        if ch in PUNCT:
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


def compute(paras):
    full = "\n".join(paras)
    narr = narration(paras)
    hz = hanzi(full)
    n_hz = len(hz)
    per_k_full = lambda n: n * 1000.0 / n_hz if n_hz else 0.0
    n_narr = len(hanzi(narr))
    per_k_narr = lambda n: n * 1000.0 / n_narr if n_narr else 0.0
    narr_slen = sentences(narr)
    freq = {}
    for ch in hz:
        freq[ch] = freq.get(ch, 0) + 1
    g_mean, g_skew = gap_stats(narr)
    sd = (sum((n - sum(narr_slen) / len(narr_slen)) ** 2 for n in narr_slen) / len(narr_slen)) ** 0.5 if narr_slen else 0.0
    disp = {
        "period_k": per_k_narr(narr.count("。")),
        "ellipsis_k": per_k_narr(narr.count("……")),
        "q_k": per_k_full(full.count("？")),
        "excl_k": per_k_full(full.count("！")),
        "gap_mean": g_mean,
        "gap_skew": g_skew,
        "short_para": sum(1 for p in paras if len(hanzi(p)) <= 20) * 100.0 / len(paras),
        "dialogue": sum(1 for p in paras if p.startswith(("「", "“"))) * 100.0 / len(paras),
        "avg_sent": sum(narr_slen) / float(len(narr_slen)) if narr_slen else 0.0,
        "sent_sd": sd,
        "run_len": run_len_count(narr_slen),
        "long_sent": sum(1 for n in narr_slen if n > 60),
        "mtld": mtld(hz) if n_hz >= MIN_MTLD_CHARS else None,
        "hapax": sum(1 for c in freq.values() if c == 1) * 100.0 / len(freq) if n_hz >= MIN_MTLD_CHARS else None,
        "func_k": per_k_full(sum(hz.count(ch) for ch in FUNC_CHARS)),
        "abstract_k": per_k_full(sum(full.count(w) for w in ABSTRACT_WORDS)),
        "concrete_k": per_k_full(sum(full.count(w) for w in CONCRETE_WORDS)),
        "trans_k": per_k_full(sum(full.count(w) for w in TRANSITION_WORDS)),
        "senses": sum(1 for words in SENSE_LISTS.values() if any(w in full for w in words)),
    }
    score_raw = dict(disp)
    score_raw["run_len"] = disp["run_len"] * 1000.0 / n_hz if n_hz else 0.0
    return disp, score_raw, n_hz, narr_slen, len(paras)


def passes(key, val):
    if val is None:
        return None
    if key == "period_k":
        return val <= 24
    if key == "ellipsis_k":
        return val >= 2
    if key == "q_k":
        return 3.0 <= val <= 6.5
    if key == "excl_k":
        return val <= 2
    if key == "gap_skew":
        return val <= 1.5
    if key == "short_para":
        return 15.0 <= val <= 40.0
    if key == "dialogue":
        return val >= 15.0
    if key in ("gap_mean", "avg_sent", "sent_sd"):
        return None
    if key == "run_len":
        return val == 0
    if key == "long_sent":
        return val == 0
    if key == "mtld":
        return val >= 60
    if key == "hapax":
        return val >= 42.0
    if key == "func_k":
        return val >= 195
    if key == "abstract_k":
        return val <= 4
    if key == "concrete_k":
        return val >= 8
    if key == "trans_k":
        return val <= 5
    if key == "senses":
        return val >= 4
    raise KeyError(key)


def fmt(key, val):
    if val is None:
        return "—"
    if key in PCT_ROWS:
        return "%.1f%%" % val
    if key in ("run_len", "long_sent"):
        return "%d 处" % int(round(val))
    if key == "senses":
        return "%d 类" % int(val)
    return "%.1f" % val


def human_ref(key, p3):
    """P25–P75 展示串（落在 P25-P75＝典型人类写作）。"""
    if p3 is None:
        return "—"
    a, _m, b = p3
    if key == "senses":
        return "%d ~ %d 类" % (a, b)
    if key == "run_len":
        return "%.1f ~ %.1f 处" % (a, b)
    if key in PCT_ROWS:
        return "%.1f%% ~ %.1f%%" % (a, b)
    if key == "func_k":
        return "%.0f ~ %.0f" % (a, b)
    return "%.1f ~ %.1f" % (a, b)


def rate_band(rate):
    if rate is None:
        return {"band": "样本不足", "cls": "ref"}
    if rate >= 70:
        return {"band": "很像人", "cls": "ok"}
    if rate >= 55:
        return {"band": "边缘", "cls": "warn"}
    if rate >= 40:
        return {"band": "偏机器", "cls": "warn"}
    return {"band": "机器味重", "cls": "err"}


def human_rate(score_raw):
    """人味率（《人味率算法与纠正指南》§1.1）：Σ(w·100·exp(−z²/6))/Σw；缺失计分项跳过并重新归一。"""
    num = den = 0.0
    for key, _l, _t, base, _p, w in ROWS:
        if not w:
            continue
        v = score_raw[key]
        if v is None:
            continue
        z = (v - base[0]) / base[1]
        num += w * 100.0 * math.exp(-(z * z) / 6.0)
        den += w
    return (num / den if den else None), {k: (score_raw[k] - b[0]) / b[1]
                                         for k, _l, _t, b, _p, w in ROWS if w and score_raw[k] is not None}


def priorities(zs):
    """修稿优先级：计分项按 w×|z| 降序，取 |z|≥1 且该方向有改法的前 3 项。"""
    out = []
    for key, _l, _t, _b, _p, w in ROWS:
        if not w or key not in zs:
            continue
        z = zs[key]
        fix = FIXES.get(key, (None, None))
        fix = fix[0] if z < 0 else fix[1]
        if fix and abs(z) >= 1.0:
            out.append({"k": ROW_BY_KEY[key][1], "w": w, "z": round(z, 1), "fix": fix})
    out.sort(key=lambda it: -(it["w"] * abs(it["z"])))
    return out[:3]


def to_float(s):
    return float(re.sub(r"[^0-9.]", "", str(s)))


def main():
    assert_mode = "--assert" in sys.argv
    src = read(SRC)
    chapters = extract_chapters(src)
    assert chapters, "no data-rw-demo editor blocks found in src"

    rw_m = re.search(r"var RW = (\{.*?\});\n</script>", src, re.S)
    rw = json.loads(rw_m.group(1)) if rw_m else None

    report, calc, fails = {}, {}, []
    for key in sorted(chapters):
        paras = chapters[key]
        disp, score_raw, n_hz, slen, n_paras = compute(paras)
        rate, zs = human_rate(score_raw)
        band = rate_band(rate)
        calc[key] = {"paras": paras, "disp": disp, "n_hz": n_hz, "n_paras": n_paras,
                     "rate": rate, "zs": zs, "band": band}
        print("== %s · 正文 %d 字 · %d 段 · 叙述 %d 句 · 最长叙述句 %d 字 ==" % (key, n_hz, n_paras, len(slen), max(slen)))
        metrics = []
        for rkey, label, target, base, p3, w in ROWS:
            ok = passes(rkey, disp[rkey])
            m = {"k": label, "v": fmt(rkey, disp[rkey]), "t": target,
                 "h": human_ref(rkey, p3), "w": w, "ok": ok}
            metrics.append(m)
            mark = {True: "✓", False: "⚠", None: "·"}[ok]
            print("   %s %-24s %9s  达标线 %-8s 权 %s" % (mark, label, m["v"], target, w))
        prio = priorities(zs) if rate is not None else []
        if rate is not None:
            print("   → 人味率 %.1f%% · %s（%s）" % (rate, band["band"], band["cls"]))
            for p in prio:
                print("     优先修 %s（权 %d，z %+.1f）：%s" % (p["k"], p["w"], p["z"], p["fix"]))
        else:
            print("   → 人味率 样本不足（< %d 字，只看不计分项绝对值）" % MIN_RATE_CHARS)
        print()
        report[key] = {"chars": n_hz,
                       "score": (None if rate is None else
                                 {"rate": round(rate, 1), "band": band["band"], "cls": band["cls"]}),
                       "priorities": prio, "metrics": metrics}

    if assert_mode:
        assert rw, "var RW block not found in src"
        for key in sorted(chapters):
            c, emb = calc[key], rw["chapters"][key]
            if emb["chars"] != c["n_hz"]:
                fails.append("%s chars: src=%s calc=%s" % (key, emb["chars"], c["n_hz"]))
            if c["rate"] is None:
                if emb["score"] is not None:
                    fails.append("%s score 应为样本不足" % key)
            else:
                if emb["score"] is None:
                    fails.append("%s score 缺失" % key)
                elif emb["score"]["band"] != c["band"]["band"] or abs(emb["score"]["rate"] - round(c["rate"], 1)) > 0.05:
                    fails.append("%s score: src=(%s,%s) calc=(%.1f,%s)" % (key, emb["score"]["rate"], emb["score"]["band"], c["rate"], c["band"]["band"]))
                got_prio = emb.get("priorities", [])
                if [p["k"] for p in got_prio] != [p["k"] for p in report[key]["priorities"]]:
                    fails.append("%s priorities 漂移: src=%s calc=%s" % (key, [p["k"] for p in got_prio], [p["k"] for p in report[key]["priorities"]]))
            for got, (rkey, label, _t, _b, p3, _w) in zip(emb["metrics"], ROWS):
                if got["k"] != label:
                    fails.append("%s 指标名漂移: %s vs %s" % (key, got["k"], label))
                    continue
                if got["h"] != human_ref(rkey, p3):
                    fails.append("%s %s 真人区间漂移: src=%s calc=%s" % (key, got["k"], got["h"], human_ref(rkey, p3)))
                    continue
                if got["w"] != ROW_BY_KEY[rkey][5]:
                    fails.append("%s %s 权重漂移: src=%s" % (key, got["k"], got["w"]))
                want = fmt(rkey, c["disp"][rkey])
                if want == "—":
                    if got["v"] != "—":
                        fails.append("%s %s: src=%s calc=样本不足" % (key, got["k"], got["v"]))
                elif abs(to_float(got["v"]) - to_float(want)) > (0.5 if rkey in PCT_ROWS else 0.05):
                    fails.append("%s %s: src=%s calc=%s" % (key, got["k"], got["v"], want))
                if got["ok"] != passes(rkey, c["disp"][rkey]):
                    fails.append("%s %s ok: src=%s calc=%s" % (key, got["k"], got["ok"], passes(rkey, c["disp"][rkey])))
            for f in emb.get("findings", []):
                idx = f["para"] - 1
                if not (0 <= idx < c["n_paras"]):
                    fails.append("%s finding 段号越界: 段%d" % (key, f["para"]))
                    continue
                excerpt = f["before"] + f["hit"] + f["after"]
                if excerpt and excerpt not in c["paras"][idx]:
                    fails.append("%s finding 摘录不在段%d: %r" % (key, f["para"], excerpt[:24]))
        for p in rw["zqSeed"]["ch14"]:
            if not (1 <= p["para"] <= calc["ch14"]["n_paras"]):
                fails.append("zq 种子段号越界: 段%d" % p["para"])
        if fails:
            print("ASSERT FAIL ×%d：" % len(fails))
            for f in fails:
                print("  ✗ " + f)
            sys.exit(1)
        print("ASSERT PASS：src.html 内嵌数值与计算一致；摘录/段号/zq 种子校验通过。")
    else:
        print("── 待粘贴 JSON（chars/score/priorities/metrics；labels 以本脚本契约为准）──")
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
