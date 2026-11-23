# assistant-chat-ui Delta

## ADDED Requirements

### Requirement: 设定页签与字段读取边界

对话线程落在设定域（`set:*`）时，服务端 SHALL 随当轮 user 消息尾注入页签身份，但 SHALL NOT 自动注入设定字段值：

- 面板名真值：`set:*` 线程 SHALL 注入「［当前页签：设定·<面板名>］」——面板键（genre/intro/world/chars/arc/style/foreshadow）映射中文名（题材/简介/世界/角色/主线/文风/伏笔）；`set:default` 与未知面板键 SHALL 回退「设定」。
- 字段值 SHALL NOT 随提示词自动注入；模型需要本页字段与已保存现值时 SHALL 调 `read_page_fields`（见 `c-agent-page-context` / `assistant-tools`「当前设定页字段按需查询」）。题材五格、简介、世界八格等字段值只应出现在工具结果里。
- 工具结果 SHALL 标注「已保存值」；页面有未保存修改时 SHALL 如实提醒，避免模型把落库值当屏幕值。
- 章节页签线程（`ch:*`）与其它线程 SHALL NOT 带设定字段真值（不串味）。

#### Scenario: 设定面板页签真值

- **WHEN** 作家在世界面板对助手说话（线程 `set:world`）
- **THEN** 本轮提示词含「［当前页签：设定·世界］」，但不含世界八格的当前值

#### Scenario: 题材面板字段按需读

- **WHEN** 新书五格全空，作家在题材面板问「当前页面有几个问题」
- **THEN** 提示词只有「［当前页签：设定·题材］」；助手调 `read_page_fields` 后，工具结果逐格点名「未填/未定」

#### Scenario: 已填给值只在工具结果

- **WHEN** 五格已填（题材=玄幻（凡人流）、主要看什么=一句话、禁忌两条、吃苦指数 7、战场一个）
- **THEN** `read_page_fields` 结果逐格给现值，未填项仍点名；提示词本身不出现这些值

#### Scenario: 章节页签不串味

- **WHEN** 作家在章纲页签（`ch:og`）对话
- **THEN** 注入「［当前页签：章纲］」照旧，SHALL NOT 出现设定字段真值

### Requirement: 书情 brief 题材行

书情 brief（系统前缀稳定段）的题材行 SHALL 反映题材目录现值：题材大类已填时 SHALL 注入「题材：<大类>（<子类>）」（子类空时只给大类）；题材未填或读取失败 SHALL 跳过该行，SHALL NOT 注入空行或占位符。题材行数据键 SHALL 与题材上下文解析结果的实际键名一致（回归钉：不得再读不存在于返回结构的键）。

#### Scenario: 题材已填进 brief

- **WHEN** 书的题材目录已存「玄幻／凡人流」，任意页签发起对话
- **THEN** 系统前缀书情段含「题材：玄幻（凡人流）」

#### Scenario: 题材全空不给空行

- **WHEN** 题材五格全空
- **THEN** 书情 brief 只含书名（与进度动态段），无「题材：」空行
