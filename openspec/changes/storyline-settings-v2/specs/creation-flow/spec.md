# creation-flow 主线卡需求迁移

## REMOVED Requirements

### Requirement: 主线卡（建书后、卷纲前的拆纲环节）

**Reason**: 主线设定页契约整体迁移至新能力 `storyline-settings`（2026-09-12 用户拍板「主线只管主线」：创建期只写「从头到尾的全景＋结局三问」）。本需求的三块内容（一句话主线＋结局＋分卷表）中：分卷表移交写作阶段（数据保留），一句话主线升级为 fullstory 全景，结局改为三问自由输入；「主线为空 SHALL NOT 阻断进入卷纲、章纲」「整存整取」等语义已在 `storyline-settings` 中保留。原需求的「待定」合法性随分卷表一并移交写作阶段。

**Replacement**: `openspec/specs/storyline-settings/spec.md`
