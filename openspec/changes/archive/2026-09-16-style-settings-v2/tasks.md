# style-settings-v2 · Tasks

> 三批切片：§1–§2＝批1 免费基座（归一＋三区表单）；§3–§5＝批2 蒸馏 PRO；§6＝批3 闭环＋伏笔增量；§7–§8＝e2e 与验收；§9 收尾。每批独立可交付。

## 1. 词表与归一边界（批1）

- [x] 1.1 新建 `client/backend/settings/style_model.py`：normalize_style（幂等，旧键 narrator_role/tone.pov→role 尾注、tone.techniques+depiction_techniques→craft、core_principles+possible_mistakes→rules 去重、pacing_rules→rules、chapter_types/tone.default_tone/atmosphere 丢弃）、read_style（剥 _legacy_style）、put_style（白名单 role/rules/craft/few_shot_examples＋类型长度校验）；单测：幂等/旧键归一/首次 _legacy_style 留底/白名单零写回/类型校验
- [x] 1.2 `settings/router.py` GET/PUT style 接入归一边界；GET 剥 `_legacy_style`；PUT 首次归一落底；test_db_storage 键集合与既有 settings 用例更新
- [x] 1.3 `filesystem/paths.py` 加 STYLE_QUANT 键（仿 THREADS 先例，不入 PATH_TO_KEY）；init 种子不动

## 2. 文风面板重写（批1）

- [x] 2.1 原型转正：`docs/design-c/drafts/ai-novel-c端-文风设定.html` → `docs/design-c/prototypes/style-settings.html`；ADJUSTMENTS 登记（ptabs 页签回归例外、词表映射、hk-sec-label→共享 sec-label、死词表不入库）；伏笔稿头部加「已落地（对应 archive/2026-09-15-foreshadow-settings-v2）」标注
- [x] 2.2 `FormField.tsx`：Cfg 加 `sum` 摘要位；ListEditor 加可选 `onMoveUp` 与 x/y 计数；book.css settings-v 段收编新词表（ptabs/fblock/anchor-chain/dims 家族/sample 家族/dist-step/portrait 家族）＋`.settings-v .sec-label/.sl-tag` 共享类；design:lint 通过
- [x] 2.3 `lib/styleApi.ts`：类型＋请求封装（get/putLocks/samples/distillStep/commit/check/fewshotMine），unwrap 沿 hooksApi；tsc 通过
- [x] 2.4 重写 `StyleSettingForm.tsx`：两页签（data-od-id 对齐原型）；文字文风签三区＋例句折叠（sum 摘要）；页签徽标 题材默认/已自定义 N 处；量化签三态（空态/蒸馏中/已蒸馏基线）；锁定切换 aria-pressed；保存 PUT 白名单 payload；save/canConfirm/markDirty 全契约；vitest：payload 白名单/零写回/canConfirm/页签切换/徽标
- [x] 2.5 `SettingsView.tsx`：文风分支接右栏四行 AI 轨（蒸馏/润色/锚定体检/例句提炼，styleRef.runAi 沿 runHooksAi）；canConfirm 预检扩展 style；面板脚 receipt 接 ChangeReceiptBar；确认门槛 warnline 槽位；删除静态说明卡；settings-forms「风格」用例重写（两页签/三区保存/量化空态）
- [x] 2.6 批1 验收：容器 pytest 全量绿、tsc 绿、vitest 绿、design:lint 绿

## 3. 蒸馏端点（批2）

- [x] 3.1 `settings/style_quant_model.py`＋`settings/style_quant_router.py`：GET 全文/PUT 仅 locks（数值忽略）；路由注册先于 /settings/{type} 兜底；单测：锁定切换/数值忽略/未蒸馏返回 {}
- [x] 3.2 `GET /settings/style-samples`：novel-samples/ 两扩展名列表＋已归档章节，去空白字数、合计、区间判定、路径穿越拒绝；单测：两路混合/不足 3000/超 10000/穿越拒绝
- [x] 3.3 `settings_style_distill.prompt` 模板（step1/2/3 分节）＋`ai_router` 三步端点：样本装配→_judge_chat→JSON 归一→写 draft（step 标记）；续跑（draft 已完成步骤跳过）；step3 出参归一（六行 baseline/details 九维/portrait 固定文案拼接/banned 候选防护）；单测（mock AI）：三步顺序/draft 续跑/step3 重跑/JSON 断裂重试
- [x] 3.4 `commit` 端点：draft→正式区＋history 追加（锁定行 mixture 记录）＋confidence/sample_chars/updated_at＋draft 清空＋幂等；禁用词候选服务端 append（`POST /settings/anti-ai/words`，归一去重）；403 门控用例（免费全端点）
- [x] 3.5 `POST /ai/style/check`（三区自洽＋禁用词句口径对齐，D7 降级）与 `/ai/style/fewshot-mine`（已归档章节提炼）；`/ai/style/{field}` 模板三区化；单测

## 4. 消费方切换（批2）

- [x] 4.1 `render.py`：新增 style_section 三区渲染＋quant_section（confidence>0、容差分档、约X±容差）；build_tone_section 标 deprecated；test_tone_section 改写为归一/退役断言
- [x] 4.2 `chapter_writer.py`：文风段重排（身份→红线→手法→例句→量化段）；读 style 经归一源；`auxiliary._format_style` 三区；test_chapter_writer_context 更新（三区注入/量化段注入/未蒸馏不注入/旧键归一后内容不丢）
- [x] 4.3 `prompt/context.py`：hook_view 加 due_now 派生标记＋渲染「（建议本章收束）」；test_hooks_consumers 增断言

## 5. 批2 验收

- [x] 5.1 容器 pytest 全量绿；tsc/vitest 绿

## 6. e2e（批3）

- [x] 6.1 新增 `e2e/style-quant.spec.ts`（mock AI）：样本勾选与区间提示→三步进度→画像确认落卡→基线六行渲染→锁定切换→重新蒸馏锁定行保留→重置撤销→免费 403 空态
- [x] 6.2 `creation-flow.spec.ts` 文风种子/流程换三区形状；settings-forms 既有断言全绿
- [x] 6.3 本地 docker 栈 e2e 全量绿（含 foreshadow 回归）

## 7. 收尾

- [x] 7.1 openspec validate 通过；proposal/tasks/specs 与实现对拍
- [x] 7.2 PR：描述含评审结论落纸表；self-review 逐条核对评审 P0/P1 清单
- [x] 7.3 PR 评审意见修复至合入
