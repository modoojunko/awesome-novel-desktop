## 方案

### 1. 建书种子

`seed_settings_to_db` 不改机制，改模板内容：`writing-style.yaml.template` 只留 `genre_profile`/`writing_model` 两个旧字段占位＋`banned_words`/`tic_patterns`；三区键显式落空。

存量书不受影响：它们 KV 里已是旧形状，`normalize_style` 读时照常归一到三区；本 change 只影响新书。模板默认值不再「count as content」——`readiness._check_style` 仍判 `role` 非空，新书因此显示文风未完成，这是诚实结果（身份本来就该由作者写）。

### 2. 取数端点

`GET /api/novels/{project_id}/settings/style/kb-draft`（只读）：

- 读 `story.yaml` 的 `genre`（21 大类）；无题材返回 `theme: ""` ＋空数组。
- 用户条目查 `kb_entries`：`status=active`、`concept ∈ (文风, 文笔)`、`genre ∈ (本书题材, 跨题材通用)`；
- 官方基线（c-kb-baseline）走 `kb.merged.load_baseline_entries`（同题材＋跨题材通用；已排用户 hide、已套 edit 副本），与用户条目合并；
- 两类都只取基线（`when_json` 为空）；同组内用户条目在前、官方基线在后。
- 槽位映射复用 `kb/snapshot.build_members`：文风 role/sample → role/style_samples；文笔 rule/craft/banned_word/tic → rules/craft/banned_words/tic_patterns。
- 排序：同题材在前、通用在后；文本去重。`tone/pov/register` 没有书内落点，只在缺「叙事身份」时各取第一条拼一句兜底。
- 展示上限 rules 20 / craft 20 / samples 6 / banned 100 / tics 20；返回 `counts` 供右栏行与弹窗显示。

`build_members` 增补 `severity` 字段（`payload.tic_severity`），供草稿回填句式规则档次；`apply_members` 落库行为不变（仍 medium）。

### 3. 右栏行与弹窗

- `styleAiRows` 首行 `key="kb"`、`ungated: true`（不调模型 / 无 Key / 免费可用）。进文风面板时取一次摘要：有内容→「这本书是悬疑，库里有 11 条同题材的写法。点开挑一挑，采纳就填进文风页。」；无题材/库空→置灰＋hint（「先定题材」/「库是空的」）。
- 点击后 `StyleSettingForm.runAi("kb")` 取草稿：无题材/空库只 toast；有内容开 `AiCardModal`（`kind=pick`、`uiOnly`，无「换一个」）。
- 默认勾选：身份 1；硬约束前 5；手法前 3；禁用词、句式全勾；示范段不勾。组头支持全选/全不选；身份可在弹窗内直接改。
- 采纳：勾中的三区替换现有（某块一条没勾则原样不动）；护栏合并去重；写入表单不保存；`record()` 回执＋撤销；切回「文字文风」页签并 toast「已经填进文风页了，别忘了保存。」

### 4. 文案

- 面板引导语改实话；徽标改「未填 / 未改动 / 已自定义 · N 处」。
- 全部用户可见串按 `copy-must-sound-human` 口径（念出声像人话）。

## 取舍

- **不自动写**：题材保存时不碰文风；作者点按钮才填。避免「定个题材就把我写的东西改了」。
- **不在表单里放按钮**：入口只在右栏，编辑区保持零操作面（面板既有纪律：AI/辅助能力都住右栏）。
- **知识库为唯一内容源**：不维护第二份硬编码蓝图；库空就明说去哪儿补。
- **只取基线**：挂场景/情绪的条目属于写章写法块，不进默认文风。
- **示范段默认不勾**：成段原文最容易把页面撑满，作者要就自己勾。

## 风险

- 知识库空账号点按钮没有内容——已用空态文案给出「拆同题材的书 / 手录」两条出口。
- 新书 `readiness.style` 变未完成：设定进度会多一项待填；这是有意为之（身份必填）。
- 存量书不迁移：旧书打开文风页仍是 58 条旧内容，作者可随时点按钮重填（可撤销）。
