# Change: c-renwei-chain

## Why

用户引入外部实战文档《人味.md》（中文小说去AI味规则集，2026-10-09 版，含《夜班车》24 条实战追加与朱雀检测战法）评审仓库提示词。定诊：仓库 polish_text v5 与 write_chapter v4 本就与该文档早期版本同源（约六成已吸收——两大杠杆、六类病灶、动作重影、句号重音等），剩余增量分四块：①write_chapter 缺整个「正面写法」层（现有反AI全是禁令形状，无「该怎么做」）；②《夜班车》24 条实战新招一条未收；③检查侧无 AI 味自查（本次不动，另案）；④朱雀检测战法（本次不动，另案——待 zhuque-detection 接入时启用）。

落位策略（用户拍板）：不只改进正文两大模板，还顺「设定→卷→章→正文」上下文链向上游铺设——上游模板生成的文案（简介/题材/文风三区/角色档案/世界观/主线/卷纲/章纲）会作为上下文注入 write_chapter，上游文字自带人味 DNA，正文才有料可学、有样可学。

设计经提示词工程师代理评审（APPROVE-WITH-CHANGES，全量合入），修正四处语义冲突：①「禁全知解说」与文风三区 role 明码出售的「俯瞰全局」机位撞车→改「感知通道合法」口径（对任何机位成立）；②新节游离在「素材优先」仲裁句之外→节内立最高决策理念＋仲裁句最小扩尾，三处一次改齐；③生活碎屑在「输出契约第 2 条（不自行添加）」最高优先铁律上开洞→收窄为「唯一豁免，仅限本条」并加钉子测试守护；④settings_style 塞现成人味清单会诱导模型照抄成通用模板（违反其自身「不要通用模板」）→改「按本书前提具体化后取用 2-4 条，原样照抄＝不合格」。

用户拍板两项：write_chapter 人味节采用**分责版**（旁白/主角/配角三块归位，把「谁负责讲什么」写成决策程序——直接呼应《人味.md》三-17「人味归属判定：区别只看归属」）；节首立**人味至上**最高决策理念（笔法冲突取更有人味的写法，平手听文风三区——比机械优先级表高一层，呼应总纲「文风优先于指标，宁可破例」）。

## What Changes

- `prompts/write_chapter.prompt`（v5→v6）：「写法要求」节后新增「## 人味写法」节——开头最高决策理念两句（人味至上＋平手听文风三区＋AI 指纹红线不让步）；「每段先分清是谁在讲」总纲；旁白（禁旁白越权/感知通道合法/具名替类别与状态动作化/人物细节只给一次）＋主角（感知唯一入口/情绪有对象＋疑问链＋总结限一次）＋配角（资格两问/遮名识人＋不配全身分镜）三块归位；事实与节奏收尾（生活碎屑唯一豁免/时序物件对账）。仲裁句扩尾：「红线与『人味写法』只管‘怎么说’」。
- `prompts/polish_text.prompt`：B-E 四类病灶分号续接增补（B＋金句三公式/格言/预告句；C＋三项清单与三连排比；D＋抽象物做主语/倒译腔；E＋否定式排比/比X还Y）；六类清单末加叙述侧守门行（引号保护压过，人物嘴上套话算塑造）；正面靶子＋「最重的话最短」。全为既有 bullet 内追加，JSON 契约不变。
- 设定七族产文模板措辞注入（1-3 行/处）：settings_intro_fill（候选句具体性）、settings_intro_polish（AI 平滑句式＋金句三公式/格言收尾）、settings_genre_core_promise（看点禁抽象词）、settings_genre_battlefield（对抗面三问）、settings_style（人味写法候选池，按前提定制取用 2-4 条）、settings_characters_bootstrap/card/dossier（语言特征格三文件逐字同串＋遮名识人）、world_draft_topic（写能进正文当素材的细节＋措辞平实）、arc_draft（fullstory 只写事件链，禁主题句定调句——流入每章 system，杠杆最高）。
- 卷/章：volume_expand（summary/conflict/ending/antagonist_line 全用具体动作句，点名叙述字段防闭集字段被殃及）；chapter_split（title 优先具体动作＋物件或反差，复用模板自带教学对）。
- `sync.py` CURATED（write_chapter desc、polish_text note）＋注释头重渲染＋manifest/README 重建。
- `tests/test_templates_extra.py` 加 test_renwei_section_pins：钉人味节在位＋最高决策理念＋**碎屑豁免限定串「唯一豁免，仅限本条」**（防措辞微调把铁律口子无声放大）＋仲裁句扩尾。
- **C端零代码改动**：全部为模板静态文本注入，占位符与 JSON 输出契约零变化（world_draft_topic 的 {topic_line} 代码侧单源不动）。

### 明确不做（蓄意不吸收备案）

- 《人味.md》十一-8「大事件后主角在脑子里过一遍替读者问问题」：与输出契约第 5 条「章末落点之后一个字不留（禁反刍）」直接对冲——硬切哲学是仓库拍板，属蓄意分歧不吸收（人味节第 6 条「内心疑问链」已限定「场面内」防越界到章末）。
- 量化指标表（八）与朱雀检测适配（七）不进生成侧：数值判据（段长/逗句比/极短段占比）归 polish 与检测域，写进生成侧会与「反过度」条款及分段规则打架；朱雀战法待 zhuque-detection 实际接线时另案启用（7.6 工作流＋7.4 修稿纪律为现成模块）。
- hooks_draft 不动（「要具体到能写进正文」口径已覆盖）；volume_rules/options/pos_first、chapter_plot_draw/chapter_selfcheck/chapter_archive_extract 不动（钉子锁定或口径已足）。
- 检查侧 AI 味自查（28 问裁 ai_check kind）：另案。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `prose-writing`：「反AI结构红线注入」Requirement 增补——清单后附「人味写法」缺省笔法节（最高决策理念＋说话人分责十条）＋仲裁句扩尾；「选区变换（去AI味）」的病灶增补**不另写 delta**（该 Requirement 已有 c-polish-v5 未归档 delta，双 MODIFIED 会冲突——按其 Impact 预警，本 change 归档 sync 须在 c-polish-v5 之后，polish 增补届时并入其 Requirement 文本）。

## Impact

- `awesome-novel-prompts`：prompts/ 16 文件＋sync.py（CURATED）＋tests/test_templates_extra.py＋manifest.json/README.md（sync 生成）；pytest 50 绿（本机 /tmp venv py3.11——主库 loader 需 ≥3.10 解释器，conftest 默认 flip 检出）
- C端：无代码影响；随发布链（publish.py 切包）下次发版生效
- 无端点/前端/门禁/依赖变化；无界面改动（免原型与 Design Impact）
- 前置依赖：c-polish-v5-diagnostic-gate 未归档——两 change 触及同 Requirement（选区变换（去AI味））时按序归档（polish-v5 先）
