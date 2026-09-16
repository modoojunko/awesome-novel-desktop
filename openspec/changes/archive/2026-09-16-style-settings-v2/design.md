# style-settings-v2 · Design

## 评审结论落纸（P0 全收）

三路评审（前端/后端/架构师）的 P0 与本设计的对应：

| 评审 P0 | 本设计落点 |
|---|---|
| 量化层不得进 style KV（整文件覆盖回踩） | 独立 KV `style-quant`（仿 threads 专用键先例）＋专用路由；style PUT 白名单只写三区＋例句 |
| 撤并键写回会静默降级老书 | UI 撤出＋零写回；GET/PUT 边界 `normalize_style` 归一＋首次落 `_legacy_style` 留底（world v2 先例）；render 侧旧键读兼容退役 |
| 蒸馏长任务无状态机 | 三步端点（step1/2/3）＋draft 续跑（无后台任务框架，全部请求内 await，沿现役同构）；前端每步 await＋进度打勾＋面板脏守卫 |
| 蒸馏并入禁用词句竞态/结构缺口 | commit 时服务端 append 端点去重；阈值型禁令落硬约束（词表只收纯词） |
| 「AI 按剧情调节」必须可预期 | 量化基线以「约 X（±容差）＋按本章剧情在容差内自行调节」确定性渲染进提示词（同字数容差先例 chapter_writer.py:183）；章级生效可视化归写作期 change |

拍板采纳（评审推荐项）：core_principles 归一进 rules（原则多为可检查约束，宁多勿丢）＋正向描述已有 role 承载；narrator_role/tone.pov 拼入 role 尾注；tone.techniques 合并进 craft；chapter_types 退役（停注入停读取，数据保留）；pacing_rules 归一进 rules；氛围不进提示词（ADR-007 不动）；蒸馏=三步＋draft；存储=KV 免升 FORMAT_VERSION；锁定嵌合由 history 如实记录；手动微调逃生门 v1 不做。

## 数据契约

### style KV（`settings/writing-style.yaml`，经 normalize_style 归一）

归一后形状（新契约）：

```yaml
role: <str>            # 叙事身份（必填门槛）
rules: [str]           # 硬约束 3–5 条
craft: [str]           # 描写手法 ≤8 条
few_shot_examples: [str]  # ≤3
_legacy_style: {...}   # 首次归一原文（world _legacy 先例），渲染侧永不读
```

normalize_style(raw) 规则（幂等）：
- 已是新形状（含 role/rules/craft 任一新键且无旧键优先）→ 原样补默认空值
- 旧键归一：`narrator_role`/`tone.pov` 非空 → 以「；」拼进 role 尾部；`tone.techniques`/`depiction_techniques` 合并去重进 craft（复用 render 双态容忍）；`core_principles`（flatten_principles 展开）＋`possible_mistakes` 合并进 rules（去重）；`tone.default_tone/atmosphere/chapter_types` 丢弃（氛围归题材蓝图）；`pacing_rules` 进 rules
- 旧 `fatigue_words` 键保留不动（chapter_writer 现役合并源，本期不动 6.0e 过渡）

首次归一时 `merged.setdefault("_legacy_style", raw)`（原文回滚基准，后续重放不覆盖）。`read_style()` GET 边界剥离 `_legacy_style` 后返回；PUT 边界 `put_style` 校验三区类型（role str、rules/craft str list ≤ 上限）＋merge-on-save **只写白名单键**（role/rules/craft/few_shot_examples）——撤并键零写回由白名单天然保证。

### style-quant KV（`settings/style-quant.yaml`，专用键不入 PATH_TO_KEY）

```yaml
version: 1
confidence: 82        # int 1-100；缺失/0=未蒸馏
sample_chars: 7214
updated_at: 2026-09-15T12:00:00
baseline:             # 六行（渲染顺序固定）
  narrative:  {value: "第三人称限知 · 紧贴主角", tolerance: 10, locked: false}
  rhythm:     {value: {dialogue: 48, action: 24, narration: 15, environment: 7, inner: 6}, tolerance: 10, locked: true}
  syntax:     {value: "平均句长 14.6 字（短41/中38/长16/超长5）", tolerance: 10, locked: false}
  lexicon:    {value: "修饰词 8.1/百字", tolerance: 10, locked: false}
  emotion:    {value: "主通道：动作生理 58%", tolerance: 10, locked: false}
  dialogue_verb: {value: "对话 18 字/轮 · 力度 strong", tolerance: 10, locked: false}
details: {...}        # 九维全量（distilled-style-spec 键名），只读展示
portrait: "..."
history:              # 每次 commit 追加；锁定行如实记录来源
  - {at: ..., sample_chars: ..., confidence: ..., baseline: {...}, mixture: {rhythm: "v2(锁定)"}}
draft:                # 蒸馏中间态（commit 成功后清空）
  step: 3
  step1: {...}  step2: {...}  step3: {baseline: {...}, details: {...}, portrait: "...", banned: [...]}
```

六行↔九维映射（渲染合并规则，存储 details 仍逐字段）：narrative←narrative(+name_pronoun_ratio)；rhythm←rhythm；syntax←syntax+cohesion；lexicon←lexicon+rhetoric；emotion←emotion_expression；dialogue_verb←dialogue_style+verb_style。focal_character 不入文风（归角色/主线）。

## 端点契约

全部挂 `require_ai_access`＋`require_novel_model`（蒸馏）；style-quant GET/PUT 与 samples 挂登录即可（GET 免费可见空态）。

```
GET  /api/novels/{id}/settings/style            # 归一读（剥 _legacy_style）
PUT  /api/novels/{id}/settings/style            # 白名单写（role/rules/craft/few_shot_examples）＋归一
GET  /api/novels/{id}/settings/style-quant      # 全文（无则 {}）
PUT  /api/novels/{id}/settings/style-quant      # 仅 {locks: {row: bool}}；其他键忽略
GET  /api/novels/{id}/settings/style-samples    # {files:[{name,chars}], chapters:[{id,label,chars}], total, in_range}
POST /api/novels/{id}/settings/ai/style-distill/step{1,2,3}   # body {samples?}；写 draft；幂等续跑
POST /api/novels/{id}/settings/ai/style-distill/commit        # draft→正式区＋history＋anti-ai append；幂等
POST /api/novels/{id}/settings/ai/style/check         # 锚定体检（三区自洽＋与禁用词句口径对齐）
POST /api/novels/{id}/settings/ai/style/fewshot-mine  # 例句提炼（源：已归档章节）
POST /api/novels/{id}/settings/anti-ai/words          # {words:[str]} 服务端归一去重 append
```

step3 出参归一：九维键缺失给默认提示文案；禁用词候选经 `_vocab_looks_like_slug` 同类防护＋长度截断。样本字数＝去空白字符数（与 6.0e 统计口径一致）。

## 提示词组装（chapter_writer/auxiliary）

文风段（替换原 role/原则/tone/mistakes 四处）：

```
【文风】
叙事身份：{role}
硬约束：
- {rules 逐条}
描写手法：
- {craft 逐行}
【文风例句（案例段原料）】
- {few_shot 逐条}          # 原位保留
【量化基线（按约执行，可按本章剧情在容差内自行调节）】   # confidence>0 才有
- 对话占比约 48%（±10%）……（六行渲染；details 不注入）
```

`build_tone_section` 退役：删除调用点，函数保留一版周期标 deprecated（test_tone_section 同步退役/改写为归一测试）。`render.py` 新增 `style_section(style, quant)` 纯函数（可单测）。`auxiliary._format_style` 改三区。活跃伏笔 `hook_view` 加 `due_now` 派生标记（planned_chapter_id==当前章），渲染「（建议本章收束）」。

## 前端结构

- `lib/styleApi.ts`：类型（StyleQuant、StyleSamples、DistillDraft）＋请求封装（get/putLocks/samples/distillStep/commit/check/fewshotMine），unwrap 沿 hooksApi。
- `StyleSettingForm.tsx` 重写（两页签单组件）：
  - 状态：`tab: "text"|"quant"`、三区表单 state、quant（style-quant 全文）、distill 视图状态机 `idle→running(step)→portrait→committed`
  - `save()`＝PUT style 白名单 payload；`canConfirm()`＝role.trim() 非空；dirty 只由文字文风签产生（量化签全只读）
  - 页签徽标：题材默认（对比 PRESET——题材蓝图预填值）/已自定义 N 处；量化徽标 未蒸馏/置信度 N
  - 蒸馏面板：样本勾选（全选/字数合计/区间即时校验）→ 三步顺序调用（每步完成打勾，中断可续跑）→ 画像确认卡（落卡/不像再学一次）→ 回执
  - 题材预填源：GET /settings/style 返回的归一数据即预填（后端已并蓝图）；「重置为题材默认」＝前端持有 blueprint 快照恢复＋回执撤销
- `SettingsView.tsx`：文风分支接 `AiWriterAssistant` 四行（styleRef.runAi 分发，沿 runHooksAi 模式）；canConfirm 预检扩展 `panel === "style"`；面板脚 receipt（ChangeReceiptBar）；删除静态说明卡
- `FormField.tsx`：Cfg 加 `sum?: string`；ListEditor 加 `onMoveUp?`＋计数显示
- 词表：book.css settings-v 段新增（清单见 proposal）；`.settings-v .sec-label/.sl-tag` 共享类＋hk-* 保留别名

## 蒸馏三步的 LLM 契约（ai_router）

- 沿 `_judge_chat`＋`_parse_json`＋`_record_failure` 现役管线；prompt 模板进 `settings_hooks.prompt` 同族新文件 `settings_style_distill.prompt`（三步共用一个模板文件按 step 分节）
- step1（读样本逐段标注）→ 出分层标注 JSON；step2（统计）→ 出量化表 JSON（九维原始值）；step3（归纳）→ 出 `{baseline六行, details九维, portrait, banned[]}`
- 弱模型 JSON 断裂：沿现役一次重试；失败 draft 保留当前 step 允许重试
- 画像文本组装在服务端（定位声明/确认问句为固定文案模板＋LLM 产出段落拼接）

## 测试策略

- 后端 pytest：normalize_style 幂等/旧键归一/_legacy 留底/白名单零写回；style-quant GET/PUT 锁定白名单/数值忽略；samples 两路计数与区间/路径穿越拒绝；蒸馏 step 续跑/commit 幂等/anti-ai append 去重/403 门控（mock AI client，沿现役 conftest）；chapter_writer 文风段重排＋量化段注入/未蒸馏不注入/伏笔 due_now；render 兼容
- 前端 vitest：StyleSettingForm 三区保存 payload/零写回/canConfirm；页签切换；蒸馏状态机（mock styleApi）
- e2e（docker 全量栈）：settings-forms 风格用例重写（两页签/三区保存断言/量化空态）；新增 style-quant.spec.ts（蒸馏全链 mock AI：样本勾选→三步→画像确认落卡→基线渲染/锁定切换/重置撤销/确认前进）；creation-flow 种子换三区形状
- design:lint/check：新屏 parity 场景按 foreshadow 先例（若门禁覆盖面不含 settings 面板则以 design:lint＋ADJUSTMENTS 为准——以实勘 design:check 覆盖范围为准）
