# assistant-panel-consolidate Specification

## ADDED Requirements

### Requirement: 面板 AI 入口「让助手办」

收编面板（题材四格/主线/伏笔/角色出稿/世界观/命名）的 AI 触发按钮 SHALL 改为「让助手办」：点击后 SHALL 聚焦右侧助手 dock 并自动发出对应指令（指令含面板上下文：格名/底稿摘要），作家无需再手动输入。原内嵌 AiCardModal 弹窗路径 SHALL 退役（组件保留供文风三区使用）。文风三区起草、AI 生成正文、简介 AI 起草 SHALL 保留既有弹窗/内联流。

#### Scenario: 世界观格让助手办
- **WHEN** 作家在世界观面板某要素格点「让助手办」
- **THEN** dock 聚焦并自动发出起草指令（含格名；页面底稿作 current 上下文），agent 产卡回对话，作家在卡上过目采纳

#### Scenario: 保留项不受影响
- **WHEN** 作家在文风面板点「AI 起草·三区」或在写作页点「生成正文」
- **THEN** 仍走既有弹窗/内联流，行为不变

### Requirement: dock autoAsk 通道

Aui2Dock SHALL 提供 autoAsk 命令式信号（seq 计数＋message）：宿主变更 seq 时 dock SHALL 自动提交该消息（走既有 chat SSE 链，与手动发送同路）。autoAsk SHALL NOT 绕过任何既有闸（键校验/域校验/授权梯度照走）。

#### Scenario: 自动提交与手动同路
- **WHEN** 面板触发 autoAsk
- **THEN** dock 中出现与手输等效的用户气泡与 run 生命周期（run_start→…→run_end），闸链一致

### Requirement: chips 覆盖补缺

settings 域 chips SHALL 补齐世界观各要素格、角色出稿（定向与发散）、命名入口（自然语言 command），使收编面板的每项能力在 dock 侧都有对等 chip；chips key SHALL 过既有启动校验白名单。

#### Scenario: 世界观 chip 可用
- **WHEN** 作家在设定·世界观页签看 dock 芯片
- **THEN** 出现各要素格起草入口，点击即发对应自然语言指令

### Requirement: 收编后采纳按卡种写回

收编能力的产物 SHALL 一律以对话内产物卡呈现，卡 SHALL 按卡种携带写回定位信息（settings 字段卡携 stype+field，世界卡携 topic，角色草案卡携 character_draft 全字段）。dock「采纳·写入」SHALL 按卡种走对应既有写链（settings GET+merge+PUT／角色建卡 API／卷纲 PUT），SHALL NOT 退回弹窗确认。写回后 SHALL 发刷新信号：面板无未保存修改时重载显示新内容，有未保存修改时 SHALL NOT 重载（对话内提示作家手动刷新）。实施实勘补记（2026-11-18）：dock 采纳写回原只有卷纲草案一条，本 Requirement 的按卡种写回为新增批次。

#### Scenario: 采纳后表单同步
- **WHEN** 作家在对话卡上采纳世界观草稿
- **THEN** 书数据写入走既有采纳链，世界观面板重渲染显示新内容
