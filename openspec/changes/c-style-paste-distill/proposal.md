## Why

文风蒸馏的样本输入目前只有两路——项目 `novel-samples/` 目录文件＋已归档章节勾选。新书两路皆空时蒸馏是死路；作家手里现成的文本（别处写的稿、自己满意的旧作）也无法直接喂给蒸馏。蒸馏的第一入口应该是「把你认可的文字直接贴进来」。

## What Changes

- **后端 step1 受理粘贴样本**：`POST /settings/ai/style-distill/step1` body 新增 `text` 字段（粘贴文本，须为字符串）。`text` 非空＝**显式重启**——清空 `style-quant.draft` 全部旧产物（仅内存态，失败时零写入），只按粘贴文本装配样本（忽略 files/chapter_ids），区间校验沿用既有 3,000–10,000（去空白字符数）与既有中文文案；`samples_used=["粘贴文本"]`、`chapter_count=0`（置信度按样本量单因子）。`text` 缺省时现行为分毫不变（draft 续跑短路保留）；蒸馏链失败后重试持续携带同一粘贴文本，不漂移为文件/章节路。
- **前端新增「粘贴文风样本」弹窗**：大 textarea＋实时去空白字数＋区间状态提示（区间外禁用提交并给补救文案）。量化页签空态以「粘贴文本蒸馏」为首选入口（保留「从文件/章节选样本」次入口）；样本选择页加「直接粘贴文本」入口。
- **画像确认卡补六行基线预览**：作者确认前即可看到将要落卡的六行量化值（「约 X（±容差）」口径，行值取自服务端同一构建产物）；**锁定行如实显示落卡将保留的上一版值并标记**，预览与落卡逐行一致。文件/章节蒸馏流同样受益。
- **不新增端点、不新增提示词模板**：复用既有三步管线（step1→step2→step3→commit）与 `style_distill_step1/2/3`；会员门控、计量（`settings_style_distill`）、失败记账全部沿用。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `style-quant`：①「样本两路与区间校验」扩为三路（新增粘贴文本路＋受理/拒绝语义）；②「蒸馏三步端点与 draft 续跑」新增粘贴＝显式重启语义（不清 draft 会被续跑短路吞掉新样本）；③「基线只读与作者画像确认」新增确认卡六行基线预览＋粘贴弹窗入口/字数提示的界面要求。

## Impact

- 后端：`client/backend/settings/ai_router.py`（step1 粘贴分支、step3 rows 落盘）；`client/backend/settings/style_quant_model.py`（commit_draft 复用 rows、quant_doc deepcopy 修复）；`client/backend/tests/test_style_settings_v2.py`（粘贴受理/超限/非字符串/重启语义/重试/预览＝落卡）。
- 前端：`client/frontend/src/components/novel/settings/StyleSettingForm.tsx`（入口与接线、确认卡预览、重启起跑）；新增 `StylePasteModal.tsx`；`client/frontend/src/lib/styleApi.ts`（`countSampleChars`＋`rows` 类型）；`client/frontend/src/components/novel/workbench/SettingsView.tsx`（右栏蒸馏行 desc 补第三路）；`client/frontend/e2e/style-quant.spec.ts`（粘贴全链用例）；`__tests__/StyleSettingForm.fewShots.test.tsx`（mock 适配）。
- 原型：`docs/design-c/prototypes/style-settings.html` ＋ `ADJUSTMENTS.md` 登记。
- 不触两端共享段（无新令牌档位/组件词汇/状态语言），S端 零改动。

## Design Impact

- **受影响端**：仅 C端；S端 无任何改动，无需截图对照。
- **受影响屏/弹层**：设定页 → 文风面板 → 量化参数页签；新增「粘贴文风样本」弹窗层（复用既有 `Modal` wbStyle 版式）；蒸馏样本选择页加粘贴入口；作者画像确认卡增补基线预览段。
- **对象状态**（对照 design-language §5 状态语言总表）：弹层复用既有 mcard 状态（scrim/进场）；提交是同步校验后立即关闭、无长驻提交态，`locked` 不启用；样本输入区为局部态——字数不足（warn 提示＋提交禁用）、区间内（ok）、超限（warn 提示＋提交禁用），语气一律用既有 info/ok/warn/err 词表，不新增第四种胶囊形态、不引入 success/danger。
- **是否触碰共享段**：否——base.css 令牌与基础组件类零改动，无新语气档位；故不声明 Modified: design-system，也不触发 design-cross。
- **是否需要原型先行**：是——`style-settings.html` 补粘贴入口＋弹窗层＋确认卡基线预览段，`ADJUSTMENTS.md` 逐条登记；弹窗打开态与既有先例同口径不入 parity 基线场景。
- **设计工件由谁产出**：实现侧自查（全部复用既有组件词汇与状态语言，无新形态需设计侧会话）。
