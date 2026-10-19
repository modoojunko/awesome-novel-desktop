# 拆书结果目录只读预览

## Why

拆书完成后用户只能「盲选」：结果目录里 10 份 Markdown 只有文件名和字符数，想确认拆出来的
内容质量（比如主线剧情拆得对不对、文风像不像）必须导出到文件夹或建书之后才能看到。
2026-10-19 用户实拆《13路末班车》（82 万字、258 章）后提出：结果目录应可直接预览每份
md 的内容——在「建书/导出」决策之前先看货。

原口径（c-deconstruct-book）是「应用内 SHALL NOT 提供拆解产物的内容预览与编辑」，当时
把预览和编辑捆绑排除是为了收敛首版范围。后端 `GET /tasks/{id}/products/{filename}` 全文
端点其实早已存在（导出链路自用），本变更只翻面呈现层：**预览放开（只读），编辑继续禁止**。

## What Changes

- **完成详情结果目录**：每份产物文件名改为可点（文本按钮形态），点击弹窗只读预览全文：
  加载中 → 全文（pre-wrap 呈现，超长滚动）；加载失败 toast 报错并收起弹窗。
- **勾选与出口不受影响**：预览不改变勾选状态、不进「已选 N/M」口径；勾选框仍按行点击切换。
- **文案翻面**：详情页「应用内不预览、不编辑拆解产物」改为「点文件名可预览（只读）；应用内
  不编辑拆解产物」；目录树头补「点文件名可预览」提示。
- **不改**：后端零新增端点（复用既有 products 全文端点，清单外文件名维持 404）；运行中/失败/
  需重传态不出预览（products 仅完成态呈现）；不做应用内编辑、不做 markdown 渲染美化
  （纯文本 pre-wrap，产物消费仍以导出/建书为准）。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `deconstruct-book`: 修改「结果目录与出口勾选」——预览从 SHALL NOT 翻为 SHALL（只读），
  编辑维持 SHALL NOT。基线为活跃变更 `c-deconstruct-book`（已实现未归档，主 `openspec/specs/`
  尚无该 capability；`c-deconstruct-resilience` 未触碰本条 requirement，无叠层冲突）。
  归档顺序：先 `c-deconstruct-book`，后本变更。

## Impact

- **后端**：零代码新增（仅 `router.get_product` docstring 更新口径）；`test_deconstruct_api.py`
  补端点行为钉（清单内回全文／清单外与穿越名 404——端点此前无直接测试）。
- **前端**：`TaskDetailPage`（结果目录行重构 label→div＋文件名按钮＋预览弹窗）、
  `deconstructApi`（`getDeconstructProduct` 封装）、`index.css`（`.fd-name`）、
  `design/base.css`（`.mcard.rd-style`＋`.preview-md`，C端 本地段）。
- **测试**：`toolsDetail.test.tsx` 补预览三态（成功＋加载中／失败两臂＋三种关闭路径／勾选不被动）。
- **风险**：极低——只读呈现层，无数据写回面；文件名合法性由后端按产物清单校验（存量逻辑）。

## Design Impact

- **受影响端**：C端。
- **屏/弹层**：`/tools/deconstruct/:id` 完成态；新增一个预览弹层（复用 scrim＋mcard 版式，
  新增 `.rd-style` 宽卡变体）。
- **共享段**：不触碰 `base.css` 共享令牌与两端共享段；`.rd-style` 落在【C端 本地段】。
- **原型**：`docs/design-c/drafts/ai-novel-c端-拆书.html` 完成态补「点文件名预览」弹层注记，
  `docs/design-c/prototypes/ADJUSTMENTS.md` 登记；复用既有弹窗版式，不新增布局形态。
