# polish-wizard Specification（delta）

## REMOVED Requirements

### Requirement: 去 AI 味修稿向导（四步弹窗）

**Reason**：去AI味改写已拍板退役（2026-10-17）。其①步「AI 味检查」（五六项规则）与人味检测（19 项指纹＋人味率＋定位 findings，免费零额度）功能重复且覆盖面更小——检查层由 `renwei-check` 收编为唯一检测引擎；其 AI 逐段代笔（③整体修改）经作家拍板取消——人工边注改稿（人味检测的逐段重扫闭环）成为唯一改稿路径。判定知识不丢失：规则类由检测引擎承接，结构红线类由生成侧反AI红线（生成时预防）承接。

**System Impact**：移除整条向导链——前端四步弹窗（PolishWizard 及 `openPolishWizard` 入口）、右栏「去AI味」动作卡（`ai-polish`）、`POST /ai-flavor-scan` 向导检查端点、朱雀存档合并问题清单逻辑、`/write/polish` 调用编排与 `quick_verdict` 快扫（端点与口径退役见 prose-writing delta）。润色/扩写/压缩（选中改写其余项）、生成侧反AI红线与人味写法、朱雀检测均不受影响。作家改稿路径收敛为：人味检测定位 → 左右边注指导人工修改 → 逐段重扫 → 朱雀真检。
