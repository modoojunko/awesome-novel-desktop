# cover-avatar Delta — c-ai-modal-confirm

## MODIFIED Requirements

### Requirement: 封面画面 AI 提取

系统 SHALL 提供端点 `POST /api/novels/{id}/image-prompt/cover-extract`，从书级白名单素材（选题 genre/sub_genre、一句话故事 promise_note、简介 synopsis、主线 story_arc.fullstory、世界舞台 stage）经提示词仓模板 `image_cover_scene` 蒸馏出一段封面画面场景草稿。端点 MUST 挂 `image-generate` 权益门与书模型就绪门（未就绪 503，`reason` 与前端 `ai_state` 同枚举；非本书 404）。模板 MUST 来自提示词仓（缺包沿既有 503 `prompts_missing` 语义）；模型输出 MUST 按严格 JSON 契约解析（`{"scene": ...}`），解析失败或空 scene MUST 返回 502 可重试错误。草稿 SHALL 在工坊内「AI 起草稿」出卡呈现供用户过目；用户点「采纳 · 填入描述」SHALL 才填入「画面描述」输入框（用户可改、显式保存才落库）；直接关闭＝不采纳，输入框与设置 MUST 保持原值；「换一个」SHALL 重新生成并替换卡内草稿。草稿 MUST NOT 直接写入输入框、设置或触发生成任务。产出场景 MUST 遵守模板硬约束：画面无文字载体、人物只作剪影/背影/远景、不出现书名/角色名/势力名专名、不剧透关键反转。

#### Scenario: 提取草稿填充画面描述

- **WHEN** PRO 用户在封面工坊点「AI 提取」
- **THEN** 端点 SHALL 返回 `{scene}`，前端 SHALL 出卡呈现草稿全文；点「采纳 · 填入描述」后草稿填入「画面描述」输入框并提示可修改后保存；未点保存时设置 MUST 保持原值

#### Scenario: 关闭即弃

- **WHEN** 出卡后用户未点采纳直接关闭
- **THEN** 「画面描述」输入框保持原值，无任何内容被写入

#### Scenario: 书模型未就绪

- **WHEN** 本书未绑定可用的写作大模型配置
- **THEN** 端点 MUST 返回 503，`detail.reason` 为 ai_state 枚举值，前端按既有四态卡引导

#### Scenario: 坏 JSON 可重试

- **WHEN** 模型返回非 JSON 或 scene 为空
- **THEN** 端点 MUST 返回 502 且文案含「可重试」；调用账目 SHALL 记失败行

#### Scenario: 素材白名单

- **WHEN** 组装提取请求
- **THEN** 发送内容 SHALL 只含五类书级素材（各按上限截断），MUST NOT 含正文、章纲、角色 dossier

### Requirement: 头像外貌 AI 起草

系统 SHALL 提供端点 `POST /api/novels/{id}/characters/{cid}/image-prompt/look-extract`，从角色卡白名单素材（题材、性别/年龄/种族、外貌档案 look、势力/身份、一句话人设）经提示词仓模板 `image_avatar_look` 蒸馏出一段只写外貌/服饰的头像描述草稿。端点 MUST 挂 `image-generate` 权益门、书模型就绪门（未就绪 503，`reason` 与前端 `ai_state` 同枚举）与角色归属校验（不属于本书/当前用户 400）。模板 MUST 来自提示词仓（缺包沿既有 503 `prompts_missing` 语义）；模型输出 MUST 按严格 JSON 契约解析（`{"look": ...}`），解析失败或空 look MUST 返回 502 可重试错误。草稿守卫 MUST 与 prompt_builder 的 avatar_prompt 截断（140 字）对齐。草稿 SHALL 在工坊内「AI 起草稿」出卡呈现供用户过目；用户点「采纳 · 填入描述」SHALL 才填入「头像描述」输入框（用户可改、显式保存才落库）；直接关闭＝不采纳，输入框与设置 MUST 保持原值；「换一个」SHALL 重新生成并替换卡内草稿。草稿 MUST NOT 直接写入输入框、设置或触发生成任务。产出 MUST 遵守模板硬约束：只写外貌/服饰、适配近景头肩构图、服装无文字徽标、不出现角色名/势力名专名、不编造角色卡没有的特征。

#### Scenario: 起草草稿填充头像描述

- **WHEN** PRO 用户在头像工坊点「AI 起草」
- **THEN** 端点 SHALL 返回 `{look}`，前端 SHALL 出卡呈现草稿全文；点「采纳 · 填入描述」后草稿填入「头像描述」输入框并提示可修改后保存；未点保存时设置 MUST 保持原值

#### Scenario: 关闭即弃

- **WHEN** 出卡后用户未点采纳直接关闭
- **THEN** 「头像描述」输入框保持原值，无任何内容被写入

#### Scenario: 角色归属校验

- **WHEN** 请求的角色不属于当前用户或本书
- **THEN** 端点 MUST 返回 400，不发起模型调用

#### Scenario: 坏 JSON 可重试

- **WHEN** 模型返回非 JSON 或 look 为空
- **THEN** 端点 MUST 返回 502 且文案含「可重试」；调用账目 SHALL 记失败行

#### Scenario: 素材白名单与不编造

- **WHEN** 组装起草请求
- **THEN** 发送内容 SHALL 只含五类角色卡白名单素材（各按上限截断），MUST NOT 含正文、章纲、dossier.background/plot；模板 SHALL 要求素材没有的特征不凭空定死
