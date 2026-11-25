# Proposal: c-kb-server-gated-sync

## Why

官方知识库（基线包 + 知识树）目前放在 CloudBase 静态托管公开路径，任何人拿到 URL 就能
下载；只有 Ed25519 签名校验，没有用户鉴权。静态托管没有私有访问/签名 URL/按登录 token
的逐请求校验，桌面端 Referer 也可伪造。产品需要：**登录才能取；S 端按档位控制每天能同步
几个题材；内容本身不分档；知识树免费；知识文件全部放私有对象存储**。

S 端契约（s-kb-signed-delivery）：`POST /api/kb/sign` 按 scope 换腾讯云 COS 短时签名
URL；基线 `baseline_genre` 按档位每日配额（免费 2 / 标准 5 / PRO 20 / MAX 50），
pointer/manifest/tree 免费。本变更落 C 端消费侧。

## What Changes

- **删除公开 CDN 抓取**：`kb/baseline.py`、`kb/tree_sync.py` 不再拼 `www.awesomenovel.com/
  knowledge/...`；新增 `kb/server_api.py`，走 `call_server_api("kb/sign")` 换 COS 短时
  URL，`fetch_signed` 出站守卫（COS 桶域白名单）后下载。
- **基线改为按题材同步**：一个 release/一份签名 manifest；每个题材是独立对象
  （`baseline/v{N}/genres/<slug>.jsonl`）。客户端只同步用户选中的题材，**只替换该题材
  的只读层**；其他题材行与用户 overlay 原样保留。`AppMeta["kb_baseline_genres"]` 存
  `{genre: {version, sha256, path, entries, synced_at}}`；按题材高水位防降级。
- **配额语义落到交互**：启动/登录/周期复查只做 **pointer+manifest 免费探测**，不自动
  下载题材、不静默扣额度；用户在知识库页/写作工作台按题材点「同步」才下载（S 端扣 1 次/
  天）。429/403/401/404 按原因诚实提示（用完/套餐不含/未登录/无此题材）。
- **知识树免费**：`tree_pointer`/`tree_data` 不占题材次数；登录后自动同步/更新；
  `KB_TREE_SYNC=0` 测试闸保留。
- **撤回恢复**：`latest.json` 的 `resume_baseline=true` 才清 `kb_baseline_retired`；
  清后仍需用户选题材，不自动下载。
- **前端**：`KnowledgeSyncModal` 从单版本确认改为**题材清单**（已同步/可更新/未同步 +
  每行同步按钮 + 今日剩余额度/重置）；知识库页当前题材未同步时给「去同步」入口；
  写作工作台 appbar 在书的题材未同步时给「去同步本题材」提示（携 `focusGenre` 开弹窗）。
- **口径/契约**：`write_block` 冷启动 fingerprint 改为按书的题材取该题材 version/sha；
  `baseline/status` 透出 `genres`；`POST /api/kb/baseline/sync` 带 `{genre}`；
  `kbApi.baselineSync(genre)`。

## Capabilities

### Modified Capabilities

- `knowledge-baseline`: 分发改 S 端签名 URL；按题材同步/部分层替换；配额与探测分离；
  撤回 resume。
- `knowledge-base`: 知识树同步改 S 端签名 URL（私有 COS，免费，登录自动更新）。
- `knowledge-source-pipeline`: 发布改私有 COS + 按题材数据对象 + 单一 manifest；
  基线 v5 resume 标记。

## Design Impact

- 受影响端：C 端。
- 屏/弹层：`KnowledgeSyncModal`（题材清单/配额/失败态）、知识库页（当前题材「去同步」
  提示）、写作工作台 appbar（「去同步本题材」提示）。
- 对象状态：复用既有 info/warn/err 语气；无新令牌、无裸 hex、无 emoji、无新增字号档位；
  弹层复用 `.pm-*` 与既有 `btn` 词汇；列表行用现有 `--border/--fg/--muted/--accent-soft`。
- 共享段：不触 `base.css` 令牌/基础组件类；不新增跨端同名类。
- 原型：沿用既有知识库/官方知识弹层版式；按题材清单属状态扩展而非新屏；
  在 `docs/design-c/prototypes/ADJUSTMENTS.md` 登记「知识库按题材同步（S 端配额）」
  与写作提示的口径，待设计侧复核。

## 非目标

- 内容创作/基线 v5 内容本身（内容仓发布，S 端不参与）。
- 按题材独立版本/独立 manifest；多份内容包。
- S 端后台页面/配额运营 UI（S 端脚本 + 档位配置）。
- DRM/下载后防复制；短时 URL + 签名内容为边界。
- 提示词包链路改造。
