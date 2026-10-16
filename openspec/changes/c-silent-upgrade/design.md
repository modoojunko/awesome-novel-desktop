# c-silent-upgrade · 设计

## Context

C端 是单进程桌面应用：pywebview 壳 + 进程内 uvicorn 线程（FastAPI/React），Windows 走
Inno Setup 安装器（数据便携式跟随安装目录 `data\`），macOS 走 .app + dmg。既有升级链
止步于「检测＋提示条＋官网手动下载」。机制验证已在 `silent-upgrade-lab` 分支完成并经
boss 真机五判据验收（免 UAC 静默覆盖、装完自动回、数据逐字节不动）；完整背景与判例见
`docs/design-c/drafts/ai-novel-c端-无感知自动升级-设计草案.md`（v3，含双路评审 21 项修订）
与 `docs/design-c/drafts/ai-novel-c端-一键升级-需求.md`（用户可见面四步口径）。

## Goals / Non-Goals

**Goals**

- 程序面升级一次点击：后台下载校验就位 → 就绪通知 → 「重启更新」→ 静默生效自动回新版
- 数据零风险：安装器与 `data\` 零接触；无损带回知情链一条不改
- 失败一律退回手动链；发布侧总闸可秒停；全程进度可见

**Non-Goals**

- macOS 自动链（v1 只 Windows，架构留位）；增量包；强更；便携版自动升级
- 数据迁移免同意（带回卡照旧）

## Decisions

1. **安装形态＝复用真安装器静默跑，不做目录自换**。安装器是唯一掌握卸载登记/快捷方式/
   ACL 语义的组件；自换目录需拆「安装目录＝数据目录」铁律。免 UAC 靠
   `PrivilegesRequiredOverridesAllowed=commandline`＋`/CURRENTUSER`（真机 V-1 立碑）。
   自动拉起用 `/AUTOLAUNCH=1`（带值；`[Run]` 项不带 `skipifsilent`/`runhidden`）。
2. **安装时机＝用户点击后、退出链尾部**。运行中 exe 被锁，只有本进程死了才能覆写；
   `quit_app` 桥（destroy）→ 既有优雅退出链 → 尾部 apply 段（TTL/sha/平台四闸）→
   detached Popen（argv 直传，禁止 cmd 字符串拼接）→ `os._exit` 放锁。
3. **「重启更新」秒回契约**：点击只做闸门复核＋落一次性标记（TTL 10 分钟，后端唯一
   写者）；34MB 完整 sha 复验放退出链（关窗后用户不盯屏）。真机实锤：复验放端点内
   3–5 秒无动静会被当成没反应手关窗。
4. **状态机与并发纪律**：`update-check.json` 的 `auto` 键 idle→downloading→staged→
   applied；全部读改写走同一把锁＋tmp/原子替换；下载单飞锁＋代际号＋取消位；失败
   矩阵分传输类（退避重试）与环境类（终止等下窗）。
5. **applied 记账语义**：记账标记只在「没有更新的就位包」时生效——真机实锤 marker
   永久压制 staged 会让就绪入口消失。
6. **触发与展示解耦**：自动下载触发不理会横幅关闭记忆；手动兜底入口仅在自动链停摆
   超时后出现（双轨收敛）。
7. **渠道与信任**：manifest v2 顶层 Ed25519 签名（独立 update-k1 钥，复用提示词包
   验签规则）；配钥前过渡期仅 sha256 双验＋可信域出站校验（下载线程用同步版校验）；
   发布顺序恒为包→manifest。实验渠道 `download/lab/latest.json` 与生产渠道物理隔离。
8. **暂存目录＝`DATA_ROOT/updates`**：安装器覆写清单不含 `data\`，暂存天然受保护；
   状态文件多写者债以单锁＋原子写偿还。

## Risks / Trade-offs

- 全量包 ~70MB/版（无增量）——CDN 可承受，v2 再议
- per-user 覆盖 admin 装的「设置→应用」双条目外观（Inno 自动改名去重缓解）＋
  公用桌面图标可写性环境相关（更新器恒带 `!desktopicon` 兜）
- 杀软对新落盘 exe 首扫可能拖垮/杀掉首启（真机实证一次）——二启正常；手册给加白引导
- manifest 签名欠账（过渡期 sha256-only）——update-k1 配钥后强制，任务在列
- 安装中断的程序目录混合态无自动回滚（数据无恙）——依赖覆盖安装幂等重跑

## Open Questions

- 无（五笔拍板待 boss 确认：钥独立／单产物／默认开／回滚源现状／迁移文案，均不阻塞
  本 change 结构，只影响 P3 细节与文案）
