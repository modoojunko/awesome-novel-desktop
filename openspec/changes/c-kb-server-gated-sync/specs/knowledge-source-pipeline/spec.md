## MODIFIED Requirements

### Requirement: 基线 v2 发布与树对齐

基线包 SHALL 按源头重跑产物发布（build→签名→上传私有 COS→最后翻 latest 指针）。一个
release SHALL 只有一份签名 manifest 与一个 `version`；每个题材的条目 SHALL 是独立对象
（`baseline/v{N}/genres/<slug>.jsonl`），manifest 用 `genres` 映射记录每个对象的
path/sha256/bytes/entry_count；SHALL NOT 按题材拆成独立版本或独立 manifest。

`latest.json` SHALL 为签名指针（version/manifest_sha256/generated_at/resume_baseline），
`resume_baseline=true` 仅在基线过合规评审、允许恢复 C 端同步时置；发布顺序 SHALL 为
「上传 v{N} 全部对象 → 冒烟（签名/hash）→ 最后翻 latest」；上传 SHALL 走私有 COS，
SHALL NOT 再上传公开静态托管；S 端 SHALL NOT 参与发布/注册（不建 release 表）。

基线条目 SHALL 携带 node_key（C 端树节点 key）或可由 C 端 slot_map 挂靠（文风 tone→叙事
身份、文笔 tic→句法规矩与忌用）；树数据文件（内容仓 taxonomy/taxonomy.json 与 COS
`tree/v{N}/taxonomy.json`）SHALL 同步补 tone/tic 两条 slot_map 规则——同一份树在两处零漂移；
树发布同样走私有 COS 并在最后翻 `tree/latest.json`。

#### Scenario: 按题材对象构建

- **WHEN** 内容仓 build 一个新版本
- **THEN** 产出 `genres/<slug>.jsonl`（每题材一个对象）＋一份签名 manifest（genres 映射）
  ＋签名 latest；题材合计条目数与 manifest entry_count 一致

#### Scenario: 发布翻指针

- **WHEN** v{N} 全部对象上传且冒烟验签/hash 通过
- **THEN** 最后覆盖 latest.json；客户端下一次 probe 看到新版本；半途失败旧指针仍指旧版

#### Scenario: 基线恢复同步

- **WHEN** 法务放行后发布 latest.json 置 `resume_baseline=true`
- **THEN** C 端探测到 resume 后才清撤回标记并展示题材清单；不自动下载

#### Scenario: 基线条目挂上树

- **WHEN** 新客户端同步某题材基线
- **THEN** 文风 tone 条目挂「叙事身份」、文笔 tic 条目挂「句法规矩与忌用」、手法 kind
  条目挂对应打法节点；树视图与列表臂可见一致的挂靠

#### Scenario: 树文件两处零漂移

- **WHEN** 树数据更新（如补 slot_map 规则）
- **THEN** 内容仓 taxonomy/taxonomy.json 与 COS tree 对象同批同内容，tree 指针随发翻版

#### Scenario: 老客户端向前兼容

- **WHEN** 老客户端拉到新基线（含本端未登记的新概念/新维度）
- **THEN** 读不懂的条目整条跳过、其余照收（既有向前兼容口径不变），SHALL NOT 整包拒收；
  客户端只同步自己档位允许的题材对象（S 端配额语义）
