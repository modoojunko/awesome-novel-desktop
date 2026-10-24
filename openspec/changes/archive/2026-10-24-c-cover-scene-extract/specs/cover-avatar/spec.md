## MODIFIED Requirements

### Requirement: 图与书/角色单一归属与 prompt 白名单

系统 SHALL 把封面归属到书、头像归属到角色；封面 prompt MUST 只读题材气质、核心承诺、世界舞台、用户 cover_prompt；头像 prompt MUST 只读角色卡的性别/年龄/种族、外貌、势力/身份、一句话人设，并可继承书级 style_key/model/provider。MUST NOT 把书名、角色名、简介原文、正文、章纲、dossier.background、dossier.plot 送入图像 prompt；书名/角色名 SHALL 只出现在 `sources` 供 UI 叠加。prompt 预览端点 SHALL 返回 positive prompt、negative_prompt、prompt_hash、prompt_template_version、style_key、size、seed、candidate_seeds、model、provider、capabilities、sources。seed MUST NOT 由用户提供：封面/头像 seed 一律按书/角色 id 确定性派生（同书/角恒定），`seed_source` SHALL 恒为 `derived`。

#### Scenario: 头像不泄露角色背景

- **WHEN** 角色卡 background/plot 填了剧情剧透
- **THEN** 头像 prompt MUST 不包含这些字段，只包含外貌/身份/人设等白名单字段

#### Scenario: 书名不画成画面文字

- **WHEN** 书的名称是「夜明铺」
- **THEN** 封面 prompt MUST 不包含「夜明铺」；sources.name SHALL 仍返回书名供 UI 后置叠加

#### Scenario: prompt_hash 可复现

- **WHEN** 同一书/角色、同一模板版本、同一 prompt/negative/size/model 再次预览
- **THEN** prompt_hash MUST 相同；只改 prompt 或模型时 hash MUST 变化，seed 不随设置漂移

#### Scenario: 老客户端残留种子字段被忽略

- **WHEN** 旧版客户端 PUT/PATCH 设置时仍携带 `cover_seed` 或 `seed`
- **THEN** 服务端 MUST 静默忽略该字段（不报错、不落库、响应不回显）

### Requirement: 图像设置读写

系统 SHALL 提供每书 `image_config_id/image_model/style_key/cover_prompt` 与角色 `avatar_prompt` 的读写；绑定配置 MUST 属于当前用户且未删除。`PUT` 为全量写入；`PATCH` SHALL 只更新显式提交字段，未提交字段 MUST 保留。style_key 不在支持列表 MUST 返回 400 `invalid_style`。

#### Scenario: 绑定不存在的配置

- **WHEN** 用户把书绑定到不属于自己的 image_config_id
- **THEN** 系统 MUST 返回 400，不写入设置

#### Scenario: PATCH 只改模型

- **WHEN** 用户 PATCH 只提交 `image_model`
- **THEN** `style_key` 与 `cover_prompt` MUST 保持原值

#### Scenario: 读回角色设置

- **WHEN** 用户保存角色 `avatar_prompt` 后重新 GET 角色设置
- **THEN** 响应 SHALL 原样返回该字段

### Requirement: 设置部分更新

前端 SHALL 用 `PATCH /api/novels/{id}/image-settings` 与 `PATCH .../characters/{cid}/image-settings` 做部分更新；只改模型时 MUST NOT 清空画风、封面描述或头像描述。

#### Scenario: 只换本书模型

- **WHEN** 用户 PATCH 只提交 `image_model`
- **THEN** 前端 MUST NOT 提交未改动字段；保存后画风与封面描述 MUST 保持原值

## ADDED Requirements

### Requirement: 封面画面 AI 提取

系统 SHALL 提供端点 `POST /api/novels/{id}/image-prompt/cover-extract`，从书级白名单素材（选题 genre/sub_genre、一句话故事 promise_note、简介 synopsis、主线 story_arc.fullstory、世界舞台 stage）经提示词仓模板 `image_cover_scene` 蒸馏出一段封面画面场景草稿。端点 MUST 挂 `image-generate` 权益门与书模型就绪门（未就绪 503，`reason` 与前端 `ai_state` 同枚举；非本书 404）。模板 MUST 来自提示词仓（缺包沿既有 503 `prompts_missing` 语义）；模型输出 MUST 按严格 JSON 契约解析（`{"scene": ...}`），解析失败或空 scene MUST 返回 502 可重试错误。草稿 SHALL 只返回给前端填充「画面描述」输入框（用户可改、显式保存才落库），MUST NOT 直接写入设置或触发生成任务。产出场景 MUST 遵守模板硬约束：画面无文字载体、人物只作剪影/背影/远景、不出现书名/角色名/势力名专名、不剧透关键反转。

#### Scenario: 提取草稿填充画面描述

- **WHEN** PRO 用户在封面工坊点「AI 提取」
- **THEN** 端点 SHALL 返回 `{scene}`，前端 SHALL 把草稿填入「画面描述」输入框并提示可修改后保存；未点保存时设置 MUST 保持原值

#### Scenario: 书模型未就绪

- **WHEN** 本书未绑定可用的写作大模型配置
- **THEN** 端点 MUST 返回 503，`detail.reason` 为 ai_state 枚举值，前端按既有四态卡引导

#### Scenario: 坏 JSON 可重试

- **WHEN** 模型返回非 JSON 或 scene 为空
- **THEN** 端点 MUST 返回 502 且文案含「可重试」；调用账目 SHALL 记失败行

#### Scenario: 素材白名单

- **WHEN** 组装提取请求
- **THEN** 发送内容 SHALL 只含五类书级素材（各按上限截断），MUST NOT 含正文、章纲、角色 dossier
