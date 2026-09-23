## Context

五路评审裁定（关键事实）：
- `backup/router.py` 全端点 `Depends(get_current_user)`；`export.py:451-461` 按 user_id 过滤且 `db.get(User, user_id)` 无行即 500——事故场景（登不进的机器）恰恰可能 User 行残缺（架构评审「必须现在做」#1）。
- `main.py:532-537` CORS `allow_origins=["*"]` 偏宽（顺带修复）。
- 免登导出无开关：前端「配置包含密钥开关默认关」方案被否（开关存在即意味着免登态可导 api_key 明文，任何本机进程可窃）——红线执行问题非文案问题（架构评审矛盾 #2）。
- UpgradeGate 双信号：authorize 拒绝只发生在用户点了登录之后，「用户不点登录就永远无标记」是死角（架构评审 B7）——本地 update-check（已免登，`update_check.py:244-246`）作第一信号。
- 旧 C端 救不了：被卡的旧 build 里没有 UpgradeGate 代码，其出口是已热修的 S端 /auth 页——本 change 价值是「下一次协议变更时新 build 就地自愈」（架构评审关键结论，写进动机防验收误判）。
- UX：升级卡情绪主角=首答句+计数行，不是按钮——「先备份作品」恒 secondary，升为主按钮等于向恐慌用户确认「先抢救再跑」。

## Goals / Non-Goals

**Goals：** 任何登录态/网络态下本地作品可打包带走；「需更新」用户一步拿到下载；配置包永不免登；免登面被三层防护钉在本机。

**Non-Goals：** DB 版本化与旧库迁入（c-db-generation-migration）；离线只读模式（不做清单）；导出包加密（manifest 校验才是真需求）。

## Decisions

1. **无主化整库导出**：免登分支不造「本地默认用户」——直接去掉 user 过滤（数据全归本机主人）。被否：构造 system user 行（引入假数据）。
2. **无开关而非默认关**：免登 UI 只有静态说明「配置包含敏感信息，登录后可导」。被否：默认关开关（存在即漏洞面）。
3. **防护=中间件而非 token**：一次性 token 防不了同源 drive-by（SPA 能拿到的任何页面都能拿到）；「回环+CORS 预检封死+路径守卫」组合封读写两端。token 被论证无效而否决。
4. **三级回落下载地址单源** `lib/updateUrl.ts`：S端 hint > 本地 update-check 缓存 > 官网常量；UpdateNotice 同引（收敛两处 DOWNLOAD_HOME）。
5. **免登备份弹窗复用备份屏四步流**（.bk-* 家族）：不发明新流程；完成页次级出口按入口语境取「去下载新版」（受阻态）或「打开所在文件夹」（常态）。

## Risks / Trade-offs

- [Docker 0.0.0.0 部署被局域网触达免登面] → 回环中间件硬拒；部署文档标注。
- [免登导出与登录态任务抢跑] → job_runner 单飞互斥（409 既有语义）。
- [update-check 在 dev 版本跳过] → UpgradeGate 主数据源是 S端 载荷，update-check 仅兜底，dev 可演示完整链路。

## Migration Plan

1. 后端（鉴权重排+防护三层+透传）pytest 绿 → 前端（login.html 原型 → UpgradeGate/OfflineExportModal/updateUrl）vitest/e2e 绿。
2. 依赖：change 1 的 code=3 信号到位则升级卡双信号全量生效；未到位时第一信号（update-check）先行可用——两 change 无硬序。
3. 回滚：revert 即回到全登录墙（无数据面风险）。

## Open Questions

（无。）
