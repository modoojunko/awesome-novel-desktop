## ADDED Requirements

### Requirement: AI 拆书入口与模型/配额门

系统 SHALL 在第 3 步提供「AI 拆书」卡：显示当前模型名、token/时间估算、全文发送给模型服务商、按作者 Key 计费、±30% 浮动、取消/失败/重跑已消耗 token 不退。AI 卡 SHALL 启用并结束 A 路「即将开放」临时态。未配置模型时 SHALL 置灰并给「去配置」；书架配额不足时 SHALL 在创建任务前提示并禁用，提供归档/删除/升级出口。创建任务 SHALL 预占 1 个书位，取消/失败释放，开书转正式书位。

#### Scenario: 未配置模型
- **WHEN** 作者进入第 3 步且没有可用模型
- **THEN** AI 卡显示「未配置模型，拆书不可用」并不可选，直接导入仍可选

#### Scenario: 书架已满
- **WHEN** 书架配额已满
- **THEN** 第 3 步显示「书架已满」与可执行出口，创建按钮禁用；两条路都不进入长时间等待

#### Scenario: 预占与释放
- **WHEN** 作者创建 AI 拆书任务后取消
- **THEN** 预占的书位释放；任务删除后不残留预占

### Requirement: 拆书任务来源、状态与交接

任务 SHALL 记录 `source=import|manual`；任务清单 SHALL 按来源分「导入 / 拆书」并支持筛选；导入任务详情页头标「导入」；导入任务 SHALL NOT 提供导出出口。创建后 SHALL 落到写作工具任务清单/详情并显示交接通知：拆书在应用内继续、可以离开页面、不要关闭应用（关闭会暂停，下次打开继续）。完成态 SHALL 显示「已完成·待开书」＋「开书」；已开书 SHALL 显示「已开书」＋「进入书内」。

#### Scenario: 导入后找任务
- **WHEN** 作者确认 AI 拆书
- **THEN** 落到写作工具任务清单/详情，显示交接通知；不出现「后台会跟进」

#### Scenario: 完成确认
- **WHEN** 拆书完成
- **THEN** 任务行显示「已完成·待开书」与「开书」，应用内同时给完成提示

#### Scenario: 导入任务无导出
- **WHEN** 作者打开 source=import 的任务详情
- **THEN** 不出现建书/存文件夹/导出入口，只出现「开书」

### Requirement: Manifest 管线与续拆

拆书任务 SHALL 使用创建时冻结的 manifest（`source_sha256`、`parser_version`、逐章 `source_idx/char_start/end`）切片，SHALL NOT 重新解析源文件。忽略/删除只发生在导入前；活动章序 SHALL 与 manifest 一致。续拆时若源 sha 不一致 SHALL 返回 `need_reupload`；parser_version 不一致 SHALL 拒绝续拆或要求重建任务。

#### Scenario: 忽略章后卡不偏移
- **WHEN** 作者在第 2 步不导入第 5 章，拆书任务随后运行
- **THEN** 41 个活动章按 manifest 的正确区间出卡，基线 ref 不偏移

#### Scenario: 源文件变化
- **WHEN** 任务续拆时源文件 sha 与 manifest 不一致
- **THEN** 返回 need_reupload，不写新卡片/基线

### Requirement: 大书分段先验证

超过约 60 万字的书 SHALL NOT 被字数上限拒绝。实施前 SHALL 用现有管线对 180 万字/240 章做技术验证：若现有管线可完成，SHALL 删掉外层分段，仅保留章级断点；若确有硬限，SHALL 采用两遍式：每段只跑逐章卡，全部段完成后用全量卡片跑一次十维归并，SHALL NOT 每段独立跑十维。任务详情 SHALL 显示段进度（若有段）；段失败 SHALL 只重跑该段。

#### Scenario: 现有管线可跑大书
- **WHEN** 180 万字/240 章在现有管线完成
- **THEN** 任务不分段，按章级断点续跑；费用/时间按实际调用累加

#### Scenario: 必须分段
- **WHEN** 实测存在硬限，任务分 3 段
- **THEN** 任务详情显示「第 X/3 段」，段 2 失败只重跑段 2，段 1/3 不重复

### Requirement: 逐章导入基线（有损）

开书 SHALL 用拆书卡为每章写 `chapter_import_baseline`：摘要、世界可见项、角色/出场、可见关系、伏笔动作；SHALL NOT 把可见状态写进 `chapter_*_changes`（那是归档提取的「变化」）。v1 SHALL 接受有损基线：coverage 对世界/关系/角色标 `partial`，伏笔/摘要按实际，物品/认知标 `not_extracted`，`evidence_absent=true`；回执 SHALL 明示「基于每章首尾约 6000 字、无证据句、物品/认知未提取」。补算 SHALL 只补缺失域，不替换已采纳行、不归档。

#### Scenario: 开书写入基线
- **WHEN** B 路拆书完成并为 42 章开书
- **THEN** 每章有基线摘要/世界/角色/关系/伏笔动作；coverage 标 partial/not_extracted；无 42 次新提取

#### Scenario: 补算不替换
- **WHEN** 作者对第 7 章点「补齐本章」的物品域
- **THEN** 只补物品，原有摘要/关系/角色基线不变，章不自动归档

### Requirement: 开书确认、执行与回执

AI 拆书完成后 SHALL 提供确认 → 执行 → 回执：确认页只读结构并显示将写入项，作家可改书名，可「调整结构」回第 2 步（尚未建书）；执行态 SHALL 在超过 5 秒时只显示一条真实计数（如正在写入 18/42 章），≤2 秒直接按钮 loading，2–5 秒不定量 loading；回执列明写入项、未写入项、未提取域，并提供「进入书内」到工作台第 N+1 章。开书 SHALL NOT 调用模型、SHALL NOT 播种设定。

#### Scenario: 开书前调整结构
- **WHEN** 作者在确认页发现分卷不对
- **THEN** 可点「调整结构」回第 2 步修改，确认后重新开书，不必删任务重来

#### Scenario: 快开书
- **WHEN** 开书在 2 秒内完成
- **THEN** 不显示进度页，按钮 loading 后直接给回执

#### Scenario: 慢开书
- **WHEN** 开书超过 5 秒
- **THEN** 只显示一条真实写入计数，不显示内部实现清单；完成后给回执

#### Scenario: 回执进入书内
- **WHEN** 作者点回执「进入书内」
- **THEN** 进入工作台第 N+1 章待写位，不是设定页

### Requirement: 开书 claim 与崩溃恢复

开书 SHALL 使用原子 claim + 租约（`open_claim_token/open_claim_at`）与阶段回执（validate/book/settings/baselines/chapters/receipt）。同一任务 SHALL 只有一个写者；进程在 `opening` 崩溃后，启动 sweep SHALL 把过期 claim 收敛为 `partial` 并允许继续。部分书 SHALL NOT 在书架露出；任务行 SHALL 显示「开书未完成·继续开书」；部分书占书位，删除时必须书+任务一起处理，不得留隐藏书。

#### Scenario: 并发开书
- **WHEN** 两个入口同时点开书
- **THEN** 只有一个 claim 成功，另一个显示「正在开书」，不重复建书

#### Scenario: 开书中断
- **WHEN** 开书到章节阶段进程被杀，重启后继续
- **THEN** 从阶段回执继续，不重复建书/设定/章节，最终完成

#### Scenario: 部分书不可见
- **WHEN** 开书处于 partial 且书已建
- **THEN** 书架不显示该书；任务行显示继续入口；删除任务时要求同时删部分书

### Requirement: 失败或取消后的降级开书

AI 拆书失败或取消后，系统 SHALL 在任务行提供「只导入正文（跳过设定）」：按确认结构只导入章节（历史章），设定留空；SHALL NOT 另建空书、SHALL NOT 声称后台继续。进行中任务 SHALL NOT 提供该入口；重复点 SHALL 返回同一本书。

#### Scenario: 拆书失败仍能开书
- **WHEN** 任务失败，作者点「只导入正文（跳过设定）」
- **THEN** 生成一本只有卷/章/正文的书，任务关联该书，回执明示设定未写入

#### Scenario: 进行中不提供跳过
- **WHEN** 任务仍在拆解中
- **THEN** 不出现该入口，只提供查看进度/取消

### Requirement: 费用与隐私告知

AI 拆书卡 SHALL 显示 token 估算（全书字数 ×1.5–2.5，按段/重试累加）、时间估算（0.5–0.8 分钟/章＋8–10 分钟收尾，±30%）与「由你的模型服务商按 Key 计费」；SHALL 明示全文会发送给作者配置的模型服务商；本机模型 SHALL 改为「不离开本机」。取消/失败/重跑已产生的调用不退 SHALL 在 CTA 上方常显。拆书源文件 staging SHALL 在开书完成/任务删除后按 TTL 清理，作者可手动删除。

#### Scenario: 费用可见
- **WHEN** 作者进入第 3 步
- **THEN** AI 卡显示模型名、token/时间范围、±30%、计费主体、取消不退

#### Scenario: 隐私告知
- **WHEN** 作者选择 AI 拆书
- **THEN** 页面明示全文将发送给其配置的模型服务商；选择本机模型时改为不离开本机
