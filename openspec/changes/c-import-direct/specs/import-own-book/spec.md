# import-own-book — 导入自有书（直接导入）

## Purpose

让存量作者把自己的 txt 正文一次搬进产品并继续写：确认卷章后立即建书，导入的是可编辑但不阻塞续写的历史章，续写永远从全书 N+1 开始；本阶段不调用模型、不建拆书任务。

## ADDED Requirements

### Requirement: 三步导入向导

系统 SHALL 在书架提供「导入我的书」三步向导：①选文件 ②确认卷章 ③导入方式。仅接受 `.txt`；单文件 ≤50MB；字数不设上限；上传前常显格式要求、样例与下载示例。A 路本期 SHALL 提供「直接导入」；AI 拆书卡由后续 change 启用，未启用前显示「即将开放」且不可点。A 路的第 3 步 SHALL NOT 要求模型配置，也 SHALL NOT 创建拆书任务。

#### Scenario: 选择 txt 并检查格式
- **WHEN** 作者选择一份符合格式的 `.txt`
- **THEN** 系统就地显示编码、字数、章节标题识别结果与结构判定，并允许进入第 2 步

#### Scenario: 非 txt 或超限文件
- **WHEN** 作者选择 `.md` / `.docx` / `.epub` 或超过 50MB 的文件
- **THEN** 系统拒绝并说明第一期仅支持 ≤50MB 的 `.txt`，不进入下一步

#### Scenario: A 路第 3 步提供直接导入
- **WHEN** 作者进入 A 路的第 3 步
- **THEN** 出现「直接导入（只带正文）」；AI 拆书卡显示「即将开放」且不可点；不出现模型配置要求

### Requirement: 按章切分的卷章确认

系统 SHALL 把卷定义为章节序列上连续的一段；第 2 步只允许在章与章之间新增切线、移动边界、合并、改名、折叠，以及把误识别章标记为「不导入」。SHALL NOT 允许单章跨卷搬动；卷必须覆盖全部活动章且每卷至少 1 章。结构判定 SHALL 区分 ok/warn/risk：warn 显示具体问题但可继续；risk 必须勾选「我了解质量风险，仍要导入」。

#### Scenario: 原文有卷
- **WHEN** 文件识别出 2 卷 42 章
- **THEN** 右侧按原卷切线预填 1–24 / 25–42，作者不调整可直接下一步

#### Scenario: 原文无卷
- **WHEN** 文件没有卷标题
- **THEN** 右侧为空且下一步禁用；作者点「+ 新增卷」得到 1 卷「正文」（1–N），再可在第 X 章后分卷

#### Scenario: 切分与合并
- **WHEN** 作者在 42 章的一卷上「在第 12 章后分卷」
- **THEN** 得到 1–12 / 13–42 两卷；「少一章/多一章」只移动边界且两卷都保持非空；「合并到下一卷」恢复为一卷

#### Scenario: 忽略误识别章
- **WHEN** 作者把第 5 章标记为「不导入」
- **THEN** 该章不进入新书，活动章序重排为 1..41，卷边界按活动章序保持连续

#### Scenario: 结构风险需显式确认
- **WHEN** 解析判定为 risk（如未识别到章节标题的大部头）
- **THEN** 系统显示具体问题与确认勾选，未勾选时不允许进入下一步

### Requirement: 直接导入不调用模型

「直接导入」SHALL 立即建书并按确认结构落卷/章/正文；SHALL NOT 调用模型（0 token）；SHALL NOT 播种设定模板；简介 SHALL 以第一章前 200 字机械填入并标「自动识别」，题材留空；SHALL NOT 预生成第 N+1 章章纲。

#### Scenario: 直接导入成功
- **WHEN** 作者选择直接导入并确认
- **THEN** 新书按确认结构生成卷/章/正文，作者可立即进入第 N+1 章；设定页不出现模板默认值

#### Scenario: 直接导入的代价
- **WHEN** 作者进入第 3 步
- **THEN** 卡片明示「伏笔/钩子/设定变化不会带过来；之后只能手动补设定，不含逐章 AI 补齐」

#### Scenario: 大书不按字数拒绝
- **WHEN** 作者导入 180 万字/240 章的 txt
- **THEN** 系统按 50MB 文件上限判断（未超限即接受），不因字数拒绝；落库分批进行

### Requirement: 历史章与续写落点

导入章 SHALL 记录不可变 `origin=import` 与 `imported_at`；SHALL NOT 新增 `status=imported` 值；历史章 SHALL 由 `origin=import && status!=archived` 派生。作者 SHALL 可编辑历史章；frontier SHALL 跳过历史章；续写 SHALL 落在全书 N+1；书本阶段 SHALL 保持写作中，历史章不参与「待完本」计数。作者可对单章「归档本章」转 archived，origin 保留，阶段仍不前进。

#### Scenario: 导入后继续写
- **WHEN** 一本 42 章的书导入完成
- **THEN** 点「续写」打开全书第 43 章；第 1 章和中间导入章不会被当作当前写作章

#### Scenario: 编辑导入章
- **WHEN** 作者修改第 10 章正文并保存
- **THEN** 保存成功，origin 仍为 import，续写仍落第 43 章；不出现「草稿/已确认」把历史语义顶掉

#### Scenario: 单章归档
- **WHEN** 作者对第 3 章点「归档本章」
- **THEN** 该章转 archived，origin 仍为 import；全书阶段仍为写作中，不因导入章归档进入待完本

### Requirement: 全书章号

系统 SHALL 由卷序＋卷内章序派生 `global_no`，SHALL NOT 把全书号写入存储或重排 `chapter_no/ref`；frontier、章节树、预览、拆章素材与新建章默认标题 SHALL 使用 `global_no`。

#### Scenario: 两卷 42 章
- **WHEN** 第 2 卷第 3 章在存储中为卷内第 3 章
- **THEN** 界面显示「全书第 27 章」；待写位显示「全书第 43 章」

#### Scenario: 新建下一章
- **WHEN** 42 章导入后作者新建下一章
- **THEN** 新章 ref 仍按卷内号生成，界面标题为「第 43 章」，不出现「第19章」

### Requirement: 原子落库与幂等

直接导入 SHALL 在一个事务内完成书/卷/章/正文/导入令牌；任一写入失败 SHALL 整笔回滚，不留下半本书；同一 `import_token` 重试 SHALL 返回同一本书，SHALL NOT 重复建卷/章。批量插入 SHALL 显式写 `word_count`、`has_prose`、`outline_status`。

#### Scenario: 中途失败回滚
- **WHEN** 240 章导入在第 120 章注入写入失败
- **THEN** 数据库中没有该书的任何卷/章/正文，作者可重试

#### Scenario: 重复提交
- **WHEN** 作者因网络超时对同一导入点两次确认
- **THEN** 只存在一本同 token 的书，卷/章不重复，第二次返回同一 book id

### Requirement: 书架配额门

创建 A 路书前 SHALL 检查书架配额；已满时 SHALL 在导入向导内提示并禁用创建，提供归档/删除/升级出口；SHALL NOT 等到导入完成才返回 403。A 路 SHALL NOT 要求模型配置。

#### Scenario: 书架已满
- **WHEN** 书架配额已满
- **THEN** 第 3 步显示「书架已满」与可执行出口，创建按钮禁用，文件与结构不丢失

### Requirement: 生命周期与成功落点

v1 SHALL 只在导入前允许忽略/删除章节；落库后 SHALL NOT 提供删章，提供「删除本书重新导入」出口。A 路成功后 SHALL 进入工作台并选中第 N+1 章待写位，主 CTA「开始写第 N+1 章」，次 CTA「去核对设定」；因 A 路没有主线/卷纲，SHALL 提供「补主线 / 补当前卷卷纲」清单。

#### Scenario: 导入成功落点
- **WHEN** 42 章直接导入成功
- **THEN** 进入工作台第 43 章待写位，主按钮为「开始写第 43 章」，右侧有补主线/卷纲清单

#### Scenario: 落库后不删章
- **WHEN** 作者打开一本已导入书的第 10 章
- **THEN** 没有删章按钮；如需重来，只能「删除本书重新导入」

### Requirement: 旧导入入口退役与旧书回填

系统 SHALL 以新向导替换旧书架导入；第一期 SHALL NOT 提供 md/docx 导入；旧 `/import/persist` SHALL NOT 作为前端入口。对 `source=import` 且能证明章与书创建于同一导入批次的旧书，backfill SHALL 只把该批次内的章标为 `origin=import`（status 不变），续写 SHALL 落 N+1，预览 SHALL 标「原文」。SHALL NOT 无差别改写书的全部章：备份恢复（书创建时间远早于恢复出的章）或导入后作者续写的章 SHALL 保持 `authored`。

#### Scenario: md/docx 用户
- **WHEN** 作者选择 md/docx
- **THEN** 界面明确第一期不支持且不提供转换；旧入口不再出现

#### Scenario: 旧导入书
- **WHEN** 打开一本旧版本导入的书
- **THEN** 其导入批次内的非归档章 origin=import、续写落 N+1、预览标原文；不是回到第 1 章

#### Scenario: 导入后作者续写
- **WHEN** 旧导入书里存在导入完成之后作者新建的章
- **THEN** 该章保持 origin=authored，不被 backfill 误标为历史章，仍参与完本计数

#### Scenario: 备份恢复的书
- **WHEN** 一本作者书从备份包恢复（书创建时间远早于恢复出的章）
- **THEN** 所有章保持 origin=authored；backfill 不把整本书改写成历史章

### Requirement: 费用与隐私告知

直接导入 SHALL 标 0 token、秒级完成、只在本机解析/入库、不发送正文给模型服务商。作者成功页 SHALL 明示「设定留空、伏笔/钩子不会带过来」。

#### Scenario: 费用可见
- **WHEN** 作者进入第 3 步
- **THEN** 直接导入卡显示「0 token · 只在本机处理」，不出现模型/Key 要求

#### Scenario: 隐私告知
- **WHEN** 作者选择直接导入
- **THEN** 页面明示正文只在本机解析入库，不发送给模型服务商
