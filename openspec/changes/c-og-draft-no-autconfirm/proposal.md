## Why

章纲编辑页「保存草稿」在无必填缺口时**自动确认章纲**（`ChapterWorkspace.tsx:484`，注释「草稿保存无缺项 → 自动确认（设计稿行为）」）。该行为是 PR 3 时代登记的应用侧扩展，当时必填 4 项、保存草稿常因缺格子停在草稿态；c-og-slim-v2（09-26）把必填砍到 2 项后「无缺口」几乎恒成立——保存草稿实际变成必确认，按钮语义与实际行为打架。用户 09-29 实机误触确认，拍板（2026-09-30）：**方案 A——保存草稿只保存，永不改确认状态；确认只走「确认章纲」按钮，并补「撤回确认」出口**（存量缺口：界面上本就没有取消确认的操作）。

## What Changes

- **保存草稿去自动确认**（BREAKING 行为变更，无数据兼容负担）：`handleSaveDraft` 只走既有保存链，toast 恒「草稿已保存」；SHALL NOT 调确认端点。
- **新增「撤回确认」**：已确认章可退回草稿态——后端 `POST /chapters/{ref}/unconfirm`（status→draft、confirmed_at 清空、outline_status 派生随状态机）；前端确认徽标（OgPane 查看态）旁加「撤回确认」入口（confirm 弹窗承担后果告知），撤回后「确认章纲」按钮恢复可点。
- 「确认章纲」按钮行为不变（缺口清零才可点）。
- spec 同步（MODIFIED）：`workbench`「章纲页签查看/编辑两态」Requirement——保存草稿语义收窄＋撤回确认动作；ADJUSTMENTS.md 修订原自动确认登记条。
- 零拆章/零提示词链路改动；gate（必填两项）不动。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `workbench`: 「章纲页签查看/编辑两态」Requirement 增「保存草稿只保存不改确认状态」「撤回确认」两条；删旧「保存草稿无缺项自动确认」隐含口径（ADJUSTMENTS 旧登记条随批修订）。

## Impact

- 后端：`client/backend/chapters/router.py` 新增 unconfirm 端点（≈15 行；status 白名单派生已有）＋1 例 pytest。
- 前端：`ChapterWorkspace.tsx`（handleSaveDraft 去自动确认）＋ `OgPane.tsx`（查看态撤回确认入口）＋ 新 prop 链；`useOutline.ts` 或直调 api 均可（按现有 confirmChapter 同层落）。
- 测试：单测（chapterWorkspace plotFlow 的 confirmChapter mock 链、useOutline 增 unconfirm 用例）；e2e 两处钉自动确认的断言改口径（`outline-ai-draft.spec.ts:174`「已保存并确认章纲」→「草稿已保存」；`workbench-features.spec.ts:193` 同）＋撤回确认新用例（workbench-features 或 chapter-dossier 增段）。
- Design Impact（用户可见界面改动，规则必填）：
  - 受影响端：**C端**（S端 不涉及）。
  - 受影响屏/弹层：写作工作台·章工作台「章纲」页签——查看态底部动作区（撤回确认入口，仅已确认态出现）＋保存草稿 toast 口径；新增一个 confirm 弹层（撤回确认，info 语气）。
  - 对象状态：沿用既有状态语言（按钮 enabled/disabled、notice/pill 的 info/ok/warn/err 词表）；不新增状态档位、不新增组件词汇；confirm 弹窗为既有弹层形态。
  - 共享段：**不触碰**（零 CSS 变更——撤回入口复用既有 `.btn-ghost`/`.done-note` 词汇，design-cross 不适用）。
  - 原型先行：章工作台事实源 `book.html` 在 parity 基线内，但撤回确认是**新增应用侧动作**（原型未建模）→ 按 ADJUSTMENTS 按 change 段登记（自动确认登记条随批修订），不进 parity 截图；设计工件由实现侧自查产出。
  - 文案口径：按钮词动词（「撤回确认」）；confirm 弹窗补救句带双出口（「保留确认」/「撤回」）；toast「草稿已保存」沿既有措辞。
