# Proposal: c-loginless-data-exit

## Why

2026-09-19 事故暴露的 C端 结构性缺陷：备份导出全部端点在登录墙后（`backup/router.py` 全量 `Depends(get_current_user)`），登录被拒的用户**没有任何 UI 途径导出本地数据**；登录页无升级出口（用户被踢到浏览器授权页来回猜）。产品红线裁定：**数据出口不设墙**——登录保护的是生成服务，不是用户自己硬盘上的文件。

## What Changes

- **免登导出（资产包）**：`export/start`（kind 限 backup/single，`include_config` 服务端强制 false）与 `export/status` 移出登录墙；免登态导出=**整库无主化**（忽略 user_id 过滤——事故场景恰恰可能 User 行残缺，现行 `db.get(User, user_id)` 会 500）；配置包（含 api_key 明文）**永不免登**，离线 UI 无开关只有静态说明。
- **三层防护替代 token**：①回环来源中间件（免登端点限 127.0.0.1/::1；Docker 0.0.0.0 场景的硬边界）②CORS 从 `allow_origins=["*"]` 收窄（生产同源+dev 白名单；封死浏览器 drive-by 读写两端）③导出目标路径禁落 DATA_ROOT（**含 kind=single 的 target_file 整路径**——那是能直指 novel.db 的写路径）。
- **登录页升级卡（UpgradeGate）**：check-auth 返回 client_outdated（s-auth-outdated-signal 契约）→ 主按钮区就地替换为升级卡；**第一信号=本地 `/api/update-check`（免登、已有 has_update/download_url）**，client_outdated 为第二信号（两信号 OR——防「用户没点登录按钮就不产生 authorize 拒绝」的死角）；S端 不可达（code=-1）绝不渲染升级卡（防误闸）。
- **登录页常驻免登导出入口**：「不登录也能备份作品」文字链（未受阻态也在——被踢出的用户要能救数据）。
- **`legacy-db/status` 免登**（现挂登录墙，前端零消费者——c-db-generation-migration 的迁入 UI 将消费它）。

## Capabilities

### New Capabilities
- `loginless-data-exit`：免登数据出口边界（哪些端点免登/永不免登、无主化口径、三层防护）＋登录页升级卡与常驻导出入口。

### Modified Capabilities
- `backup-restore`：export start/status 的鉴权语义与免登口径（整库/强制无配置包/路径守卫）。

## Impact

- **后端（client/backend）**：`backup/router.py`（鉴权面重排＋路径守卫）、`backup/export.py`（`user_id=None` 整库口径＋include_config 强制位）、`auth_local/middleware.py`（新 `get_user_or_local`）、`main.py`（CORS 收窄＋回环中间件注册）、`auth_local/service.py`（check-auth 透传，若 change 1 未先行则随本批）。
- **前端（client/frontend）**：`LoginPage.tsx`（outdated 分支＋UpgradeGate＋常驻导出链）、新 `UpgradeGate.tsx`、新 `OfflineExportModal.tsx`（复用备份屏四步流与 .bk-* 家族）、新 `lib/updateUrl.ts`（下载地址三级回落单源，UpdateNotice 改引）。
- **原型**：新建 `prototypes/login.html`（登录屏从未有原型基线——补历史欠账：常规态/升级卡两场景/免登备份弹窗）；`ADJUSTMENTS.md` 登记。
- **测试**：后端 pytest（免登矩阵：免登含配置包→422、import 免登→401、DATA_ROOT 目标→拒、无 User 行→整库成功）；前端 vitest＋e2e（未登录走完整导出）。

## Design Impact

- 受影响端：仅 C端。不触两端共享段。
- 受影响屏/弹层：登录页（升级卡替换主按钮区＋常驻导出链＋免登备份弹窗）；S端 授权页文案对齐在 change 1。
- 对象状态：升级卡=pill warn「需要更新/暂时无法登录」两档（§5 warn 档，err 不用于登录受阻——无不可逆后果）；进度/完成态沿备份屏既有（dot-live/locked/ok 圆徽）；免费/PRO 在导出与升级卡**零出现**（数据救援现场出现销售信号摧毁信任，UX 四条论证）。
- 文案（UX 规格，逐字入原型）：首答句「你的作品都在这台电脑上」＋可核对计数（5 本书 · N 字，完好无损）；主按钮=「去下载新版」、次按钮=「先备份作品」（恒 secondary——恐慌由证据化解，不由按钮排序放大）；「版本过旧」措辞全站禁用。
- 原型先行：**需要**——login.html 新建（含四场景）；ADJUSTMENTS 登记两条（登录屏补基线、免登备份弹窗并入 backup 家族口径）。
