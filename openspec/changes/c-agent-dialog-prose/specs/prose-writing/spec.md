# prose-writing Specification (Delta)

## Purpose

write 链接收助手挑选的写法条目（kb_picks），agent 模式下写法块按挑选结果组装，跳过规则选择器。

## ADDED Requirements

### Requirement: 按助手挑选条目组装写法块

`POST .../write` body 含 `kb_picks` 键（空数组也算）时 SHALL 进入 agent 模式：写法块只由 `kb_picks` 列出的条目组装（逐条三域解析：书级副本→账号条目→官方基线；concept∈(手法,文风,文笔)；status=active；保 agent 顺序；逐条理由随带）；SHALL NOT 调规则选择器。零有效条目 SHALL 不出块（回退本书文风设定）。body 不含该键时既有行为（规则选择器）SHALL 一字不变。

#### Scenario: 挑选条目直接组装

- **WHEN** body 带 kb_picks 两有效条目
- **THEN** 写法块只含这两条（顺序=agent 顺序，文本=条目 instruction），run 落 selector="agent"

#### Scenario: 零命中不出块

- **WHEN** body 带 kb_picks 空数组或全部条目解析失败
- **THEN** 不注入写法块、不留 run，生成照常进行

#### Scenario: 不含键走旧路

- **WHEN** body 不含 kb_picks 键（含 env 熔断直开路径）
- **THEN** 写法块仍由 prepare_write_block 规则选择器产出，行为与本变更前逐字节一致

### Requirement: agent 模式重试字节一致

同章同 kb_picks 同提示词的重试 SHALL 复用同一条 run（brief_hash=章＋prompt 摘要＋picks），写法块逐字节一致；条目文本以 run 内 text_snapshot 固化。

#### Scenario: 重试复用同 run

- **WHEN** 相同 kb_picks 与提示词再次生成同一章
- **THEN** 复用既有 run（selector="agent"），写法块与上次逐字节一致
