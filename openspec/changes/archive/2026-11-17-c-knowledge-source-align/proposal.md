## Why

知识内容仓（awesome-novel-knowledge）的源头生产链与 C 端 v2 知识口径系统性不一致。两链共用同一个拆书引擎与提示词模板（产物本身是 v2 全字段：name/how/example/evidence_ch/confidence/kind 实测张张全），但知识仓的「产物→源条目」转换层（tools/deconstruct_batch.py）按旧口径挑键——实测 215 条源条目 payload 键分布：evidence_ch 0、confidence 0、kind 0、example 0、name/how 0；文风产 value 键（C 端 v2 为 text）；文件名含「斩神-前30章」「749-前40章」＝试拆版产物入仓。

下游症状（CDN 基线 v1 全继承）：

1. 基线 53 条两代键名混用（文风 tone 6 条 value＋2 条 text 同槽并存；文笔 8 条 value＋2 条 rule 键装错位）；
2. 基线手法 31 条 payload 仅 instruction+scene——无 kind（全部堆「更多场面打法」兜底叶，无法分家）、无例句、无可信度；
3. 基线条目挂不上 C 端知识树：文风 tone（8 条）/文笔 tic（1 条）无 slot_map 归属规则；基线是只读知识行无 parent 链——树视图装配按孤儿剔除，树里完全看不见基线；
4. schema/entry.schema.json 的 concept enum 只有 [手法,文风,文笔]——世界设定/角色设定被制度性排除（树 13 节点零基线的根源）；payload 自由 object 未约束键面；
5. 源条目文件级含试拆版（早该按版本收敛口径被全本替换）。

boss 2026-11-09 拍板：**不是简单改知识库项目的存量数据，而是把数据源头一起匹配**——修源头生产链，让知识仓产出的每个知识实例天然就是 C 端知识对象定义的形状（可信度/硬度/kind/例句/章证据/角色格），下游（CDN 基线包、树挂靠、键名）自然全对齐。

**架构主从（boss 同日定口径）**：两个知识库各自维护——S端官方知识库（我们维护：知识内容仓＋CDN 分发，内容生产都在这）与 C端作家知识库（作家自主：本地拆书/手录/蒸馏积累）。S端库经 CDN 投影到作家库为只读「官方精选」层（写时复制既有）；本 change 修的就是 S端库的生产链，让官方知识以 C 端作家库能吃的形状发布。

## What Changes

改动主体在知识内容仓（awesome-novel-knowledge，另一 git 仓）；C 端仓零代码改动（CDN 上的知识适应 C 端，方向不得反向）。

1. **转换层复用 C 端映射（治本）**：tools/deconstruct_batch.py 的「产物→源条目」映射不再自写旧口径，改为 import C 端后端 `kb.deconstruct_import.map_deconstruct_products`（该依赖本就存在——拆书引擎已复用 C 端检出），把返回的知识对象转成基线源条目 json（全字段透传：name/how/example/evidence_ch/confidence/kind/scene/emotion/steps）；
2. **源条目对象对齐 C 端知识对象**：固定列四样齐（正文／原文案例 example／章证据 evidence_ch／出处书）；知识点归属字段（node_key，按 C 端树节点 key 标注）；
3. **schema/entry.schema.json 升版**：concept enum 扩世界设定/角色设定；payload 键面按 C 端 v2 收紧（枚举合法键）；新增 example/evidence_ch/confidence/kind/node_key 字段定义；validate.py 硬闸同步；
4. **存量重跑**：215 条源条目按新转换重跑（书稿在、断点缓存机制现成）；试拆版源条目文件（斩神-前30章／749-前40章）以全本重拆替换或标记废弃；
5. **基线包 v2 发布**：build→签名→CDN `/knowledge/baseline/v2/`，指针翻 v2（向前兼容口径：0.47.0 客户端按旧层读，v2 条目老客户端跳过读不懂的键不炸）；
6. **树归属规则补两条（C 端树数据文件，非代码）**：slot_map 补「文风|tone→叙事身份」与「文笔|tic→句法规矩与忌用」（随下个 C 端版本走；CDN 树 v1 同步更新——树 v1 已在 /knowledge/tree/，是过渡供给）。

## Capabilities

### New Capabilities
- knowledge-source-pipeline：知识仓源头生产链（转换映射/schema 契约/校验硬闸/发布）与 C 端 v2 口径的一致性契约

### Modified Capabilities
- knowledge-base：基线只读层的条目形状（v2 结构化字段）、树挂靠（slot_map 补 tone/tic、node_key 挂靠）

## Design Impact

无用户可见界面改动（数据源头与内容仓工具链改造；C 端 UI 由既有 merged 视图/树视图/抽屉按新数据形状自然渲染，字段字典已有覆盖）。不触碰两端共享段；免原型。

## 顾客影响

基线知识（官方打底）在 0.47.0+ 客户端获得 v2 形状：官方条目抽屉有例句/章证据/可信度格、手法分家挂对节点、树视图可见基线挂靠。0.44.2 等老客户升级链路不受影响（迁移引擎已验证）。
