# style-settings-v2

## Why

文风设定是 AI 写章提示词的最热数据源，但现行面板还是旧六组折叠卡：AI 易犯错误与「禁用词句」面板职责重叠（两边拦同一批词）、叙事基调五项与叙事身份/量化叙事维三处重复写视角、四字段与 awesome-novel 蒸馏工作流的量化层（九维）完全脱节——蒸馏（把作者认可的文章学成可执行参数）在产品里零落地。用户已多轮拍板：文风设定收敛为两部分（文字文风＝免费三区；量化参数＝PRO 蒸馏），不再选题材（题材上游已定）、不做场景卡（章节量化变化交给写章 AI 在容差内自行调节）。前端/后端/架构师三路评审已给出 P0 结论：量化层不得进现行 style KV（整文件覆盖会回踩只读基线）、撤并键必须零写回＋读时归一（否则老书静默降级）、蒸馏走三步端点＋draft 续跑、蒸馏并入禁用词句必须服务端 append。

## What Changes

- **文字文风三区**（免费，继承题材蓝图预填）：叙事身份（必填一句：镜头距离＋态度）/ 硬约束（3–5 条可检查红线；风格特有禁令也写这里，通用 AI 词句归「禁用词句」面板）/ 描写手法（题材预填删改，至多 8 条）＋ 文风例句（1–3 条选填，折叠组）
- **撤并**：`possible_mistakes`（AI 易犯错误）与叙事基调组（narrator_role/tone{...}）撤出 UI——通用反模式归禁用词句面板、基调拆进身份/手法/题材；**撤并键零写回**（merge-on-save 只覆盖仍在 UI 的键），GET/PUT 边界 `normalize_style` 读时归一＋首次归一原文落 `_legacy_style` 留底一个版本周期（world v2 先例）；`chapter_types/pacing_rules` 停止注入（chapter_types 退役、pacing_rules 归一进硬约束），题材氛围彻底退出提示词（ADR-007 口径不变）
- **量化参数（PRO 蒸馏）**：独立 KV `style-quant`（不进 style YAML，防整卡覆盖回踩）——六行基线（九维按语义合并：镜头人称/篇幅配比五层/句子段落/修饰密度/情绪外化/对话动词质感；存储仍按九维逐字段）、`details` 九维全量、confidence/sample_chars/history 版本快照；基线只读＋行级 `locked`（重蒸馏跳过），PUT 仅受理锁定切换与蒸馏 commit
- **蒸馏三步流（A3 组装审阅形）**：样本两路（项目 `novel-samples/` 目录文件＋勾选已归档章节，合计 3,000–10,000 字区间校验）→ `/ai/style-distill/step1|step2|step3` 端点串联（每步产物落 `style-quant.draft`，中断按 draft 续跑，「不像再学一次」＝重跑 step3）→ 作者画像确认卡（定位声明＋确认问句）→ `commit` 落正式区＋版本快照；confidence>0 后量化基线注入写章提示词（「约 X（±容差）执行，按本章剧情在容差内自行调节」）
- **禁用词句归口**：蒸馏学到的禁用词在 commit 时由**服务端** append 进 anti-ai 面板并去重（新端点 `POST /settings/anti-ai/words`），前端面板永不整表回写机器段；阈值型禁令（如「突然 ≤4 次/章」）落硬约束区不进词表
- **前端两页签**：文字文风 / 量化参数（`.settings-v .ptabs/.ptab`，ADJUSTMENTS 登记页签回归例外——仅面板内层级）；量化页签对免费/未蒸馏显示空态（PRO 徽＋收益一句＋去蒸馏入口），蒸馏中显示三步进度＋画像确认；右栏 AI 助手卡换四行（蒸馏我的文风/润色文字文风/锚定体检/例句提炼），编辑区零 AI 按钮（沿伏笔纪律）；确认门槛＝叙事身份非空（canConfirm 提示性预检，后端兜底）
- **消费方切换**：`chapter_writer` 文风段重排（身份→红线→手法→例句→量化基线段；删 tone 块与 mistakes 行）；`auxiliary._format_style` 同步；`render.build_tone_section` 退役（读兼容保留一个版本周期）；readiness 判据不动（role 非空）
- **伏笔小增量**：写章注入的 `hook_view` 加「建议本章收束」派生标记（`planned_chapter_id==当前章` 时渲染提示，纯派生不加列）
- 明确不做（non-goals）：场景卡/style-profiles 不落地（章节量化由写作期 AI 容差内调节）；「本章实际生效参数条」工作台 UI 归写作期 change；手动微调基线逃生门（override 记账）批后再议；蒸馏不做后台任务轮询（请求内三步端点＋draft 续跑）；跨书复制蒸馏基线不做

## Capabilities

### New Capabilities

- `style-quant`: 量化参数层契约——独立 style-quant KV、六行基线只读＋行级锁定、蒸馏三步端点（step1/2/3＋commit、draft 续跑）、样本两路与 3,000–10,000 区间校验、PRO 门控、版本快照与 history、蒸馏产物服务端并入禁用词句、量化基线注入写章提示词（约 X±容差、章内 AI 自调）

### Modified Capabilities

- `creation-flow`: 文风面板改两页签后的设定确认流（叙事身份必填门槛、确认即前进不变）；creation-flow 种子换三区形状
- `readiness`: style checker 判据不变（role 非空）但数据源经 normalize_style 归一——旧键（narrator_role/tone.pov）归一后仍判「已填」
- `prompt-crafting`: 提示词文风段重排为「身份→红线→手法→例句→量化基线」单一来源结构；tone 块与 mistakes 行退役；新增量化基线段（confidence>0 才注入）；伏笔注入补「建议本章收束」派生标记
- `design-system`: 新增 settings-v 页签词表（ptabs/ptab）、锚定块词表（fblock/fb-head/fb-no/ac-*）、基线词表（dims/dims-meta/bx-*/lock-btn/five-bar/det-row）、蒸馏词表（sample-*/dist-step/portrait/pz-*）；Cfg 组件加 sum 摘要位；ListEditor 加上移＋计数；页签回归例外登记

## Impact

- **C端后端** `client/backend`：新 `settings/style_model.py`（normalize_style/read_style/put_style 归一边界）；新 `settings/style_quant_model.py`＋`settings/style_quant_router.py`（GET/PUT 锁定/样本列表）；`settings/ai_router.py`（`/ai/style-distill/{step,commit}`、`/ai/style/{check,fewshot-mine}`、style 字段模板三区化）；`settings/router.py`（style GET/PUT 走归一边界）；`settings/render.py`（build_tone_section 退役＋三区渲染函数）；`write/chapter_writer.py`、`write/auxiliary.py`（消费方切换＋量化基线段）；`settings/anti_ai_router.py` 或 router（禁用词 append 端点）；`workflow/readiness.py`（不动判据、过归一源）；`filesystem/paths.py`（style-quant 专用键，仿 threads 先例）；测试矩阵约 25 例
- **C端前端** `client/frontend`：`lib/styleApi.ts`（新）；`components/novel/settings/StyleSettingForm.tsx` 重写为两页签（三区＋量化 tab＋蒸馏面板）；`components/novel/settings/FormField.tsx`（Cfg sum 位、ListEditor 上移/计数）；`SettingsView.tsx`（文风右栏四行 AI 轨、styleRef.runAi、canConfirm 预检扩展、receipt 接线）；`design/book.css`（词表收编＋ADJUSTMENTS 登记）；e2e `settings-forms.spec.ts` 风格用例重写＋新增 `style-quant.spec.ts`＋`creation-flow.spec.ts` 种子换形状；vitest `StyleSettingForm.fewShots.test.tsx` 更新
- **迁移**：无 schema 变更（style-quant 走 KV）；style KV 读时归一＋`_legacy_style` 留底；导出全树打包自动带上新键（免升 FORMAT_VERSION）
- **设计工件**：设计稿 `docs/design-c/drafts/ai-novel-c端-文风设定.html`（用户已终审）转正 `docs/design-c/prototypes/` 并登记 ADJUSTMENTS（含伏笔稿「已落地」标注）

## Design Impact

- 受影响端：**C端**（S端 无涉）
- 受影响屏/弹层：设定页「文风」面板（面板内两页签、右栏 AI 助手卡四行、蒸馏三步视图＋作者画像确认卡）；无新弹层（蒸馏确认在面板内，不加二次弹窗）
- 对象状态（对照状态语言总表）：页签徽标 文字文风=「题材默认」ok→「已自定义 · N 处」warn；量化=「未蒸馏」empty→「置信度 N · 容差 ±X%」acc；蒸馏三步完成态=ok；确认门槛提示沿 warnline 槽位；回执沿 accent 回执语言（持久、无 8 秒自清，对齐 ChangeReceiptBar）
- 触碰两端共享段：否（新词表为 settings-v 作用域，沿 hk-* 先例落 book.css；Cfg/ListEditor 扩展为既有组件加可选 prop，不新增平行词表）
- 原型先行：是——设计稿转正 prototypes 并登记 ADJUSTMENTS（页签回归例外＋词表映射）后再动实现
- 设计工件来源：设计侧会话（已产出，经前端/后端/架构师三路评审）
