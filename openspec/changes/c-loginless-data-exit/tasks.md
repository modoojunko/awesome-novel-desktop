## 0. 原型先行

- [ ] 0.1 新建 `docs/design-c/prototypes/login.html`：s1 常规登录（收编 auth-card 现状，补历史欠账基线）／s2 升级卡·需要更新／s3 升级卡·暂时无法登录／s4 免登备份弹窗四步（借 .bk-* 家族）；文案逐字用 UX 规格（首答句/计数行/两场景诊断句/动词按钮）。验证：浏览器过四场景＋ADJUSTMENTS 登记两条
- [ ] 0.2 `lib/updateUrl.ts` 三级回落单源（UpdateNotice 的 DOWNLOAD_HOME 迁入）。验证：tsc＋两处消费同源

## 1. 后端：免登面与防护

- [ ] 1.1 `auth_local/middleware.py` 新增 `get_user_or_local`（复用主体，401→None 身份）；export start/status 换挂。验证：pytest——无会话调用不 401
- [ ] 1.2 `backup/export.py` 无主化：`user_id=None` 走整库口径（去 user 过滤、跳过 User/api_configs 段）；`include_config` 免登强制 false（服务端丢弃请求值）。验证：pytest——免登整机导出成功（含「无 User 行」夹具）；免登请求 include_config=true 不产配置包
- [ ] 1.3 三层防护：回环中间件（免登端点限 127.0.0.1/::1）；CORS 收窄（`main.py:534` 同源+dev 白名单）；导出路径守卫（target_dir＋single target_file 拒落 DATA_ROOT）。验证：pytest 矩阵——非回环拒/CORS 预检不批/路径守卫两形态
- [ ] 1.4 `legacy-db/status` 免登（供 change 3 迁入 UI 与登录页计数行消费）。验证：pytest 无会话 200
- [ ] 1.5 check-auth 透传 client_outdated 载荷（若 change 1 未先行）。验证：pytest mock code=3 透传

## 2. 前端：升级卡与免登导出

- [ ] 2.1 `UpgradeGate.tsx`：两场景分档（update-check 事实对照 vs 服务异常归因）；双信号 OR（client_outdated / 受阻态+has_update）；S端 不可达不渲染；真实锚点下载＋复制地址。验证：vitest 三态（需更新/服务异常/不可达）
- [ ] 2.2 `LoginPage.tsx` 接线：轮询命中 code=3→停轮询换卡；auth_notice 结构化 {kind:'upgrade'}；常驻「不登录也能备份作品」链。验证：vitest 轮询分支
- [ ] 2.3 `OfflineExportModal.tsx`：四步流复用备份屏（无配置开关、静态说明）；完成页次级出口按入口语境。验证：vitest 全流程（未登录→选目录→进度→完成）
- [ ] 2.4 登录页本地库计数行（legacy-db/status 或本地轻查询；空库变体文案）。验证：vitest 两变体

## 3. 门禁与回归

- [ ] 3.1 后端全量 pytest（新增免登矩阵/无主化/防护）；前端 vitest＋tsc＋design:lint/check。验证：全绿留输出
- [ ] 3.2 e2e：未登录完整导出一册→包内容断言；登录页升级卡 mock 场景。验证：spec 绿
- [ ] 3.3 汇报红线自查：免登面端点清单（含/不含）与 specs 对账。验证：清单落 change 目录
