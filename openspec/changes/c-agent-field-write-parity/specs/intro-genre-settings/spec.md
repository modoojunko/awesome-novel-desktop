## ADDED Requirements

### Requirement: agent 字段级写题材 02-05 走页面契约

agent 的 `write_settings_field` 写题材面板 SHALL 使用设定页 02-05 的可见字段映射与写链契约：

- 字段映射 SHALL 为：02 主要看什么＝`promise_note`（主句，≤200 字）；`core_promise` 是页面「标签」行（给作家省字的短标签，≤60 字），SHALL NOT 由 agent 字段写直接改——标签走 `settings_genre_core_promise` 采纳卡；03 绝对禁止＝`forbidden_list`；04 吃苦指数＝`cost_ratio`；05 本小说斗什么＝`battlefield`。
- 授权卡与工具说明的字段名 SHALL 与页面小标题一致（主要看什么／绝对禁止／吃苦指数／本小说斗什么）；SHALL NOT 出现「核心承诺／禁忌／代价设定／战场」等页面找不到的旧名。工具枚举 SHALL NOT 包含 `core_promise`。
- 写入 SHALL 与前端面板同源走 `NovelGenreIn` 校验：`forbidden_list` 为 `[{tagId|text}]`、`battlefield` 为字符串数组且自定义项 ≤20 字、`cost_ratio` 为 1-10 整数；违规值 SHALL NOT 落库。
- 授权卡 preview SHALL 按上述契约预校验；注定写不进去的值 SHALL NOT 弹卡，SHALL 以人话理由回喂模型改对再来。
- agent 试图直接写 `core_promise` 时 SHALL NOT 弹卡，SHALL 提示「标签走出爽点采纳卡，主句写 promise_note」。

#### Scenario: 主要看什么落到主句
- **WHEN** 作家说「把主要看什么改成『主角靠算计翻盘』」，agent 调 write_settings_field 写 `genre.promise_note`
- **THEN** 授权卡字段名显示「主要看什么」，写入后 02 主输入框显示该句，`core_promise` 短标签保持现值

#### Scenario: 标签槽不直接写
- **WHEN** agent 试图直接写 `genre.core_promise`
- **THEN** SHALL NOT 出现授权卡；助手收到「标签走出爽点采纳卡，主句写 promise_note」的人话理由，改走主句或采纳卡

#### Scenario: 列表与数值形状不合规不弹卡
- **WHEN** agent 写 `forbidden_list` 时传纯字符串数组、写 `battlefield` 时传单个字符串、或写 `cost_ratio` 越界（如 11）
- **THEN** SHALL NOT 出现授权卡；助手收到对应的人话拒绝理由（形状/上限/范围），改对后再请求
