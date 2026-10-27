# 拆书失败详情页原地换模型（泡泡）

## Why

失败任务详情页的「去换模型」出口当前是 `<Link to="/config">`——一点就跳去模型配置页，
脱离任务上下文。真机反馈（2026-10-27）：用户在失败详情想的是「换个模型接着拆这个任务」，
而不是「去改模型配置」；跳走后还得自己找回来、再点续拆，链路断成两截。

而后端 `/deconstruct/tasks/{id}/resume` 早已支持 `api_config_id`/`ai_model` 换模型续拆
（c-deconstruct-resilience D8，含 resolve 校验＋model_history 追加），前端却从未接线——
纯前端欠账。工作台正文生成已有现成的模型选择泡泡（c-prose-model-search 的 `ModelPicker`：
portal＋fixed 锚定＋顶搜索），本变更把它泛化两处复用，失败详情原地完成「换模型 → 续拆」。

## What Changes

- **失败详情页出口改造**：瞬时故障（provider_unavailable/stalled/timeout/rate_limit）与
  内容审核（content_filter）的「去换模型」出口不再跳 `/config`——页内弹出现有模型选择泡泡
  （带搜索、按配置分组、原模型旗标）；选定即暂存（页内可见「已选新模型 ×××」），
  点「从断点续拆」以新模型入队续拆；页面与其余出口（续拆/删除/告警账）一律不动。
- **回落保底**：可选模型 <2（含清单加载失败/为空）或鉴权/配置类失败（auth/config/route，
  病根在配置本身）仍走原「去模型配置」链接——单模型用户零变化。
- **组件泛化**：`ModelPicker` 从 workbench/modals 导出并加可选 props（label/triggerLabel/
  triggerClass/flagLabel/panelWidth），工作台既有调用缺省行为逐字节不变。
- **不改**：resume 端点契约（已支持换模型）、model_history 语义、续拆按钮/删除流程、
  运行中与完成态详情、模型配置页本身。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `deconstruct-book`: 修改「任务清单与详情」——失败面板的换模型出口从跳配置页改为
  详情页原地泡泡选模型＋暂存＋续拆携带，新增两条 scenario（原地换模型、可选模型不足回落）。
  基线注意：活跃变更 `c-deconstruct-resilience` 的 delta 也 MODIFIED 同一 Requirement
  （已实现未归档），归档顺序须先 resilience 后本变更，冲突面仅「失败面板出口」一句。

## Impact

- **前端**：`components/novel/workbench/modals.tsx`（ModelPicker 泛化导出）、
  `components/tools/TaskDetailPage.tsx`（泡泡接线＋暂存＋resume 带参）、
  `__tests__/toolsDetail.test.tsx`（新用例＋fetchModelOptions mock）；AiModal 既有泡泡
  用例回归。后端、提示词仓零改动。
- **风险**：纯前端，续拆请求体仅在用户主动换模型时多两字段；不换模型路径请求体不变。
