## ADDED Requirements

### Requirement: 文字层提取步与分段落卡

- 蒸馏 SHALL 在既有三步之后增加第四请求内端点 `POST /settings/ai/style-distill/step4`（文字层提取），对同一份已装配样本提取两层草稿：
  - 三区草稿：`role`（叙事身份一句话）＋`rules`（可执行写作规则条目）＋`craft`（表现手法条目）；样本中「刻意避免的写法」SHALL 转「避免…」句式并入 rules 草稿；
  - 示范段：0–6 条**逐字原文段**（单条 ≤200 字，样本不足时可以少；样本中对话与叙述两种形态皆存在时，示范段 SHALL 各覆盖至少一条；只取样本原文，禁止自造、改写或删节拼接）。
- step4 的样本供给 SHALL 由请求重供：前端每次调用 step4 SHALL 随请求携带样本上下文（粘贴 `text` 或文件/章节勾选，与 step1 同一 body）。step4 的 `text` 参数 SHALL 只作样本供给，MUST NOT 触发 step1 的「`text` 非空＝清空 draft 重启」语义（同名参数、语义相异，SHALL 进钉子测试）；draft 无 step1 产物或样本不可供时 SHALL 返回 400（文案指向先完成第一步）。
- step4 产物 SHALL 写入 `style-quant.draft` 并按既有续跑语义执行：中断后重开 SHALL 跳过已完成步骤；存量 draft（无 step4 产物）续跑时 SHALL 补跑 step4；粘贴重启清空 draft 的语义对 step4 同样适用。
- step4 SHALL 挂与三步同款的会员门控（免费 403 `member_required`）与本书模型就绪依赖；step4 失败 SHALL 可单独重试且 MUST NOT 影响已完成的 step1–3 产物。
- 本机已装提示词包缺 `style_learn_extract` 模板时（客户端新于包的版本斜坡窗口），step4 SHALL 返回结构化错误（提示联网更新提示词包），SHALL NOT 以 500 形态暴露；确认卡文字层段 SHALL 呈现降级文案，三步基线路径与落卡 MUST NOT 受影响。
- step4 SHALL 支持 force 重提（保留 step1–3 产物，仅重产文字层草稿）；确认卡文字层段 SHALL 提供「重新提取」入口，与 step3「不像，再学一次」互不影响。
- 确认卡 SHALL 在六行基线预览之外分段呈现文字层：三区草稿（可编辑：身份一句＋规则列表＋手法列表）与示范段（只读段落＋可删条目）；用户 SHALL 对「基线」「三区草稿」「示范段」三段各自独立采纳或弃采，未采纳段 SHALL 零写回。
- 采纳写边界：三区草稿采纳 SHALL 经文风 KV 白名单写（role/rules/craft 替换，编辑后的 taboo「避免…」行随 rules），示范段采纳 SHALL 写 `style_samples`（≤6 条、单条截 500 字、替换语义）；两段采纳 SHALL 在写前回读文风 KV 合并（MUST NOT 覆盖用户未保存的禁用词/句式编辑），并 SHALL 挂回执可一键撤销；采纳 SHALL 同步表单态并重置脏快照基线（避免后续表单保存回踩采纳值或误报脏）；基线采纳走既有 commit，语义不变。
- 「不像，再学一次」重跑 step3 时，SHALL NOT 自动清掉已采纳的文字层（采纳发生在文风 KV，与 draft 生命周期解耦）。

#### Scenario: 学全三层落卡

- **WHEN** 用户粘贴 5,000 字参考书文本完成蒸馏，确认卡上依次采纳基线、三区草稿（微调两条规则）、示范段（删 1 条留 4 条）
- **THEN** 量化正式区出 v(N+1) 快照；文风 KV 的 role/rules/craft 为编辑后草稿；style_samples 为余下 4 条；三条 ChangeReceipt 均可分别撤销

#### Scenario: 只采纳示范段

- **WHEN** 用户对基线点「不落卡」、三区草稿弃采，仅采纳示范段
- **THEN** style-quant 正式区与文风三区零变化，仅 style_samples 被替换；draft 照常保留（基线可稍后单独落卡）

#### Scenario: 三区替换可撤销

- **WHEN** 本书原三区为手写内容，用户采纳三区草稿后点回执撤销
- **THEN** role/rules/craft 恢复采纳前内容，撤销动作有 toast 确认

#### Scenario: 采纳不覆盖未保存的禁用词

- **WHEN** 用户在表单态改了禁用词未保存，随即采纳三区草稿
- **THEN** 采纳写回基于服务端最新文风 KV 合并，未保存的禁用词编辑不被覆盖丢失

#### Scenario: 存量 draft 补跑 step4

- **WHEN** 旧 draft 停在 step3 完成（无 step4 产物），用户重开蒸馏面板
- **THEN** 系统只跑 step4（不重复调用 step1–3），确认卡照常呈现文字层两段

#### Scenario: step4 失败不影响基线落卡

- **WHEN** step4 返回 502，用户重试一次仍失败，随后直接落卡基线
- **THEN** 基线照常 commit 成功；step4 可稍后单独重试，重试只产文字层草稿

#### Scenario: 粘贴重启清空文字层草稿

- **WHEN** draft 已含 step4 产物，用户粘贴新文本重启蒸馏
- **THEN** draft 全部旧产物（含 step4）清空，文字层草稿按新样本重新提取

#### Scenario: step4 的 text 不触发清空重启

- **WHEN** draft 已有 step1–3 产物，前端携带与 step1 相同的粘贴 `text` 调用 step4
- **THEN** draft 旧产物原样保留、只新增 step4 草稿；样本不足区间或非字符串的 400 行为与 step1 同口径但不产生任何清空

#### Scenario: 旧包缺模板降级

- **WHEN** 本机提示词包为旧版（无 style_learn_extract），用户点「学文字层」
- **THEN** 文字层段呈现「更新提示词包后可用」降级文案；step1–3 与基线落卡照常可用，SHALL NOT 出现 500

#### Scenario: force 重提只重摇文字层

- **WHEN** 用户对文字层草稿不满意点「重新提取」
- **THEN** 仅 step4 重跑（step1–3 产物与已落卡基线不动），确认卡文字层两段刷新

#### Scenario: 免费用户与未配模型

- **WHEN** 免费用户或未配模型的本书调用 step4
- **THEN** 分别返回 403 member_required 与结构化模型错误，文风 KV 与 style-quant 均零写入
