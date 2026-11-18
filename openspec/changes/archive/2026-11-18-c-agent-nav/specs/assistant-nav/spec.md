# assistant-nav Specification

## ADDED Requirements

### Requirement: 页面切换工具

agent SHALL 提供章节页签切换工具（switch_tab），入参为页签键（og/prose/settings/relations/hooks/actions/style 七值封闭集）。工具 SHALL 属读类（免授权梯度）。服务端 SHALL 校验 tab 白名单：非法值 SHALL 返回失败摘要（模型如实转告，列可选页签），SHALL NOT 生成 effect。工具 summary SHALL 回喂切换结果。

#### Scenario: 切到正文
- **WHEN** 作家在章纲页签对助手说「把页面切到正文」
- **THEN** agent 调 switch_tab(tab="prose") → 服务端校验通过并生成 navigate effect → 前端立即切到正文页签 → summary 回喂「已切到正文」

#### Scenario: 非法页签
- **WHEN** 作家说「切到不存在的页」
- **THEN** 校验失败，无 effect 产生，agent 如实说明切不了并列出可选页签

### Requirement: 域封闭可见性

switch_tab SHALL 仅在章节页签域（ch:og/ch:prose/ch:settings/ch:relations/ch:hooks/ch:actions/ch:style）的工具清单中可见；卷纲/设定/预览/默认域 SHALL NOT 声明该工具——域外助手无从调用，源头杜绝跨域乱切。

#### Scenario: 卷纲页签不可见
- **WHEN** 作家在卷纲页签说「切到正文」
- **THEN** 该域工具清单不含 switch_tab，模型无从调用，如实说明「打开一章后我再帮你切」（带出口话术）

### Requirement: navigate effect 即时应用

切换 effect SHALL 随工具步骤完成即时下发（不等 run 收尾）；事件 SHALL 携带 action="navigate"、domain="ui"、target=页签键。前端 SHALL 在章节工作台内真实切换页签（与作家手点页签同语义），SHALL NOT 重拉章节数据。navigate effect SHALL NOT 持久化——历史回放 SHALL NOT 重放导航（作家重开书不被 teleport）。refresh 类 effect 仍按既有口径在 run 收尾批量应用。

#### Scenario: 中途翻页
- **WHEN** agent 调用 switch_tab 成功且流未结束
- **THEN** 页面在 agent 继续说话的同时已切到目标页签（作家无等待感）

#### Scenario: 回放安全
- **WHEN** 作家重开书或切页签回来回放历史
- **THEN** 历史中的导航不重新执行，页面停在作家当前位置

### Requirement: 前端应用守卫

前端 SHALL 仅在章节工作台且当前选中章节时应用 navigate effect；不满足时 SHALL 静默忽略（不切页、不报错）。页签间切换 SHALL 与手点页签同语义（不拦脏表单）；dock 线程随页签重绑沿用既有页签隔离机制。

#### Scenario: 竞态忽略
- **WHEN** effect 到达时作家已手动离开章节工作台（如去了设定页）
- **THEN** 前端忽略本次导航，页面保持作家当前位置，无报错

### Requirement: 话术契约

switch_tab 的工具描述 SHALL 约束话术：调用前的话术 SHALL NOT 预告「已切」——只能说「我切过去」「你看一下正文」；切换是否完成由系统执行与回执，模型 SHALL NOT 凭话术背书未发生的操作。

#### Scenario: 无幻觉背书
- **WHEN** agent 决定切页签
- **THEN** 话术为「我切过去」类进行时表述；页面由 effect 真实驱动，不再出现「已切到」假话术（走查实锤场景回归）
