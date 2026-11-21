## ADDED Requirements

### Requirement: DeepSeek 当前日期标记

OpenAI 协议的 DeepSeek 助手调用 SHALL 在当前 user 消息之前插入一条
`{"role":"latest_reminder","content":"<date>,<weekday>,<location>,<platform>,<language>"}`
消息，日期/星期取 Asia/Shanghai 本地日期、星期用中文、location 留空、platform=App、
language=中文（如 `2026-11-09,星期一,,App,中文`）。该消息 SHALL 只进当前轮外发窗口，
SHALL NOT 持久化进会话历史、SHALL NOT 进 compact 状态；其它 vendor（非 DeepSeek/openai）
SHALL NOT 收到该 role（未知 role 有被端点拒绝的风险）。窗口内该消息 SHALL 紧挨最后一条
user 消息之前；历史轮次的 user 消息前不补插。

#### Scenario: 当前轮插在 user 消息前
- **WHEN** DeepSeek 助手发起一轮对话，窗口为 [旧 user, assistant, 当前 user]
- **THEN** 外发 messages 为 [旧 user, assistant, latest_reminder, 当前 user]；提醒内容含本地日期/中文星期/App/中文

#### Scenario: 不落库不跨轮残留
- **WHEN** 同一线程下一轮构建外发窗口
- **THEN** 上一轮的 latest_reminder 不出现在历史消息里，只在当轮当前 user 前重新生成一条

#### Scenario: 非 DeepSeek 不发
- **WHEN** 助手使用 GLM/其它 vendor 的模型
- **THEN** 外发 messages 不含 latest_reminder role
