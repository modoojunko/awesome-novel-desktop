## REMOVED Requirements

### Requirement: 写类工具受授权梯度管控且写后可撤销

**Reason**: 三档会员把 `allow_book`（本书内自动执行）收为 MAX 独有；原“三档授权（默认/本书/全部）”对所有档位开放，与新会员边界冲突。

**Migration**: 由 ADDED「写类工具授权梯度（三档会员）」承接：标准/PRO 仅 `confirm_each`，MAX 可选 `allow_book`；硬地板与撤销回执保持原语义。

### Requirement: 档位门控与免费体验

**Reason**: 原条款以“免费/干活类 PRO/发散类 MAX”描述，未覆盖标准（免费）档的头脑风暴能力与 PRO 的 AI 写手边界，也与 `assistant-execute` 的 PRO 起发放不一致。

**Migration**: 由 ADDED「三档助理体验」承接：标准＝只读头脑风暴；PRO＝可写 AI 写手（每写必确认）；MAX＝可查/可画/可建书/可自动执行。

## ADDED Requirements

### Requirement: 写类工具授权梯度（三档会员）

- 直接写/改类工具（书内实体变更、知识库变更）SHALL 经授权梯度管控：
  - **标准（免费）**：无写类工具；仅读类/对话。
  - **PRO**：`confirm_each`（每写必确认——授权卡列出将改实体/字段与目标预览，批准后执行）。
  - **MAX**：`confirm_each` 或 `allow_book`（本书内实体写自动放行，写完落回执＋撤销 chip）。
- `allow_all` SHALL 仅作存量兼容映射到 `allow_book`；SHALL NOT 作为新可选档位。
- 硬地板清单（删除全书、批量删除章节、覆盖已确认的设定项、变更授权档位本身）SHALL 在任何档位下都弹授权卡，SHALL NOT 存在自动路径；授权档位的变更入口 SHALL 只存在于设置页，SHALL NOT 出现在 agent 工具清单。
- 每次写入（无论自动或批准）SHALL 落回执卡并携带撤销入口；撤销 SHALL 基于版本历史实现。
- 拒绝时 SHALL 只向 agent 反馈非诊断性拒绝语，完整理由仅呈现给作家。
- 授权批准 SHALL 可持久：执行中断（含应用重启）后未决授权 SHALL 可恢复继续。

#### Scenario: 标准（免费）无写工具

- **WHEN** 标准（免费）用户要求助手直接修改角色年龄
- **THEN** 助手不调用写类工具，回对话内 PRO 升级引导（说明开通后能做什么），不写入

#### Scenario: PRO 每写必确认

- **WHEN** PRO 用户要求助手直接修改角色年龄
- **THEN** 助手停车弹授权卡，批准后执行并落回执；未批准不写入

#### Scenario: MAX 本书自动执行

- **WHEN** MAX 用户在本书内选择 `allow_book` 并要求助手修改一个卷纲字段
- **THEN** 自动执行并落回执＋撤销入口；硬地板类请求仍弹授权卡

#### Scenario: 硬地板任何档位都弹卡

- **WHEN** MAX 用户要求助手删除全书或批量删章
- **THEN** 仍弹授权卡，不自动执行

### Requirement: 三档助理体验

- 助手对话本身 SHALL 对登录用户可用（吃用户自配模型 Key）；未配置 Key 时 SHALL 在对话内出配置引导卡，SHALL NOT 以报错打断对话流。
- **标准（免费）**：读类工具与问答可用；SHALL 能读章节/设定/大纲/进度/版本/页面字段并与作家头脑风暴（聊设定/人物/剧情/走向）；SHALL NOT 调用起草/生成/写类工具，SHALL NOT 把想法写入书。
- **PRO**：增加起草/生成/写类工具（`ai-plan`/`ai-generate`/`settings-ai-fields`/`assistant-execute` 等），作为 AI 写手；每写必确认。
- **MAX**：增加知识库检索/收录、人味检测与逐行修改指引、AI 图像、拆书建书、发散起草/剧情推演/文风蒸馏、`allow_book` 自动执行。
- 档位不足或所需提示词包缺失时 SHALL 在对话内出升级引导卡（说明开通后能做什么），SHALL NOT 以 403/异常打断对话流。
- 免费体验 SHALL NOT 设轮数闸；长对话成本由 compact 与上下文预算控制。

#### Scenario: 标准（免费）头脑风暴

- **WHEN** 标准（免费）用户说「这卷反派动机不够狠，帮我想几个方向」
- **THEN** 助手读本书设定/大纲后给出方向与讨论；不生成可落库的章纲/正文，不写书

#### Scenario: 标准（免费）要求直接写

- **WHEN** 标准（免费）用户说「直接把第三章重写一遍」
- **THEN** 助手回 PRO 升级引导（AI 写手能做什么），不调用生成/写类工具

#### Scenario: PRO AI 写手

- **WHEN** PRO 用户说「按这版章纲把第三章写出来」
- **THEN** 助手按正文方案卡流程产出提示词与方案，作家过目后生成；每写必确认

#### Scenario: MAX 秘书

- **WHEN** MAX 用户说「把这段的人味问题查一下并给我改法」
- **THEN** 助手调用人味检测（`human-taste`）返回逐行问题与修改指引；PRO 用户同一请求走 MAX 升级出口
