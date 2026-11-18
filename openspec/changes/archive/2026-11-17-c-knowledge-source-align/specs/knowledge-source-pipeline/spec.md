# knowledge-source-pipeline Specification

## ADDED Requirements

### Requirement: 源头生产链与 C 端口径一致

知识内容仓（awesome-novel-knowledge）的源头生产链（拆书引擎产物 → 转换映射 → 源条目 →
schema 契约 → 校验硬闸 → 打包发布）产出的知识实例对象 SHALL 与 C 端知识口径
（kb/deconstruct_import v2 映射＋taxonomy 字段模板）一致——**CDN 上的知识适应 C 端，
方向不得反向**。实现主体住知识内容仓（tools/deconstruct_batch.py、schema/entry.schema.json、
tools/validate.py、tools/tree_publish.py），C 端仓只承载树数据文件（kb/data/taxonomy.json，
随 C 端发版）。任何一环产出与 C 端口径不一致 SHALL 视为该环缺陷（修环，不手改下游数据）。

#### Scenario: 全链形状一致实证

- **WHEN** 同一本全本书稿分别走 C 端拆书收录与知识仓批量拆书转换
- **THEN** 两边产出的知识实例对象同形：同槽同键名（无 v1 value 键）、同带 example/evidence_ch/confidence、手法 kind 分家一致、可挂靠同一批树节点

### Requirement: 转换层复用 C 端映射

知识仓的「拆书产物 → 源条目」转换 SHALL 复用 C 端后端 `kb.deconstruct_import` 的映射
函数（同一份「产物→条目」逻辑），SHALL NOT 维护第二份旧口径映射；转换产物 SHALL 透传
C 端 v2 全部结构化字段（name/how/example/evidence_ch/confidence/kind/scene/emotion/steps）。

#### Scenario: v2 字段不丢失

- **WHEN** 拆书产物含 name/how/example/evidence_ch/confidence/kind 的手法条目进入转换
- **THEN** 源条目 payload 与条目级字段透传全部上述键（evidence_ch 进条目章证据、example 进原文案例、confidence/kind 进 payload），SHALL NOT 出现只保留 instruction/scene 的旧口径输出

#### Scenario: 映射随 C 端演进

- **WHEN** C 端收集映射新增一个结构化字段
- **THEN** 知识仓转换层无需改映射逻辑即随复用透传该字段（只允许转换外壳适配 json 形状）

### Requirement: schema 契约与硬闸覆盖 v2 键面

schema/entry.schema.json SHALL 覆盖 v2 键面：payload 合法键枚举（instruction/scene/emotion/steps/kind/confidence/name/how/example/evidence_ch 等）、条目级 example/evidence_ch/confidence/kind/node_key 字段定义；validate.py 硬闸 SHALL 拒绝键面外的 payload 键（value 等 v1 键名 SHALL 视为违规）。world/character 维度的收录许可 SHALL 由 schema 的 concept enum 表达。

#### Scenario: v1 键名被硬闸拒绝

- **WHEN** 源条目 payload 含 v1 键名 value（文风 tone 旧口径）
- **THEN** validate 校验该条违规（键面外），build 拒绝打包含此条目的版本

#### Scenario: world/character 维度许可

- **WHEN** schema concept enum 扩入 世界设定/角色设定
- **THEN** 这两维源条目过 validate 并进基线包（不再被制度性排除）；enum 未扩时此类条目仍违规

### Requirement: 试拆版源条目替换

源条目 SHALL NOT 以试拆版拆书产物为源——源文件名含「-前N章」的条目组 SHALL 以同书全本
重拆产物替换（转换重跑自然产生）；无法重拆的 SHALL 标记废弃并出包（tombstones 或剔除）。

#### Scenario: 试拆文件重跑被全本替换

- **WHEN** 「拆书-斩神-前30章.jsonl」对应书稿以全本重跑批量拆书
- **THEN** 新源文件以全本条目入仓、试拆文件剔除，重名 src_key 以全本为准

### Requirement: 基线 v2 发布与树对齐

基线包 v2 SHALL 按上述源头重跑产物发布（build→签名→CDN 指针翻 v2）；基线条目 SHALL 携带
node_key（C 端树节点 key）或可由 C 端 slot_map 挂靠（文风 tone→叙事身份、文笔 tic→句法规矩
与忌用）；树数据文件（C 端仓 kb/data/taxonomy.json 与 CDN /knowledge/tree/）SHALL 同步补
tone/tic 两条 slot_map 规则——同一份树在两处零漂移。

#### Scenario: 基线条目挂上树

- **WHEN** 0.47.0+ 客户端同步基线 v2
- **THEN** 文风 tone 条目挂「叙事身份」、文笔 tic 条目挂「句法规矩与忌用」、手法 kind 条目挂对应打法节点；树视图与列表臂可见一致的挂靠

#### Scenario: 老客户端向前兼容

- **WHEN** 0.44~0.46 客户端拉到基线 v2
- **THEN** 读不懂 v2 新键的条目整条跳过、其余照收（既有向前兼容口径不变），SHALL NOT 整包拒收

#### Scenario: 树文件两处零漂移

- **WHEN** 树数据更新（如补 slot_map 规则）
- **THEN** C 端仓 kb/data/taxonomy.json 与知识仓 taxonomy/taxonomy.json 同批同内容变更，CDN tree 指针随发翻版
