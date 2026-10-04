## 1. 后端退役

- [x] 1.1 删 `POST /write/expand`、`POST /write/compress` 端点（write/router.py:520/:457，含 import）与 `expand_text`（auxiliary.py:213）/`compress_text`（:178）；`expand_text.prompt`/`compress_text.prompt` 整文件删除；`polish_text`/`/write/polish`/`build_auxiliary_context` 不动；模块 docstring「continue, polish, and expand」等残留顺手清。验证：`grep -rE "expand_text|compress_text" client/backend --include="*.py" --include="*.prompt"` 零残留；pytest 全量绿
- [x] 1.2 `tests/test_write_transform_modes.py`：TestCompress 类（3 用例）删除＋模块 docstring 去「/write/compress」＋`AITimeoutError` import 随超时用例清理（TestPolish 保留）；`tests/test_write_routes_contract.py` 照 `test_continue_route_retired` 形制**新增两条反向钉**（`/compress`、`/expand` not in openapi_paths——sibling 清单从不含两项，无「去清单」动作）。验证：两测试文件绿
- [x] 1.3 ruff CI 同参复核（`--extend-select F811,F821,F841`）全绿

## 2. 前端退役

- [x] 2.1 AiAssistPanel 段落加工组单卡化：删场景扩写/压缩两卡与 `ai-para-group` 折叠分组行，去AI味单卡 `testid=ai-polish`（未选中置灰＋「先在正文选中一段」hint）；`expandLoading`/`compressLoading` props 删；说明行/脚注去「扩写/压缩」。验证：`grep -rE "场景扩写|压缩啰嗦|expandLoading|compressLoading|ai-para-group|段落加工" client/frontend/src` 零残留
- [x] 2.2 ProsePane：`runTransform` 删 expand/compress 分支；`ProseAIState` 与 INITIAL 常量的 expandLoading/compressLoading 字段删（:50-66）；`ProseHandle` expand/compress 方法与 useImperativeHandle 包装删（:77-79/:672-673）；preview footer「已应用扩写/压缩」分支删（:867-871）；`ProseAIState.continueLoading` 死字段（#669 残留）顺手删。Rail `onAiSelection` mode 类型、NovelWorkspace `AiAction` selection mode 收窄 `"polish"`。验证：tsc 零错
- [x] 2.3 `lib/ai.ts` 删 `compressText`（:186）/`expandText`（:200）；`ContrastPreviewModal` mode 类型收窄（「扩写后/压缩后」分支删）。验证：`grep -rE "expandText|compressText" client/frontend/src` 零残留
- [x] 2.4 单测改写：`__tests__/AiAssistPanel.test.tsx:94-136` 整用例（未选中态去AI味置灰断言、压缩卡两段→去AI味 onAiSelection("polish")）；`__tests__/NovelWorkspace.test.tsx:602-605`（ai-para-group 存在断言删、ai-polish null→置灰存在、场景扩写 null 保留）。验证：vitest 全量绿
- [x] 2.5 原型同步（按文案锚点，行号已漂移勿照抄）：`docs/design-c/prototypes/book.html` 删「场景扩写」「压缩啰嗦段落」两卡行与脚注「扩写/压缩」字样；`ADJUSTMENTS.md` 追加退役登记；`e2e/design-parity-book.spec.ts:245` 注释「扩写」顺手清。验证：grep 原型零残留
- [x] 2.6 e2e 必红断言改写：`e2e/workbench-features.spec.ts:680-684` 折叠行断言（ai-para-group disabled＋ai-polish count 0）改为单卡置灰断言（与 2.1 同批落地，勿留到 e2e 阶段爆）。验证：该 spec 局部绿
- [x] 2.7 #669 工件终态化（评审落地项复核）：其 workbench 552 块/ADDED 密度重排块/prompt-crafting 块已按 D3 修订——提交前 `openspec validate c-retire-continue-writing` 复核绿

## 3. 全量验证

- [x] 3.1 后端 pytest 全量＋前端 vitest 全量＋tsc＋ruff 全绿
- [x] 3.2 零残留自证（**必须 `grep -E`**，BSD grep 字面 `|` 假绿）：`grep -rEn "场景扩写|压缩啰嗦|expandText|compressText|expandLoading|compressLoading|ai-para-group|段落加工" client/frontend/src client/frontend/e2e docs/design-c/prototypes/book.html` 零命中（保留面白名单：卷域 `volumes/ai/expand`、`desk-expand` 事件、creation-flow:315 的正向缺席断言）；e2e 全量复跑与 parity 基线重录留待常规环境（#669 同判例）；归档顺序硬约束复核：#669 归档 PR 先于本 change（D3）
