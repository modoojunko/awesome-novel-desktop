# c-agent-panel-consolidate Design

## Context

盘点实勘（2026-11-18）：设定面板内嵌 AiCardModal 弹窗是 agent 产卡链的**平行重复路径**
——agent 工具已全量存在（题材四格/世界观三件/伏笔两件/主线/角色发散/命名/体检），
且 dock chips 11-15 已收编一轮（settings.default 每面板 chip 发自然语言，16 行）。
chips 覆盖缺口：世界观各要素格、角色出稿（定向/发散）、命名。

面板→dock 反向触发目前不存在（dock→面板的 open 芯片有：onOpenAction 分派
zhuque/plot_draw/cast_review/simulate 等；面板→dock 只有 NovelWorkspace 对
ChapterWorkspace 的信号先例：aiWriteSignal 计数器模式）。

## Goals / Non-Goals

- Goals：入口统一（面板 AI 按钮全部改「让助手办」）；上下文随行（格名/底稿）；闸链
  零绕过；AiCardModal 仅文风三区保留
- Non-Goals：抽卡/推演弹窗改造（挂账待实测）；AiCardModal 组件删除（文风仍用）；
  生成正文 AiModal 改造（核心写作流安全面）

## Decisions

### D1：autoAsk 信号（aiWriteSignal 同款计数器模式）

Aui2Dock 新 prop：`autoAsk?: { seq: number; message: string }`。宿主（NovelWorkspace）
持 `autoAskState`；面板按钮 → setAutoAskState(n => ({seq: n.seq+1, message}))。
Aui2Dock 内 useEffect [autoAsk?.seq]：seq>0 → 走既有 submit 路径（与手输同函数：
streamAssistantChat＋run 生命周期＋镜像＋落盘全一致）。**零闸绕过**：键校验/域校验/
授权梯度全在既有链上。

提交函数提取：现有 submit 内嵌在回调里，提取 `submitMessage(text)` 内部函数供
autoAsk effect 复用（不改变手动路径行为）。

### D2：面板触发契约（上下文随行）

各面板「让助手办」按钮组装消息（自然语言＋上下文摘要）后 bump seq：
- 世界观格：`帮我起草「{格名}」：{底稿前 80 字}`——底稿直传保住 c-world-draft-input
  的 current 语义（agent 从消息拿 current 调 draft_worldbuilding）
- 题材格：`给我几个「{格名}」的候选。`
- 角色出稿：`按现有角色和主线，{定向|发散}出稿一个角色草案。`
- 主线/伏笔/命名：直接复用 chips command 文案（单一文案源——chips 表即文案源，
  面板按钮从 chatRegistry 注册表读 command，不抄第二份）

### D3：chips 覆盖补缺

settings.default/settings.chars chips 补：world 各要素格（按 SINK_TOPIC 表）、
chars 出稿两态（draft_character 定向/diverge_character_group 发散）、命名
（draft_names）。key 走既有 validateRegistrations 白名单校验（工具清单内才可注册）。

### D4：退役清单（AiCardModal 入口移除，组件保留）

| 面板 | 退役按钮 | 改为 |
|---|---|---|
| GenreSettingForm | 四格「AI 填」 | 让助手办（格名入消息） |
| StoryArcForm | 起草主线/结局校准 | 让助手办（chips 文案） |
| HooksSettingForm | h1 起草/h2 拟收束/h3 体检/h4 查一致性 | 让助手办（chips 文案） |
| CharacterManager | 出稿/体检 | 让助手办（定向/发散两态） |
| WorldSettingPanel | 各格「AI 填」 | 让助手办（格名＋底稿） |

保留：StyleSettingForm（文风三区 AiCardModal）、生成正文 AiModal、简介建书流。
各面板 AiCardState/清理逻辑移除要彻底（防死代码）；SettingsView 的 runAi/clearAi
分发链按面板实际保留面收窄。

## Risks / Trade-offs

- **就地感丢失**：作家填表时点按钮要瞥一眼对话卡——autoAsk 自动聚焦 dock 缓解；
  采纳后 effect/刷新链保证表单同步
- **上下文丢失**：底稿直传截 80 字可能断章——世界格底稿本就短（单格），可接受；
  长底稿场景挂账
- **chips 文案双源风险**：D2 强制面板从注册表读 command（不抄第二份），测试钉
  「面板按钮文案===chips 文案」

## Migration Plan

纯前端入口替换；后端零改动；旧弹窗组件保留（文风仍用），回滚＝revert。

## Open Questions

<!-- 无：七项收编/三项保留/两项挂账，boss 按分析拍板（2026-11-18）。 -->
