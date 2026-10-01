## 1. 原型先行（硬性流程）

- [x] 1.1 `book.html` 右栏章选卡：「AI 帮写剧情」行改名「剧情抽卡」，行序调整为 剧情抽卡①／盘点出场人物②／剧情推演③／补全缺失字段④／与卷纲冲突检测⑤；ADJUSTMENTS.md 追加登记小节。验证：grep 原型无「AI 帮写剧情」。

## 2. 实现

- [x] 2.1 `AiAssistPanel.tsx`：`cap("plot-draw", ...)` 行名改「剧情抽卡」，rows 数组重排（plot-draw→cast-review→simulate→fill→conflict）。验证：tsc 干净。
- [x] 2.2 注释同步：`Rail.tsx`（透传注释）、`ChapterWorkspace.tsx`（479/642 两处）、`aiAssistPanel.plotTool.test.tsx` 头注释、`e2e/plot.spec.ts:8` 头注释。验证：grep src/e2e 无「AI 帮写剧情」。

## 3. 测试

- [x] 3.1 `castReviewRail.test.tsx`：免费循环断言 `/AI 帮写剧情/`→`/剧情抽卡/`；PRO 用例按钮名同步。验证：该文件 vitest 绿。

## 4. 回归

- [x] 4.1 C端 `npx tsc --noEmit` 干净；vitest 相关文件全绿。
- [x] 4.2 `npm run design:lint` 零新增；`openspec validate --strict` 通过。
- [x] 4.3 e2e（plot.spec 等）定位器走 testid 不受力，合流前随隔离栈补跑。


## 执行证据（2026-10-01）

- 1.1/2.x/3.1：原型 grep 零「AI 帮写剧情」；src/e2e grep 零旧名；castReviewRail 5/5、plotTool、AiAssistPanel、rewriteFlow 共 20 用例绿。
- 4.1：`tsc --noEmit` exit 0；全量 vitest 1058 绿＋CharacterManager.adopt×3（main 存量红，已对拍）。
- 4.2：design:lint 零新增（唯一 ✗＝model-config.html emoji 已提交存量）；`openspec validate --strict` 两 change 均过。
- 4.3：plot.spec e2e 定位器全走 `og-plot-draw` testid，不受改名影响；合流前随隔离栈补跑。
