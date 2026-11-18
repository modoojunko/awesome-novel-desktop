# assistant-effects Specification

## Purpose
TBD - created by archiving change c-agent-effects. Update Purpose after archive.

## Requirements

### Requirement: 写操作 Effect 系统

agent 的每个写类工具 SHALL 声明 effect 元数据（domain/target），router 在 run_end 事件中注入 effects 数组。前端 Aui2Dock SHALL 在收到 run_end 时提取 effects 并调 onEffects 回调。NovelWorkspace SHALL 实现按域刷新（复用已有加载函数），SHALL NOT 全量重拉。dirty 状态（作家正在编辑未保存）SHALL 跳过刷新并在对话内提示。

#### Scenario: 确认章纲后树刷新
- **WHEN** agent 执行 confirm_chapter 成功
- **THEN** run_end 事件携带 effects [{action:"refresh",domain:"chapters",target:ref}]，Aui2Dock 调 onEffects，NovelWorkspace 刷新章节列表，左侧树第七章变绿

#### Scenario: dirty 保护
- **WHEN** 作家正在编辑某字段未保存，agent 执行写操作
- **THEN** 刷新跳过（NovelWorkspace 检查 dirty），对话内提示「有未保存的编辑」

### Requirement: 结构动作工具收编

agent SHALL 提供六个结构管理写工具（confirm_chapter/unconfirm_chapter/archive_chapter/unarchive_chapter/add_volume/add_chapter），kind=write 走授权梯度，能力核走 caps/ 直调（与面板同源），写授权卡携带人话预览。

#### Scenario: 确认章纲
- **WHEN** 作家说「确认第七章章纲」
- **THEN** agent 调 confirm_chapter → 授权卡→允许 → 章纲确认落库 → 回执＋树刷新

#### Scenario: 新增一卷
- **WHEN** 作家说「开第二卷」
- **THEN** agent 调 add_volume → 授权卡→允许 → 卷创建落库 → 回执＋左侧树出现新卷

### Requirement: 世界观三件收编

agent SHALL 提供世界观三件读/产卡工具（draft_worldbuilding/check_worldbuilding/lore_suggest），与设定·世界观面板同源，产物过目采纳不自动写回。

#### Scenario: 起草世界观
- **WHEN** 作家说「帮我起草世界观」
- **THEN** agent 产世界观候选卡，过目后由作家采纳
