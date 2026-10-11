# 修稿向导 · 用户旅程 × 阶段数据 IO 设计

> 版本 v2 终版（2026-10-10 拍板收敛）· 配套原型：`docs/design-c/drafts/ai-novel-c端-修稿工作流-原型.html`
> v2 收敛记录：阶段①定名「AI 味检查」、②定名「选择段落」（2026-10-10 用户拍板——①查问题出清单、②在清单上勾选；「预检」「热片」为遗留/内部术语，UI 不出现）；① 逐段复测废弃（额度与切段抖动考量）→ 攒批闭环；② 「⑤ 向导内整章复测」整步废弃——应用后走页面顶栏**现成朱雀条**的重检收口（stale 机制已有）；③ 复测/回滚编排（原 §5）随之删除。
> 前提口径：朱雀检测已完成（结果已落库存档）；`/write/polish` 与正文保存链为现成端点；AI 味检查规则移植自资产包 `_precheck.py`。

---

## 0. 全旅程一屏

```
[前置] 朱雀检测完成（存档在手，正文标注态）
   └→ 作家点右栏「去 AI 味」→ 弹窗向导
①AI味检查(本地规则+读检测存档,0额度) → ②选择段落(在问题清单上勾选) → ③整体修改·逐段取舍(每段1次polish,0检测额度)
   → ④应用(一次写回) → 弹窗收尾
[收口] 顶栏朱雀条自动置 stale（正文已修改）→ 作家自己点「重检」→ 回到[前置]，可再来一轮
```

数据主权：向导内一切为**候选态**，唯一写正文口＝④「应用到正文」（作家按键）；复测与否、何时测，全在向导外的现成朱雀条。

---

## 1. 阶段 × 数据 IO 总表

| 阶段 | 触发 | 输入 | 处理者 | 输出 | 花费 | 写正文? |
|---|---|---|---|---|---|---|
| ① AI 味检查 | 进入向导自动跑 | 本章正文文本（编辑器内存态，flush 后） | **新** `POST /ai-flavor-scan`（纯函数） | `AiFlavorScanReport`（机器项清单＋软指标） | 0 | 否 |
| ② 选择段落 | 作家在清单上勾选 | ①的合并问题清单（本地条目＋朱雀段落） | 前端交互 | 勾选态（进③改写队列的段集合） | 0 | 否 |
| ③ 整体修改·逐段取舍 | 作家逐段点「生成改后」 | 单段原文（②勾选队列中的段） | 现成 `/write/polish`（单段选区） | 该段候选改后文本（before/after 对照） | 每段 1 次模型 | 否（候选态） |
| ④ 应用 | 作家点「应用到正文」 | 逐段取舍结果 | 现成保存链 | 采用段写回；旧检测置 stale；弹窗收尾 | 0 | **是**（唯一写口） |
| [收口] 重检 | 作家自点顶栏「重检」 | 落盘正文 | 现成 `zhuque-check` | 新存档＋新标注；不满意可再来一轮向导 | 1 检测额度 | 否 |

废弃记录：~~③.5 逐段复测~~（每段 1 额度＋切段抖动不可靠）、~~⑤ 向导内整章复测~~（与顶栏朱雀条重号）。

---

## 2. 核心数据结构（两个对象贯穿；v2 瘦身）

### 2.1 `AiFlavorScanReport`（① 输出；原 PrecheckReport 随阶段定名改）

```jsonc
{
  "chapter_ref": "vol-1-ch-6",
  "prose_fingerprint": "sha256:…",      // 与检测存档 prose_hash 同算法——判断扫描新鲜度
  "word_count_platform": 1180,
  "issues": [
    {
      "rule": "period_density",         // 规则 id（§3 清单）
      "severity": "blocking" | "advisory",
      "para": 6,
      "excerpt": "水银柱停在一个活人…",  // ≤40 字
      "detail": "段内句号 6 处，一口气读完的动作间应逗号连缀",
      "count": 6
    }
  ],
  "metrics": {                          // 软指标（只展示不拦截）
    "comma_period_ratio": 2.1,
    "short_para_ratio": 0.09,
    "dialogue_ratio": 0.31,
    "metaphor_density": 0.0
  }
}
```

### 2.2 问题清单与勾选（①产出、②消费）

①的输出在 UI 层合并为一张清单：本地规则条目（段级聚合）＋朱雀 conf≥0.5 段落（带百分比），统一字段：段号/摘要/来源（文字层规则｜朱雀判定）/原因一句话。②＝这张清单上的勾选交互（默认全选），勾选结果即③改写队列。「热片」为内部术语（代码/数据层 hotspot），UI 不出现。

### 2.3 `FixCandidate`（③ 每段候选——v2 取代 FixAttempt）

```jsonc
{
  "id": "cand-001",
  "para": 2,
  "source": "detector" | "rule",        // 朱雀判定的段还是本地规则命中的段
  "before": "掌心贴上砖墙，…（段原文）",
  "after": "掌心贴上砖墙，…（polish 产物）",
  "verdict": "accept" | "keep_original" // 作家逐段取舍，默认 accept；keep_original＝应用时写回 before
}
```

~~FixAttempt.retest/verdict(keep|rollback)~~ 随逐段复测废弃；~~RoundSnapshot~~ 随向导内复测废弃（应用前正文从未变过，无需整轮快照——「回滚」即把某段 verdict 切回 keep_original）。

---

## 3. AI 味检查规则清单（移植 `_precheck.py` + 补两条）

| rule id | 内容 | 来源 | severity | 进③改写队列 |
|---|---|---|---|---|
| `trailing_tag` | 尾随标签 | 资产包 HARD | blocking | 是 |
| `quote_sandwich` | 引语夹层（三变体） | 资产包 HARD | blocking | 是 |
| `not_a_but_b` | 不是A是B 全变体 | 资产包 HARD | blocking | 是 |
| `dash_ban` | 破折号 | 资产包 HARD | blocking | 是 |
| `ellipsis_misuse` | 省略号两用法之外 | 资产包 HARD | blocking | 是 |
| `halfwidth_punct` | 半角标点 | 资产包 HARD | blocking | 是 |
| `nested_quotes` | 嵌套双引号 | 资产包 HARD | blocking | 是 |
| `bare_line` | 叙述碎句行 | 资产包 HARD | blocking | 是 |
| `count_words_claim` | 「这五个字」逐字数对 | 资产包 HARD | blocking | **否**（事实错须人工） |
| `metaphor_words` | 比喻词表 | 资产包 HARD* | advisory（建议，见拍板） | 是 |
| `word_count_band` | 字数带（书级 word_target） | 资产包改书级口径 | advisory | 否 |
| `para_start_repeat` | **补**相邻段首同词（引号占位后扫段首） | 人味二-12 | advisory | 是 |
| `period_density` | **补**段内句号 >1 | 人味二-11 | advisory | 是 |
| `comma_period_ratio` | 逗句比 <2.3 | 资产包软指标 | advisory | 否（整体指标） |
| `short_para_ratio` | 极短段占比 <15% | 资产包（判别力最强条） | advisory | 否（整体指标） |
| `outline_overlap` | 细纲照搬→二期（对剧情条目重合检测） | 资产包 | — | — |

---

## 4. 病灶 → 改法建议映射（② 清单行展示用，纯提示不喂模型）

| 清单行表现 | 建议 id | 人味出处 |
|---|---|---|
| 引号独白密集成片 | `monologue_dequote` 独白去引号化 | 7.3 杠杆二 |
| 干叙述＋有可开口人物 | `info_to_dialogue` 信息入对白 | 7.3 杠杆一 |
| 段内句号密/碎句 | `merge_periods` 句号→逗号 | 7.5-15 |
| 罐装反应/解释尾巴 | `delete_or_concretize` | 7.5-10 |
| 温柔堆叠/环境流排比 | `thin_stacking` | 7.5-13/12 |
| 通用 | `rough_shorten` 糙短化四件套 | 7.5-7 |

映射为启发式（段文本特征＋AI 味检查命中推断），只影响提示文案，不影响 polish 自身诊断。

---

## 5. ③ 的编排细节（整体修改·逐段取舍）

```
进入③：改写队列 = ②勾选的段（朱雀判定段＋机器项段已在①合并去重）
逐段：
  作家点「生成改后」 → polish(该段) → FixCandidate（before/after 展示）
  作家当场取舍：verdict = accept（默认）/ keep_original（不满意可点「重新生成」再花 1 次模型）
全部段处理完 → 「应用到正文」激活
④ 应用：
  对每个 accept 段写回 after；keep_original 段不动
  （实质＝一次整章保存：候选段替换后走现有保存链）
  → 旧检测自动置 stale；弹窗收尾；toast「正文已更新，建议重检一次」
```

- **弹窗中途关闭**：候选全弃，正文一字未动（全程候选态，无部分写回风险）。
- **重新生成**：同段可再来（每次数 1 次模型调用）；不设硬上限，UI 显示本次会话已用次数。
- **额度账**：向导内 0 检测额度；检测额度只在作家点顶栏「重检」时消耗（月度台账既有口径）。
- **正文长度**：应用后超 `MAX_PROSE_CHARS` 时按检测既有口径提示（极端情况，polish 净删为主不太会超）。

---

## 6. 对照取舍（并入 ③ 展示，v2 无独立④ diff 视图）

- 逐段 before/after 即对照（左原文右润色，段级）；
- 每段 verdict 开关即取舍；应用后如需「反悔」，正文编辑器本身就是回退工具（版本历史现成）；
- 字级 diff 高亮为二期增强，一期整段对照够用。

---

## 7. 端点清单（净新增 vs 复用）

| 端点 | 状态 | 说明 |
|---|---|---|
| `POST /api/novels/{id}/chapters/{ref}/ai-flavor-scan` | **新增** | 正文服务端读章；出参 `AiFlavorScanReport`。判据单源模块 `write/ai_flavor_scan.py`（CLI/测试共用） |
| `GET …/zhuque-result` | 复用 | ② 读存档 |
| `POST …/write/polish` | 复用 | ③ 逐段候选生成（不改接口；改法建议只展示不喂） |
| 正文保存链 | 复用 | ④ 唯一写口 |
| `POST …/zhuque-check` | 复用（向导外） | 收口重检＝顶栏朱雀条既有动作 |
| 向导会话态 | **前端持有** | `FixCandidate[]` 不落库，关弹窗即弃 |

---

## 8. 剩余待拍板（收敛后仅两点）

1. **比喻词 severity**：资产包升了 HARD；产品建议 advisory（书级文风可配「允许生活化比喻」）。定哪个？
2. **改法建议 `hint` 是否喂给 polish**：一期建议不喂（只展示）；观察 polish v7 诊断精度后二期再定。

（原「逐段复测免不免」「向导内整章测」两项已随架构废弃，不再需要拍。）
