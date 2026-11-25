# Design: c-kb-server-gated-sync

## D1 一次 release/一份 manifest，按题材拆数据对象

内容不分档，仍是一个 `version` + 一份签名 manifest；每个题材是独立对象：

```json
{"version":5,"format_client":"0.45.0","entry_count":8197,
 "genres":{"玄幻":{"path":"genres/<slug>.jsonl","sha256":"...","bytes":123,"entry_count":474}, ...},
 "tombstones_sha256":"..."}
```

`latest.json` = `{version, manifest_sha256, generated_at, resume_baseline, signer_key_id,
signature}`。客户端验指针→按 `manifest_sha256` 对拍 manifest 原始字节→验 manifest 签名，
再取选中题材的 path/hash；不为每个题材造独立版本。

## D2 只替换该题材的只读层

`_replace_genre_layer(genre, version, entries, ...)`：

- 只删/插 `KbBaselineEntry.genre == genre` 的行与对应 `KbBaselineTag`；
- 其他题材行、overlay 原样保留；
- orphan hide/edit、提升副本、re-add auto-hide、carry（本端读不懂沿用旧层）全部按该题材
  `src_key` 作用域处理——逐条复用旧整层实现；
- 单事务提交；`AppMeta["kb_baseline_genres"][genre] = {version, sha256, path, entries,
  synced_at}`；全局 `kb_baseline_version` 取各题材最大值（兼容旧读数）；
- 按题材高水位：release version < 本地该题材 version → `older_than_installed`，旧层不动。

## D3 探测与下载分离（不静默扣额度）

- 启动/登录/周期复查只调 `probe_latest()`：`sign("baseline_pointer")` →
  `sign("baseline_manifest")`（免费）→ 得到题材清单/本机已同步/今日配额/resume；
  **绝不自动下载题材**。周期复查只刷新可用状态，不整层替换。
- 用户动作：知识库页/写作工作台按题材点同步 → `sync_genre(genre)`：
  `sign("baseline_genre", version, path, genre)` → 下载 → sha256/size → 逐条
  `check_baseline_entry` → 只替换该题材层。
- 免费额度：free/none 2、standard 5、PRO 20、MAX 50（S 端 `entitlement.kb`）；429/403/
  401 按原因提示；600s 同 version+path 幂等由 S 端保证，客户端 `_syncing` 单飞。
- 同题材内容 sha 未变 → `current`，不发 genre ticket（不扣额度）。

## D4 知识树免费且自动更新

`tree_pointer`/`tree_data` 只要求登录、不占题材次数；启动/登录自动同步/更新，保留
`KB_TREE_SYNC=0` 测试闸与既有缓存/回执/高水位/结构闸。S 端返回 COS 签名 URL，客户端
出站守卫（`KB_STORAGE_HOSTS` 精确主机 + fake-ip 逃生）后下载。

## D5 撤回恢复由 pointer 显式放行

`latest.json.resume_baseline=true` 是内容仓/S 端的显式放行；只有带该标记才清
`kb_baseline_retired`。清标记后不自动下载——仍需用户选题材。`probe_latest` 在撤回态
且拿不到 release（未登录/网络）时优先回 `reason=retired`；拿到 release 且 resume 才展示
清单。

## D6 指纹/读面

- `write_block` 冷启动 fingerprint 从全局版本改为 `baseline:{genre_version}:{genre}:
  {genre_sha}`，官方升级该题材即换域重选，不误复用旧 run。
- `baseline/status` 透出 `genres` 映射；probe 返回 `genres/installed_genres/updates/quota/
  resume`；前端题材清单以 `sha256` 对拍得出已同步/可更新/未同步。

## D7 旧客户端与公开树过渡

- 基线：旧客户端仍处撤回态（不拉取）；v5 只走 S 端。
- 知识树：新客户端走 S 端；公开 `knowledge/tree` 保留一个版本周期供旧客户端，随后
  从静态托管删除。旧客户端靠已缓存树继续工作、随自动更新迁移。
