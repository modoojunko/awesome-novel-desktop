## ADDED Requirements

### Requirement: 导入结构一次成型与连续切分校验

- 导入建书 SHALL 接收第 2 步确认的结构 `volumes: [{title, chapter_from, chapter_to}]`，并在一次事务内按位置创建卷与章；卷号 SHALL 按位置从 1 连续分配，卷名自由文本（空则回落「第N卷」），章 ref SHALL 稳定且可定位到卷内章序。
- 服务端 SHALL 校验结构覆盖全部活动章 1..N，不重不漏：`chapter_from` 必须紧接上一卷 `chapter_to+1`，首卷从 1 开始，末卷到 N 结束，每卷至少 1 章，卷名不重复不强制但不得为空。
- 结构不合法（缺口、重叠、空卷、越界）SHALL 返回 400 并指出具体卷/章范围；SHALL NOT 部分建书、SHALL NOT 静默修正分卷。
- 导入落库 SHALL NOT 播种设定模板（`seed_settings=false`）；书级设定未写入的项保持空白。
- 同一导入请求重试 SHALL 幂等：按导入令牌/书 id 去重，SHALL NOT 重复建卷、建章或重复写正文；失败时整笔回滚，不留下半本书。

#### Scenario: 结构缺口被拒绝
- **WHEN** 提交 1–12 / 14–42 两卷（缺第 13 章）
- **THEN** 返回 400 并指出缺口在第 13 章，不创建任何卷/章

#### Scenario: 连续结构一次建书
- **WHEN** 提交 1–24 / 25–42 两卷并导入正文
- **THEN** 生成 2 卷 42 章，卷号 1/2 按位置分配，正文逐章落库，书立即可打开

#### Scenario: 重试不重复
- **WHEN** 同一导入令牌因网络超时重试一次
- **THEN** 仍只有 2 卷 42 章，正文不重复，返回同一本书

#### Scenario: 无卷原文
- **WHEN** 原文没有卷标题，作者在第 2 步新增一卷「正文」
- **THEN** 服务端接受 1 卷 N 章的结构并正常建书

### Requirement: imported 章状态与章号标题归一

- 章节状态 SHALL 支持 `imported`（历史章），与 draft/archived 并列；导入落库的章 SHALL 使用 imported，SHALL NOT 使用 draft 或 archived。
- 卷章树、章详情、正文保存、删除、版本历史 SHALL 能读取/处理 imported 章；导入章 SHALL 可编辑、可单章归档、可删除（按既有删除链/引用规则）。
- 存储 SHALL 保留卷内章号；界面与提示词 SHALL 用「全书第 N 章」展示（由卷序＋卷内章序计算）；标题入库前 SHALL 剥掉「第X章/第X回/第X节」序号，展示时再拼一次，SHALL NOT 重复堆叠序号。
- 删除/忽略章节 SHALL 发生在导入落库之前；落库后删除导入章 SHALL 按既有删除规则处理引用与后续章序，SHALL NOT 留下指向已删章的基线孤儿。

#### Scenario: 导入章可保存
- **WHEN** 作者修改一个 imported 章的正文并保存
- **THEN** 保存成功，状态仍为 imported，版本历史照常记录

#### Scenario: 全书号展示
- **WHEN** 第 2 卷第 3 章在存储中为卷内第 3 章
- **THEN** 界面显示「全书第 27 章」，标题为「归乡」而不是「第3章 归乡」重复序号

#### Scenario: 删除导入章
- **WHEN** 作者删除一个 imported 章
- **THEN** 按既有删除规则移除该章及其章档引用，后续章序连续，不出现孤立基线
