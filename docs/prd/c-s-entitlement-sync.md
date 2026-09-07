# C端×S端 套餐权益同步机制设计（Entitlement Sync）

| | |
|---|---|
| 状态 | **设计稿 · 停审批口（待批准，未动工）** |
| 日期 | 2026-09-06 |
| 触发事故 | PRO 用户（modoojunko）本地 C端 被按免费处理：1 本书限额 + AI 全关。根因=双事实源断裂（S端 档位归一化 pro/max，C端 MEMBER_TIERS 白名单停留旧档位名） |
| 影响范围 | server（S端）/ client（C端，前后端）|
| 关联既定纪律 | 本体论纪律（一物一属、词义专属）、schema 演进宪法（pg_gate + server_default）、feature key 登记制、先审方案再改代码 |

---

## 1. 背景与病根

"什么套餐能用什么功能"目前两端**各存一份硬编码**：

- S端 `app/domain/payments/pricing.py`：把 legacy 档位名归一化（monthly/quarterly/yearly/lifetime → **pro**），check-auth 返回归一化后的 tier；
- C端 `client/backend/auth_local/service.py:87`：`MEMBER_TIERS = ("trial","monthly","quarterly","yearly","lifetime")` 自判会员。

S端 改一次档位命名，C端 白名单立刻过期。本次 "pro"/"max" 不在白名单 → PRO 用户 `is_member=False`、`project_limit=1`。这不是孤立 bug，是**双事实源结构问题**：只要两端各判各的，以后每次调套餐都会复发。

**治本方向（用户拍板的思路）**：C端 登录时从 S端 拿到"该用户的套餐内容+时长"结构化权益，缓存本地；C端 所有功能开关只读这份快照，不再自判档位。S端 成为唯一事实源。

---

## 2. 术语表（本体论：一物一名，一物一属，词义专属）

| 术语 | 英文/表 | 是什么 | 归属 |
|---|---|---|---|
| **档位** | Tier（`tiers` 表） | 内容等级：pro / max / 未来的档。定义"能用什么" | S端 商品目录 |
| **套餐** | Sku（`skus` 表） | 可购买商品 = 档位 × 时长（+价格+设备数）。pro 月付/季付/年付是三个套餐、同一档位 | S端 商品目录 |
| **权益** | entitlement（存量表名 `codes`，见 §2.1） | 用户每笔购买落下的记录：档位 + 到期日 + 状态（active/queued/frozen/revoked） | 用户持有，S端 记账 |
| **权益快照** | entitlement（本设计新增的下发/缓存字段） | 某用户"当前能用什么"的结构化投影：features + limits。由权益×档位配置在 check-auth 时算出 | 用户×时刻的持有物；C端 只持只读副本 |
| **功能 key** | FeatureKey | 全产品统一登记的功能名（如 `ai-generate`），双端按词汇表实现 | 双端共享 spec |

本体论检查：features/limits 是**权益快照的属性**（随退款收回而缩）；档位配置是**商品目录**（属 S端）；C端 不持有档位对象，只持快照。`MEMBER_TIERS` 这个 C端 私货第二事实源**摘除**。

### 2.1 命名裁定（用户拍板 2026-09-06，了结"一物三名"遗留）

09-03 命名审计遗留"一物三名 code/grant/entitlement 未议"。用户拍板裁定：**"code" 词义专属"代码"；权益就用"权益"（entitlement）；设备的权限就用"设备权限"（device_permission）**。

| 名 | 裁定 |
|---|---|
| `code` | **词义归还"代码"，从此不命名任何权益对象。** 现网 `codes` 表拿它命名权益 = 存量违例；**表改名（codes → entitlements）列遗留项单独裁决**——生产表改名是大迁移，不并入本特性，本文档行文中该表一律称"权益"，代码引用保留存量表名 |
| `grant` | **退役，不再命名对象。** 设备授权正名 `authorization`（用户拍板 2026-09-06，四选一：authorizations/permits/bindings/enrollments）：现有代码动词已存在（`POST /api/authorize`、`authorize_device()` 创建的正是这条记录），名词化零新词；OAuth RFC 8628 标准术语 Device Authorization；C端 授权页文案本就叫"设备授权"。存量违例改名（`device_grants` → `authorizations`、grant_repo → authorization_repo、URI `/grants/*` → `/authorizations/*`）**与 codes 改名同一遗留立项**，不并入本特性 |
| `entitlement` | **✅ 采用 = 权益**。本特性全链路：契约字段 `data.entitlement`、tiers 新列 `entitlement`、C端 缓存键 `entitlement`、兜底表 `ENTITLEMENT_DEFAULTS` |
| `License` | 保留为 S端 域聚合类名（`app/domain/licensing/license.py`，实存对象），不作契约字段名——聚合叫 License，聚合投影出的"内容"叫权益，两词各司其职。**中文口径 = 会员资格（持有聚合）**：回答"是不是会员/什么档/到何时"，UI 文案"我的套餐"、后端布尔 `is_member` 均此概念；英文词形是 09-03 拍板（#285–#287，URI /api/pay/license，membership 裁定域外词弃用） |

**"一物三名"就此了结**：code 归代码、grant 退役（对象正名 authorization 设备授权）、entitlement = 权益正名。遗留关闭，存量改名（codes→entitlements + device_grants→authorizations）统一走一个迁移立项。

---

## 3. 现状盘点（全部实测，非假设）

### 3.1 S端 生产数据（2026-09-06 查询）

`tiers`（档位表，已有）：

| key | 显示名 | rank | 状态 | 卖点 |
|---|---|---|---|---|
| pro | PRO | 20 | live | AI 生成正文（流式）/ 设定与章纲融入 AI / 多设备同步 |
| max | MAX | 30 | **planned（规划中）** | （空） |

`skus`（套餐表，已有，3 行全是 pro 家族）：

| sku_key | 档位 | 时长(period_days) | 价格 | 设备数 |
|---|---|---|---|---|
| pro_monthly | pro | 30 | ¥30 | 3 |
| pro_quarterly | pro | 90 | ¥80×0.9=¥72 | 3 |
| pro_yearly | pro | 365 | ¥299×0.8=¥239.2 | 5 |

权益表（存量名 `codes`）：tier + expires_at + status。`License.merge()` 已实现：跳过 revoked/frozen/pending_activation，取最高档位 + 最晚到期。

### 3.2 现有 check-auth 契约（`server/app/interfaces/client_api/authorize.py`）

```json
{ "code": 0, "data": { "token", "username", "tier", "expires_at", "days_remaining?", "attention?" } }
```

`tier` = 归一化后的 effective_tier（none/free/trial/pro/max）。

### 3.3 C端 判定链（单点，好消息）

```
config.json (tier/expires_at)
   └→ check_permission()  ← 唯一判定点（service.py）
        ├→ require_ai_access (deps.py)      AI 403 member_required
        ├→ require_project_limit (deps.py)  免费建书 403
        └→ C端后端 /check-auth 响应 → LicenseProvider/useTier → 前端全部消费 is_member
```

前端消费 `is_member/isPro` 的组件：NovelListPage（`freeLimitReached = !isMember && novels.length >= 1`）、CreateProjectModal（同口径）、ChapterWorkspace（prompt tab / canAiDraft）、Rail（rail-locked 升级卡）、UpgradeModal、NovelWorkspace、PrefsModal、BookPrefsModal。

### 3.4 C端 已有功能注册表（重要既有资产）

`client/frontend/src/lib/features.ts`：`FeatureKey` 联合类型 + `FEATURES` 注册表，12 个 key：

- 免费完整可用（7）：tree-crud / prose-edit / version-history / archive / volume-chapter-config / advanced-config-entry / settings-7-items
- 会员 AI 能力（5）：settings-ai-fields / outline-advanced-fields / **ai-generate** / **prompt-panel** / **ai-model**

口径既定（2026-08-18）：入口一律可见不做 UI 隐藏；使用由后端统一拦截（AI 403 / 建书 403），前端只做升级引导。**本设计沿用该口径，不改为隐藏式。**

---

## 4. 目标与非目标

**目标**
1. S端 单一事实源：档位上配置"内容（features/limits）"，套餐上已有"时长/设备数"，check-auth 下发合并后的权益快照；
2. C端 摘除档位白名单，登录拉快照缓存本地，按快照开功能；
3. 新增档位/套餐/功能 = S端 配置（+C端 发版带新功能实现），**判定逻辑零改动**；
4. 新老版本互滚兼容，任何一端先升级都不炸。

**非目标**
- 不做 DRM：C端 是本地桌面应用，权益门禁是 UX 级（防误用不防改制包）；
- 不改 S端 支付/退款/排队/冻结既有语义（快照自动继承 License.merge 结果）；
- **不改存量表名**（codes → entitlements 的改名是遗留项单独裁决，见 §2.1）；
- 本期不改前端"入口可见"口径（隐藏式门禁不在范围）；
- S端 管理后台可视化编辑、升级页功能矩阵接口 = 二期，本文只留接口位置。

---

## 5. 总体架构

```
┌─ S端（事实源）──────────────────────────────┐
│ tiers.entitlement = 内容配置(新增列)         │
│ skus.period_days/device_limit = 时长与设备   │
│ codes(存量名) = 用户权益记录(不变)            │
│                                              │
│ check-auth:                                  │
│   License.merge(codes) → effective_tier ────┼──┐
│                + max_expires_at              │  │
│   tier 配置(缺省回退 ENTITLEMENT_DEFAULTS) ──┼──┤
└──────────────────────────────────────────────┘  │
                    │ HTTP（现有 check-auth 响应加一个可选字段）│
                    ▼                              ▼
┌─ C端（消费者）────────────────────────────────────────┐
│ config.json 缓存：entitlement 快照 + fetched_at        │
│                                                        │
│ check_permission()（唯一判定点，重写判定源）：          │
│   ① expires_at 本地判过期 → 过期=免费基线（不依赖网络） │
│   ② 有快照 → features/limits 决定 is_member/max_projects│
│   ③ 无快照(老S端) → FALLBACK 兜底名单(含 pro/max)      │
│   ④ S端不可达 → 沿用上次快照，绝不降级                  │
│        │                                               │
│        ├→ require_ai_access / require_project_limit（不变）│
│        └→ 前端 useTier / features 注册表（快照驱动）    │
└────────────────────────────────────────────────────────┘
```

### 5.1 端到端数据流（八跳全景）

```
写入侧（慢变量，一年动几次）
  运营/种子SQL ─▶ tiers.entitlement（档位标准权益模板；缺行/坏JSON→ENTITLEMENT_DEFAULTS 接住）
  支付/退款链 ──▶ codes 行（tier+expires_at+status；退款=改状态不删行）

读取链（每次刷新走一遍）
 ①触发 C端：启动/登录 + 路由切换 + window focus(尽力)
 ② C端后端 /auth/check-auth → browser_auth(silent)
 ③HTTP S端 /api/check-auth
 ④ License.merge(codes) → effective_tier + max_expires_at
 ⑤ TierRepo 查 tiers.entitlement（进程内缓存 60s，保住 #288 单往返）
 ⑥ 响应 data.entitlement = {v, features, limits}（模板实例化为用户投影）
 ⑦ C端完整性校验 → 写 config.json 快照（entitlement + fetched_at）
 ⑧ check_permission 本地判定【不联网】→ require_ai_access / require_project_limit
    / verify_session → 前端 useTier/useFeature/客服提示条
```

形态逐跳结论化：模板（档位标准）→ 记录（用户购买）→ 投影（用户此刻可用）→ 快照（本地副本）→ 判定（布尔/数字）→ 界面。**没有任何一跳自己发明规则**；网络只存在于刷新点，业务请求零额外延迟；写侧变化（退款/购买）靠下次刷新传播（Q1/Q5）。

断点行为：③ 超时→沿用旧快照不降级；⑥/⑦ 不全→三段式（重同步→档位标准兜底+客服提示）；到期→本地即降不等刷新；code 1/2→清除/基线。

---

## 6. S端 设计

### 6.1 tiers 表加一列（内容配置的家）

```sql
ALTER TABLE tiers
  ADD COLUMN entitlement TEXT NOT NULL DEFAULT '{}';
```

- **单列 JSON**：未来加新权益维度零 DDL（生产 PG schema 手工维护是既定痛点，列数最小化）；
- 配在档位级不配在套餐级：pro 月/季/年共用同一份内容配置，改一处三家生效；时长/设备数本就在 skus 上，各归各家；
- schema 纪律全套适用：`server_default '{}'` 落 ORM（`models/payments.py` TierORM）+ `pg_schema.py` EXPECTED_DEFAULTS/REQUIRED 不变量登记 + pg_gate 门禁 + 生产手工 DDL（改既有表加列，无新表，不触发 cloudbase_admin 授权问题）。

### 6.2 ENTITLEMENT_DEFAULTS（代码级兜底，config.py）

```python
# 与 TIER_POLICY 同层；档位行无配置或缺列时回退
ENTITLEMENT_DEFAULTS = {
    "none":  {"features": [], "limits": {"max_projects": 1}},
    "free":  {"features": [], "limits": {"max_projects": 1}},
    "trial": {"features": ["settings-ai-fields", "outline-advanced-fields",
                           "ai-generate", "prompt-panel", "ai-model"],
              "limits": {"max_projects": None}},
    "pro":   {"features": ["settings-ai-fields", "outline-advanced-fields",
                           "ai-generate", "prompt-panel", "ai-model"],
              "limits": {"max_projects": None}},
    "max":   {"features": ["settings-ai-fields", "outline-advanced-fields",
                           "ai-generate", "prompt-panel", "ai-model"],
              "limits": {"max_projects": None}},   # planned：先给 pro 同款，上线时改配置即可
}
```

features 取值**直接采用 C端 `features.ts` 既有 FeatureKey 词汇表**——不发明第二套词。设备数不下发（现由 S端 激活链路 own，C端 无消费点，避免造无主字段；将来 C端 要展示设备配额时再加 `limits.device_limit`，来源=购买行对应 sku 列）。

### 6.3 check-auth 组装（authorize.py，伪代码）

```python
license_ = License(username).merge(codes)          # 现有逻辑零改动
data = { token, username, tier, expires_at, ... }   # 现有字段零改动

tier_cfg = TierRepo(db).find_cached(license_.effective_tier)  # 进程内 TTL 缓存 60s：
    # tiers 配置变更频率极低，缓存避免每次刷新多一跳 pg_http（保住 #288 单往返优化）
snap = tier_cfg.entitlement（坏 JSON 也走兜底） if tier_cfg else None
data["entitlement"] = {"v": 1, **(snap or ENTITLEMENT_DEFAULTS.get(tier, 免费基线))}
```

退款/冻结/排队自然生效：merge 跳过 revoked/frozen、queued 顶位逻辑不变，快照在下次 check-auth 自动反映。

### 6.4 种子 SQL（生产 DDL 同事务）

```sql
UPDATE tiers SET entitlement = '{"features":["settings-ai-fields","outline-advanced-fields","ai-generate","prompt-panel","ai-model"],"limits":{"max_projects":null}}'
 WHERE key = 'pro';
UPDATE tiers SET entitlement = '{}' WHERE key = 'max';  -- planned 留空走 DEFAULTS
```

### 6.5 功能 key 词汇表（登记制）

- 词汇表事实源 = `client/frontend/src/lib/features.ts` 的 FeatureKey；本文 §3.4 的 12 个 key 即首批目录；
- 规则：**加新 key 必须先在 openspec specs 登记，S端 配置与 C端 实现按词汇表对齐**（与 nodeTitle.ts 单一事实源、schema 演进宪法同款纪律）；
- S端 下发未知 key 对老 C端 无害（忽略）；C端 出现未知 key 属 C端 超前实现，发现即修。

### 6.6 套餐×功能映射矩阵（首期，如实反映生产现状）

| C端 收费功能 | feature key | 免费 | trial | pro | max(planned) |
|---|---|---|---|---|---|
| AI 生成正文 / 章纲 AI 起草 | `ai-generate` | ❌ | ✅ | ✅ | ✅ |
| 提示词面板（可见不能用） | `prompt-panel` | ❌ | ✅ | ✅ | ✅ |
| 设置里的 AI 字段 | `settings-ai-fields` | ❌ | ✅ | ✅ | ✅ |
| AI 模型配置 | `ai-model` | ❌ | ✅ | ✅ | ✅ |
| 章纲高级字段 | `outline-advanced-fields` | ❌ | ✅ | ✅ | ✅ |
| 多本书（不走 key，走限额） | — | limits.max_projects=1 | null 不限 | null | null |
| 人工写作全家 7 项 | 7 个免费 key | ✅ | ✅ | ✅ | ✅ |

- 现阶段 trial/pro/max 内容相同（差异只有时长/价格）——与生产一致（max 未配差异化内容）；
- **决策权在 S端 tiers.entitlement**（改套餐=改配置），**执行权在 C端 门禁点**（useFeature/require_ai_access 只查 key，无权决定套餐内容），key 是两端对上的公共词汇；
- max 扩位 = S端 给 max 行的 features 加新 key，C端 判定零改动。

---

## 7. 契约设计（check-auth v2）

响应**新增一个可选字段**，其余全部不动：

```json
{
  "code": 0,
  "data": {
    "token": "…", "username": "…",
    "tier": "pro", "expires_at": "2126-08-01T00:00:00",
    "days_remaining": 43960,
    "entitlement": {
      "v": 1,
      "features": ["settings-ai-fields", "outline-advanced-fields", "ai-generate", "prompt-panel", "ai-model"],
      "limits": { "max_projects": null }
    }
  }
}
```

字段语义：

| 字段 | 语义 |
|---|---|
| `features` | 该用户当前可用的功能 key 数组；未知 key 旧 C端 忽略 |
| `limits.max_projects` | 建书上限；**null=不限**，数字=封顶 |
| `v` | 契约版本，当前恒 1，预留演进 |
| 字段缺省 | = 老 S端，C端 走兜底（见兼容矩阵） |

注：`tier`/`expires_at` 保持平铺不动（老 C端 在消费），权益快照只装**增量信息**（features/limits），不做对象的整体搬迁——兼容优先。

### 兼容矩阵（互滚不炸）

| S端＼C端 | 新 C端 | 老 C端（现网） |
|---|---|---|
| 新 S端 | 快照判定（主路径） | 多余字段被忽略，行为=现状（老 C端 收到 pro 照样判免费——**所以要尽快发新 C端**） |
| 老 S端 | 兜底名单判定 | 现状 |

---

## 8. C端 设计

### 8.1 快照缓存（config.json）

```json
{
  "tier": "pro",
  "expires_at": "2126-08-01T00:00:00",
  "entitlement": { "v": 1, "features": ["…"], "limits": {"max_projects": null} },
  "entitlement_fetched_at": "2026-09-06T12:42:27+00:00"
}
```

- `browser_auth(silent)` code 0 时随 tier/expires_at 一起写入；
- **刷新时机（Q1 拍板 2026-09-06）**：启动/登录（现状）+ **应用回到前台** + **进入工作台**，三处触发静默刷新（去抖节流，如 60s 内不重复）；**不做定时轮询**（省电省请求，且不把 S端 云托管实例钉活烧点数）。支撑产品拍板"付完最快生效"：用户在网页付完款，切回 App 即生效；
- 会话失效（code 1 清凭据）时**连同 entitlement 快照一并清除**；
- `load_or_create_config` 默认值补 `"entitlement": null`。

### 8.2 check_permission() 判定优先级链（核心改动）

```python
FALLBACK_MEMBER_TIERS = ("trial", "pro", "max",
                         "monthly", "quarterly", "yearly", "lifetime")  # 兜底，且这次事故的补丁

def check_permission():
    # 0) deletion_pending → 免费基线（语义不变）
    # 1) expires_at 本地判过期/非法 → 免费基线（语义不变，不依赖网络）
    #    （Q4 收紧：trial 无 expires_at 一律按免费基线；仅 dev/test 环境保留旧宽限——
    #     "无到期=永久"只许存在于开发测试）
    # 2) snap = cfg.entitlement（Q3 三段式，用户拍板）：
    #    a) 快照完整（features 与 limits.max_projects 齐备）→ 直接采用
    #    b) 快照存在但字段不全 → 触发一次重同步（回源 S端）；
    #       同步成功 → 回到 a；仍缺/离线 → 按 tier 采用 STANDARD_FALLBACK
    #       （该档位当时版本的标准配置 = S端 ENTITLEMENT_DEFAULTS 的双端同表镜像），
    #       同时前端挂"权益数据异常，请联系客服"提示条，
    #       附问题详情（缺失字段/tier/fetched_at，一键可复制）
    #    c) 无快照（老 S端 / 首装未刷新）→ tier in FALLBACK_MEMBER_TIERS 判定；
    #       是会员 → 不限，否则免费 1 本
```

要点：
- **主路径不存在档位白名单**；FALLBACK 只活在"无快照"分支，兜老 S端 与首次升级未刷新的窗口；
- **STANDARD_FALLBACK 与 S端 ENTITLEMENT_DEFAULTS 是同一张表的两端镜像**（登记进 specs 防漂移），只用于"快照异常且重同步不可得"的极端分支——按档位标准给权限，不是瞎放开（Q3 拍板）；
- **完整快照下 is_member 由快照自证**：`bool(features) or max_projects 不限`——不再 or 档位白名单（避免"tier=pro 但快照是免费基线"这类矛盾输入被白名单翻案；本地过期判定在步骤 1 先行，天然防住过期矛盾）；
- 过期判定先于快照消费（快照可能比过期判断新鲜度低）；
- `deletion_pending` / `expired` 分支只发免费基线（features=[]，max_projects=1），语义与现状一致。

**叶子级定案（架构师自查 2026-09-06，代码实锤）**：
1. S端 查档位配置用现成 `TierRepo`（payments_repo.py:453），不新建仓储；
2. 登录写快照只有一处落点——`browser_auth(silent)` 的 code 0 分支（非静默路径只返回 auth_url，实际轮询保存仍走 silent 分支），无第二写入点；
3. 前端透传落点 = `verify_session()` 响应加 `entitlement` 原文 + `entitlement_degraded` 标志（三段式 b 分支置位，驱动前端客服提示条）；
4. Q4 的"仅 dev/test 保留 trial 宽限"用环境变量判据（如 `ENTITLEMENT_LEGACY_TRIAL=1`，仅本地 compose/测试注入；生产安装包不带）；
5. "回前台"信号：桌面壳 pywebview 无现成 focus 桥（已查证），**以路由切换为唯一保证触发点**（进工作台/书列表），window focus 事件尽力而为不作依赖；
6. STANDARD_FALLBACK 单一事实源：仓库级共享 JSON（如 `docs/contracts/entitlement-defaults.json`），S端/C端 测试各自读该文件与自己代码里的表对拍，防漂移。

### 8.3 后端门禁零改动

`require_ai_access` / `require_project_limit` / C端 `/check-auth` 响应形状全部不变——它们消费的 `is_member`/`project_limit` 自动变对。**verify 响应附带透传 entitlement 快照原文**（可选字段），供前端下一节用。

### 8.4 前端（渐进，两小步）

1. `LicenseProvider` 把 verify 响应中的 entitlement 快照存入 context；新增 `useFeature(key): boolean`（快照 features 包含判定；快照缺失时回退 `features.ts` 静态 memberOnly 口径）；
2. `features.ts` 语义微调：注册表从"判定依据"降级为"**词汇表 + 快照缺失时的兜底**"，注释同步改写。

**本期不做**：把 8 个消费组件逐个改成 useFeature（它们消费的 is_member 已经会变对，收益为零的搬砖）。逐 key 细粒度门禁等 MAX 上线带新功能时再做——那是这套机制的红利兑现，不是本期成本。

---

## 9. 全场景业务流程（100% 覆盖）

| # | 场景 | 流程与结果 |
|---|---|---|
| 1 | PRO 用户登录（本事故） | check-auth 返 pro+快照 → 缓存 → max_projects=null 建书放行、is_member=true AI 开 ✅ |
| 2 | 免费用户建第 2 本书 | 快照 max_projects=1 → 后端 403 + 前端 freeLimitReached 弹升级（现有链路） |
| 3 | 免费用户点 AI | is_member=false → require_ai_access 403 member_required → 统一升级引导（现有链路） |
| 4 | 会员未配 API Key | 403 之后 503 引导设置（现有链路，不在本设计范围） |
| 5 | 套餐到期 | expires_at 本地即判 → 免费基线；旧书保留可读可导出，不能建第 2 本 |
| 6 | 退款（frozen/revoked） | License.merge 跳过 → 下次 check-auth 快照自动缩成免费基线 |
| 7 | pro 未到期想上 max（升级） | **拍板方向=补差价升级**（差价按 pro 剩余时长折算，付完立即生效；独立立项，见 §12 遗留项）。立项上线前现网维持排队现状，entitlement **如实透传** S端 merge 判定，不做本地特判 |
| 8 | 注销撤销期（deletion_pending） | 免费基线 + 结构化提示（现有语义不变） |
| 9 | 断网/云托管冷启动 503 | code=-1 → 沿用上次快照，**绝不把会员降成免费**；useAuthHeal 现有重试路径兼容 |
| 10 | 老 S端（未部署新契约） | 无 entitlement 字段 → FALLBACK 名单（含 pro/max）→ 行为正确 |
| 11 | 老 C端 + 新 S端 | 字段被忽略 → 现状行为（事故仍在老 C端 上存在 → 发新 C端 是闭环必要条件） |
| 12 | 新档位 MAX 上线 | S端 配 max 的 entitlement + skus 加行 → 买 MAX 者自动拿更大清单；老 C端 对新 key 置灰按未开通 |
| 13 | 多设备 | 设备数仍由 S端 激活链路 own（sku.device_limit），本设计不动 |
| 14 | 本地作品与权益解耦 | 任何权益变化不触碰本地 SQLite；阅读/编辑/导出永远可用（双保险既定拍板） |
| 15 | 会话中途购买套餐 | 回到前台/进工作台触发静默刷新（Q1）→ 新权益即刻生效，无需重启——支撑"付完最快享受"拍板 |
| 16 | 本地快照数据不全 | 三段式（Q3）：触发重同步回源 S端 → 仍缺/离线则按档位标准兜底（STANDARD_FALLBACK）+ 客服提示条（问题详情可复制） |
| 17 | trial 无到期数据 | 生产按免费基线（Q4 收紧）；仅 dev/test 环境保留旧宽限 |

---

## 10. 安全与产品边界（立场声明）

- 权益快照明文存于本地 config.json，可被有意篡改 → **接受**。C端 门禁是 UX 级契约，不是 DRM；真钱与真权益的记账在 S端（订单/退款/对账）；
- **退款收回生效节奏（Q5 拍板）**：接受刷新节奏——网页退款确认后，用户下次回前台/启动/进工作台权益即缩水，窗口通常分钟级；不建推送通道（当前体量不值，且烧 CloudBase 点数）；
- 产品承诺不变：本地作品永不因权益丢失锁死；备份导出是跨机保底。

---

## 11. 演进 SOP（以后加档位/套餐/功能的动作卡）

**加新套餐（现有档位新时长）**：skus 插一行（period_days/价格/设备数）→ 完事，两端零改动。

**加新档位（如 MAX 上线）**：
1. tiers 的 max 行配 entitlement（features/limits）+ status 改 live；
2. skus 插 max×月/季/年；
3. 若 features 含 C端 未实现的新 key：C端 发版带实现（先行配置也可以，老 C端 忽略）。

**加新功能（进现有档位）**：
1. specs 登记新 FeatureKey →
2. C端 发版带实现（门禁点 + 未识别置灰）→
3. S端 tiers 对应档位 features 数组加该 key。

任何一条都不需要改判定逻辑——这就是本机制买的未来。

---

## 12. 落地切片与测试策略

| 切片 | 内容 | 测试 |
|---|---|---|
| PR-1 S端 | TierORM 加列 + pg_schema 不变量 + ENTITLEMENT_DEFAULTS + check-auth 下发 + 种子 SQL 脚本 | 扩展 `test_check_auth_extension.py`（下发形状/缺省回退/免费基线）+ `contract/test_c端_contracts.py`（契约形状）+ pg_gate 实测 |
| PR-2 C端 | config 快照读写/清理 + check_permission 优先级链（Q3 三段式/Q4 trial 收紧）+ **刷新触发点（回前台/进工作台，去抖）** + verify 透传 | 单测：pro+快照→不限/免快照+pro→兜底不限/过期→基线/快照缺字段→重同步→档位标准兜底/trial 无到期→生产收紧 dev 宽限/回前台触发刷新 |
| PR-3 前端 | LicenseProvider 快照 + useFeature + features.ts 注释改写 + **权益异常客服提示条**（问题详情可复制，链接复用 constants/support.ts 单源） | vitest（useTier/useFeature 快照与兜底两路 + 提示条出现条件）|
| 验收 | 本地 docker 栈：PRO 账号建第 2 本书成功 + AI 入口解锁；断网复测不降级；**中途购买→切回前台即生效演练** | e2e（打桩 check-auth 快照两态） |

**发布顺序约束**：PR-1 可独立上线（对老 C端 无感）；PR-2/3 合并后发新 C端 才算闭环（场景 11）。

**生产上线动作**（发版口，用户拍板后执行）：生产 PG 手工 DDL + 种子 SQL → pg_gate 验证 → S端 部署（tag/dispatch 或 MCP）→ C端 随下个版本带出。

**遗留项（不并入本特性）**：
1. 存量名纠正统一一个迁移立项——`codes` 表改名 `entitlements`（权益）+ `device_grants` 表/grant_repo/`/grants/*` URI 改名 authorization 族（设备授权，§2.1 裁定）——生产改名属大迁移，须单独立项评估（视图兼容/双写过渡/回滚），本特性只用旧名读写，不受影响；
2. **补差价升级（Q2 拍板方向，独立新特性）**：pro→max 升级订单，差价按 pro 剩余时长折算，付完立即生效；动订单类型/收银台/差价计算/退款联动，立项时须与本特性的权益快照联调（升级完成→刷新即生效）；
3. 排队机制的最终归宿待升级特性上线后重审（升级场景被补差价取代后，排队剩余适用面收缩）。

## 13. 与 P0 止血的关系

`MEMBER_TIERS` 追加 "pro"/"max"（1 行）= 本设计 §8.2 FALLBACK 名单的子集。**若本设计很快动工，P0 可并入 PR-2 不单独发**；若动工排期远，P0 先行止血。二选一，不重复做。

---

## 14. 待拍板项

**Grill 已拍板（2026-09-06，已折入正文）**：
- Q1 刷新时机 = 启动/登录 + 回前台 + 进工作台，无定时轮询（§8.1）
- Q3 快照异常三段式 = 重同步 → 档位标准兜底 + 客服提示（§8.2）
- Q4 trial 无到期生产收紧、dev/test 保留（§8.2）
- Q5 退款收回接受刷新节奏，不建推送（§10）
- Q2 升级走补差价 → 登记为独立立项（§12 遗留项 2）

**仍待拍板**：
1. **本设计是否批准动工**（PR-1→3；走不走 openspec 由用户定）；
2. P0 止血并入 PR-2（未反对即按此执行）；
3. max 的 DEFAULTS 暂给 pro 同款（planned，未反对即执行）；
4. 二期位置确认：S端 管理后台编辑 entitlement 配置、升级页功能矩阵公开接口；
5. 遗留立项排期：存量改名迁移、补差价升级（均不阻塞本特性）。
