## Why

选区加工三卡中的「场景扩写」与「压缩啰嗦段落」使用率低且职责可被整章生成/去AI味覆盖（扩写新场景＝整章生成的子集，压缩啰嗦＝去AI味的删冗余子能力）；随 AI 续写退役（#669）一并裁撤，右栏 AI 助手收敛为「生成正文＋去AI味＋朱雀检测」三个高价值动作。**去AI味（polish）保留不动**——反AI红线家族（c-polish-prompt-anti-ai）的落点。

## What Changes

- **后端**：退役 `POST /write/expand`、`POST /write/compress` 两端点＋`expand_text`/`compress_text` 函数＋`expand_text.prompt`/`compress_text.prompt` 模板；`polish_text` 与 `/write/polish` 保留；`build_auxiliary_context` 保留（polish 消费）。契约测试**新增两条反向钉缺席**（子路径清单从不含这两项，无「去清单」动作）。
- **前端**：右栏「段落加工组」三卡收编为**「去AI味」单卡**（`testid=ai-polish`，未选中置灰，三卡折叠分组头机制退役）；`onAiSelection`/`AiAction` selection mode 收窄为 `"polish"`；ProsePane `runTransform` 删 expand/compress 分支＋`ProseAIState` 的 expandLoading/compressLoading 字段＋`ProseHandle` expand/compress 方法＋preview footer「已应用扩写/压缩」分支；`lib/ai.ts` 删 `expandText`/`compressText`；`ContrastPreviewModal` mode 类型收窄；`ProseAIState.continueLoading` 死字段（#669 残留）顺手删。
- **原型**：book.html 删「场景扩写」「压缩啰嗦段落」两卡行（按卡片文案锚点定位），右栏脚注措辞同步。
- **明确不在范围**：去AI味（polish）全链；卷域 AI 的 `volumes/ai/expand`（卷纲展开）；朱雀检测。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `prose-writing`：REMOVED「选区变换（去AI味/扩写/压缩）」（三端点条款随扩写/压缩退役）＋ADDED「选区变换（去AI味）」（polish 端点与去AI味口径原样承接）。
- `workbench`：MODIFIED「右栏「AI 辅助」面板（随页签切换，动作全部落地）」——动作清单段落加工组收编为去AI味单卡（终态含 #668 解锁链口径与 #669 续写建议删除，见 design D3）；「未选段时段落动作折叠为分组行」scenario 正文改单卡置灰语义（标题为历史名，MODIFIED 同名约束下保留，design D3 注记）。
- `prompt-crafting`：MODIFIED「素材包确定性组装」——辅助链清单终态「去AI味辅助链」。

## Impact

- 后端：`write/router.py`、`write/auxiliary.py`（expand_text/compress_text）、`prompts/expand_text.prompt`/`compress_text.prompt`、`tests/test_write_transform_modes.py`（TestCompress 类删除＋docstring/AITimeoutError import 残留清理）、`tests/test_write_routes_contract.py`（反向钉）。
- 前端：`workbench/AiAssistPanel.tsx`（单卡化＋expandLoading/compressLoading props）、`workbench/ProsePane.tsx`（runTransform 分支＋ProseAIState 字段＋ProseHandle 方法＋preview footer 分支＋continueLoading 死字段）、`workbench/Rail.tsx`、`NovelWorkspace.tsx`、`lib/ai.ts`、`ContrastPreviewModal.tsx`、`__tests__/AiAssistPanel.test.tsx`（:94-136 整用例改写）＋`__tests__/NovelWorkspace.test.tsx`（:602-605 ai-para-group/ai-polish 断言改写）＋`e2e/workbench-features.spec.ts`（:680-684 折叠行断言改单卡置灰）。
- 原型：`docs/design-c/prototypes/book.html`（两卡行＋脚注，按文案锚点）；`ADJUSTMENTS.md` 退役登记；parity 基线随 design:check 重录。
- 计量：`operation=expand/compress` 历史行留存，无门禁消费。
- 归档顺序注记（design D3）：**#669 先于本 change 归档**（其 980 REMOVED+ADDED 带走主 spec 三卡折叠条款；其工件已终态化至与本 change 一致，顺序回归消除）；#668 归档位次不限（本 change 552 终态已含其解锁链口径，覆盖幂等）。
- 显式接受（P3 登记，不扩 scope）：`frontend-auth-heal` spec:116「去AI味/扩写类请求」与 `intro-genre-settings` spec:216「expand_text 须补 novel_id」两处规范文本在归档后陈旧——前者语义仍可满足（去AI味在列），后者指向已删函数的历史登记句，均随各自 change 下次触及时顺手校准。
