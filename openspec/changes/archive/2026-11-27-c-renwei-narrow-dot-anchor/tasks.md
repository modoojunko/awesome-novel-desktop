# Tasks — c-renwei-narrow-dot-anchor

## 1. 原型先行 / 设计登记

- [x] 1.1 原型影响判定：`docs/design-c/prototypes/book.html` 无 `rw-mnote`/人味边注（grep 0 命中）→ 原型基线未涵盖本形态、不新增视觉形态、不改像素基线；`docs/design-c/prototypes/ADJUSTMENTS.md` 已追加「2026-11-27 · 锚点＝段尾实测」登记（含交互口径）
- [x] 1.2 锚点语义溯源：drafts 人味检测原型「段角胶囊跟段尾走」口径（段角胶囊后因右栏简述退役）；本屏不在 `design:check` 像素矩阵（只跑 list.html / preview.html），视觉由组件单测＋真 Chromium 几何探针覆盖

## 2. 实现（承接 PR #1128，分支 c-renwei-dot-anchor-text）

- [x] 2.1 `RenweiMarginNotes` 段尾锚落地：`textEndRect()` 取最后一个含可见字的文本节点末字后缘 Range（剥尾部空白/零宽）；`DOT_BOX_H/DOT_BOX_W/DOT_GAP_TO_BOX`；`dots`/`narrow` 状态；窄栏内联 `left/top`（短行跟末字、满行贴列缘外侧）；验证＝单测 19/19＋真 Chromium 探针
- [x] 2.2 量测缺席兜底：`textEndRect()` 返回 null 时不给内联 left，回落 `book.css` 窄栏 `left: min(var(--rw-notes-left), calc(100% - 20px))`；`right:2px` 已删除；验证＝单测「量测缺席…不给内联 left」
- [x] 2.3 RO stale 收口：`groupsRef.current = groups`，`measure()` 从 ref 取当轮问题段（ResizeObserver deps 仍只挂 `editorEl`）；验证＝实现审读＋全量单测绿
- [x] 2.4 注释与常量互指：组件头注释写「圆点跟段尾走，不钉层缘/列缘」两连判例；CSS 注释写 `min()` 仅为量测兜底＋点击穿透理由；验证＝实现审读

## 3. 测试

- [x] 3.1 锚点用例：段尾 left/top、zoom 1.25 折算、极窄钳制、宽栏不写内联锚、窄→宽 stale 门、量测缺席、尾部空白跳过；验证＝`npx vitest run src/__tests__/renweiCheck.test.tsx` **22/22 绿**
- [x] 3.2 真 Chromium 几何探针（900px 中栏）：短行「“熬的。”他说。」→ 点距末字 **6.39px**、点中心＝末行中心（109px）、距纸右缘 580px、距中栏右缘 626px；满行 → 文本末缘＝列缘（790）、点距末字 **6px**、距纸右缘 50px、距中栏右缘 96px
- [x] 3.3 变异验证：锚改列缘 → 433/628 红；去 `/zoom` → 347/433 红；去窄栏门 → 窄→宽带 stale 锚红；去钳制 → 680/703 红；去装饰跳过 → 朱雀章用例红；去 Observer → 续写不重锚红；去 characterData → 打字步 503/433 红；去 childList → 粘贴步 603/503 红；去行高补足 → WebKit 用例 528/511 红；回退 CSS `right:2px` → CSS 源守卫红；全部恢复后 22/22

## 4. 审阅整改（review-agent）

- [x] 4.1 点击穿透：窄栏整盒 `pointer-events:none`，只有 8px 圆点与 `.dtl` 接事件；真 Chromium 探针＝末字右侧 +1/+16px `elementFromPoint` 命中 `<p>`、悬停圆点出卡（display:block）、卡内按钮回调触发 1 次
- [x] 4.2 编辑即重锚：独立 `[editorEl]` effect 装 MutationObserver（subtree/characterData/childList，rAF 合并，不依赖 ResizeObserver）；单测补「窄→宽切换不把 stale 段尾锚带进文字列」＋「characterData/childList 两种变更都重锚」，并 afterEach cleanup 卸载组件断观察器
- [x] 4.3 宽栏不做无用功：先算 `isNarrow`，仅窄栏才遍历问题段做 Range 并 `setDots`；单测「宽栏不写内联 left」
- [x] 4.4 极窄钳制：内联锚 `Math.min(计算值, layerW − DOT_BOX_W − 2)`；单测 703→680
- [x] 4.5 尾部空白/零宽：`textEndRect` 反向找可见文本节点并剥尾部空白；单测断言 `setStart` offset＝3（不含尾部 2 空格＋零宽）
- [x] 4.6 测试收桩：Range/Element 桩改 `vi.spyOn`＋describe 级 `afterEach(vi.restoreAllMocks + zoom 复位)`；补 CSS 源守卫（列缘 `min()`＋pointer-events，防 `right:2px` 回潮）

- [x] 4.7 朱雀判章共存：`textEndRect` 跳过段内装饰/控件子树（`.zq-mark`/`.ProseMirror-widget`/`contenteditable=false`），不把「AI／疑似」章文字当正文末字；单测「段尾是朱雀判定章」＋真 Chromium 探针（修前 picked=疑似 x=127，修后 picked=正文末字 x=259.6）；变异验证去跳过即红

- [x] 4.8 collapsed Range 高 0（WebKit 防御）：height 0 时按段落 computed line-height 补足再居中；单测「WebKit」断言 top=528（去掉回落会返回 511）；变异验证已红

## 5. 回归

- [x] 5.1 C端门禁：`npx tsc --noEmit` **exit 0**；`npm run design:lint` exit 1 但输出与主检出逐字一致（唯一违规＝存量 `docs/design-c/prototypes/preview.html` emoji，非本改动）；`DESIGN_PARITY=1` 两 spec **7 passed / 1 failed**，失败项＝preview 阅读屏像素差 **4.598%**（主检出同栈 A/B＝**4.596%**，同一存量环境差异；本改动不触 list/preview）
- [x] 5.2 共享段判定：不触 base.css 令牌/基础组件类/pill/notice/sk/panel/f-err 家族，`node scripts/design-cross.mjs` 不适用（引用 proposal Design Impact）；renwei 相关存量单测 `renweiCheck` 22/22、`renweiChapterMemory` 3/3、`renweiChapterReset` 2/2；前端全量 **2358 passed / 1 skipped（187 files）**

## 6. 交付与归档

- [x] 6.1 只报 diff 等老板批准；批准后 push 更新 PR #1128（head `4dba00cf`，CI 绿）；老板批准后 squash 合入 main＝`6c3f7388`（2026-11-27），合并后 main CI 绿（run 45936949336）
- [x] 6.2 合入后归档：本 change 归档为 `2026-11-27-c-renwei-narrow-dot-anchor`；`renwei-check` 主 spec「正文左右分边注与覆盖层」同步（1 modified：塌缩态锚点/交互＋6 个场景）；`openspec validate --specs` **83 passed / 0 failed**
