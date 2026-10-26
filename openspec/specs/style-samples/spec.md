# style-samples Specification

## Purpose
成段文风示范（style_samples）的生命周期：把拆书得到的原书成段原文摘录落进文风 KV，作为正文生成时模型可模仿的最强笔法依据；与短句例句（few_shot_examples，例句提炼专属）并存互不挤占。

## Requirements

### Requirement: 示范段落文风 KV 与写边界

- writing-style KV SHALL 新增白名单写键 `style_samples`（字符串列表，≤6 条、单条 ≤500 字），GET/PUT `/settings/style` 对其做与既有键同款的归一边界处理（去空白、保序去重、上限截断、单条截长）。
- 书籍备份导出/导入 SHALL 整文件透传 writing-style KV，`style_samples` 随文件原样迁移，SHALL NOT 需要专项迁移逻辑。
- 存量书无该键时一切链路 SHALL 视为空，SHALL NOT 产生空节、报错或迁移动作。

#### Scenario: 读写回路
- **WHEN** PUT /settings/style 带 `style_samples` 3 条成段原文后再 GET
- **THEN** 3 条原样返回（顺序保持、无重复）；与三区、禁用词等既有键共存于同一文档

#### Scenario: 上限截断
- **WHEN** PUT 带 9 条、其中 1 条超 500 字
- **THEN** 只保留前 6 条且超长条目截到 500 字，不报错

#### Scenario: 存量书零感知
- **WHEN** 存量书 writing-style KV 无 `style_samples` 键
- **THEN** GET 响应无该键或为空，正文提示词不含示范段块，文风页不出现示范段折叠组

### Requirement: 拆书例句成段落盘

- 建书写入「写作文风」维度时，系统 SHALL 把产物例句（成段原文摘录）经清洗截长（单条 ≤400 字）后写入 `style_samples`（取前 6 条），SHALL NOT 再写入 `few_shot_examples`。
- 产物例句 SHALL 为原书逐字原文段（由提示词包模板约束产出）；清洗 SHALL NOT 改写原文内容，只做长度收口与不可用条目剔除。
- 旧拆书任务产物中的短例句 SHALL 照常收进 `style_samples`（短但无害），SHALL NOT 因此拒绝写入。
- 例句字段为空时 SHALL 保留新书文风设定其余字段并给出降级提示，SHALL NOT 报错中断。

#### Scenario: 建书后示范段可见
- **WHEN** 用户拆完书勾默认项建书成功，进入新书文风页
- **THEN** 示范段折叠组显示产物例句（成段原文，≤6 条）；硬约束/手法含「写作技法」维度并去重后的条目

#### Scenario: 旧任务短例兼容
- **WHEN** 旧拆书任务的文风产物例句为 ≤60 字短句
- **THEN** 建书仍把短句写入 `style_samples`（条数与长度按上限收口），流程不中断

### Requirement: 正文恒定层示范段注入

- 正文生成 system 恒定层的文风基线 SHALL 含示范段块：取 `style_samples` 前 3 条逐条编号呈现，并声明其为本书句式、节奏、对话密度的最高笔法依据。
- 示范段块 SHALL 位于 system 恒定层（逐章一致，命中供应商提示词缓存）；本书设定未变更时示范段内容 SHALL 逐章一致。
- 未配置 `style_samples` 时 SHALL 跳过该块而非输出空节；补缝续写、AI 体检等轻量路径 SHALL NOT 注入示范段。

#### Scenario: 示范段进恒定层
- **WHEN** 本书文风 KV 含 6 条示范段，连续生成两章
- **THEN** 两章 system 层均含前 3 条示范段且逐字节一致

#### Scenario: 未配置跳过
- **WHEN** 本书无示范段
- **THEN** system 层文风基线不含示范段块，也不存在引用空示范段的悬空说明

### Requirement: 文风页示范段展示

- 文风面板「文字文风」签 SHALL 在例句区后新增「示范段」折叠组：只读段落列表（保留原文换行）＋单条删除，SHALL NOT 提供添加或行内编辑入口（来源仅拆书导入）。
- 表单保存 SHALL 在示范段非空时携带该键、为空时 SHALL NOT 携带该键（存量保存流程的 payload 键集保持不变）。

#### Scenario: 删除一条示范段
- **WHEN** 用户在示范段折叠组删除第 2 条并保存
- **THEN** PUT payload 含余下示范段（保序），保存后重进页面只显示余下条目

#### Scenario: 无示范段不显组
- **WHEN** 本书无示范段
- **THEN** 文风页不出现示范段折叠组
