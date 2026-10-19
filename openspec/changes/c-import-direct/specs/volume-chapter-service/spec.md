## ADDED Requirements

### Requirement: 导入结构一次成型与连续切分校验

- 导入建书 SHALL 接收第 2 步确认的结构 `volumes: [{title, chapter_from, chapter_to}]`，并在一次事务内按位置创建卷与章；卷号 SHALL 按位置从 1 连续分配，卷名自由文本（空则回落「第N卷」）。
- 服务端 SHALL 校验结构覆盖全部活动章 1..M，不重不漏：`chapter_from` 必须紧接上一卷 `chapter_to+1`，首卷从 1 开始，末卷到 M 结束，每卷至少 1 章。
- 结构不合法（缺口、重叠、空卷、越界）SHALL 返回 400 并指出具体卷/章范围；SHALL NOT 部分建书、SHALL NOT 静默修正分卷。
- 忽略/删除章节 SHALL 只发生在导入落库之前；落库后 SHALL NOT 提供删章，避免重排 `chapter_no/ref` 破坏 last_write 与归档引用。

#### Scenario: 结构缺口被拒绝
- **WHEN** 提交 1–12 / 14–42 两卷（缺第 13 章）
- **THEN** 返回 400 并指出缺口在第 13 章，不创建任何卷/章

#### Scenario: 连续结构一次建书
- **WHEN** 提交 1–24 / 25–42 两卷并导入正文
- **THEN** 生成 2 卷 42 章，卷号 1/2 按位置分配，正文逐章落库，书立即可打开

#### Scenario: 落库后不删章
- **WHEN** 作者打开已导入书的第 10 章
- **THEN** 不提供删章动作；接口也拒绝删除有正文的导入章

### Requirement: 历史章来源与全书章号

- 导入落库的章 SHALL 写不可变 `origin=import` 与 `imported_at`；SHALL NOT 写新的 `status=imported` 值；章状态仍使用既有 draft/confirmed/archived。
- 存储 SHALL 保留卷内章号 `chapter_no` 与稳定 `ref`；界面/提示词 SHALL 使用由卷序＋卷内序派生的 `global_no`，SHALL NOT 把全书号写入存储或重排 ref。
- 标题入库前 SHALL 剥掉「第X章/第X回/第X节」序号，展示时拼一次；卷标题剥「第N卷」序号，显示时拼「第N卷 · 卷名」或「第N卷」。
- 历史章 SHALL 可编辑、可单章归档；归档只改 status，origin 保留，不触发全书号重排。

#### Scenario: 全书号展示
- **WHEN** 第 2 卷第 3 章在存储中为卷内第 3 章
- **THEN** 界面显示「全书第 27 章」，标题为「归乡」而不是「第3章 归乡」重复序号

#### Scenario: 编辑历史章
- **WHEN** 作者修改一个 origin=import 章的正文并保存
- **THEN** 保存成功，origin 仍为 import，chapter_no/ref 不变，续写仍落 N+1

### Requirement: 导入原子 writer 与幂等

- 直接导入 SHALL 使用独立的事务级 writer：书、卷、章、正文、`import_token` 在同一 session/事务内写入；SHALL NOT 复用会自行 commit 的建书/存章服务。
- 写入 SHALL 显式计算 `word_count`、`has_prose`、`outline_status`；SHALL NOT 依赖 repository upsert 的默认零值。
- 同一 `import_token` 重试 SHALL 返回同一本书，SHALL NOT 重复建卷/章；失败 SHALL 整笔回滚。

#### Scenario: 失败整笔回滚
- **WHEN** 240 章导入在第 120 章写入失败
- **THEN** 数据库中没有该书的卷/章/正文，重试从零开始且不重复

#### Scenario: 重复提交幂等
- **WHEN** 同一 import_token 因超时重试
- **THEN** 返回同一 book id，卷/章不重复，`word_count/has_prose` 正确
