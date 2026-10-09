## Context

自动弹窗链路：`NovelListPage` 挂载 effect 每次进书架静默探测 `/prompt-pack/probe`（`claimPackProbe` 只是 StrictMode 双挂载去重的在途槽，非一次性闸）；probe 返回「未安装」（`!installed_version && source !== "dev" && reason !== "min_client_version"`）即 `openPackModal({mode:"install"})`，install 模式开窗即自动跑安装，失败落 `failed` 态（「写作能力没有就绪」）。`PromptPackModal.close()` 只做停轮询＋关窗＋弹窗队列出队，**无任何持久化**；更新模式 confirm 页「暂不更新」也只 `close()`。

现成事实：手动入口已存在（账号面板「写作能力」菜单项，`mode:"manual"`）；AI 功能无包时报 503 `prompts_missing`，前端静态文案指引去账号菜单。localStorage 先例三种：`MigrationBanner` 永久关闭（`"1"`）、`ExpiryNoticeBar` 按日 key、`onboarding-dismissed-${projectId}` 按项目。

规格现状：`prompt-pack-delivery` 「暂不更新」明确写了「下次进入『我的作品』页再探测提示」——更新模式的重弹是**现行规格行为**，本 change 同时修首装与更新两处，属规格级变更。

## Goals / Non-Goals

**Goals:**
- 首装弹窗关闭后持久化不再自动弹；安装成功后记忆自愈清除。
- 更新「暂不更新」按 CDN 版本号记忆：同版本不重弹，版本变化自动恢复提醒。
- 手动入口（账号菜单）完全不受关闭记忆影响。

**Non-Goals:**
- 不改 probe 契约、后端零改动（版本锚点直接用 probe 已返回的 `latest_version`）。
- 不做「prompts_missing 报错时按需弹安装窗」新链路（现文案指引已可用，另行立项）。
- 不动 shell-dialog-queue 入场约束、进度期锁定、探测静默语义。
- 不引入服务端同步的记忆（关闭记忆是纯本机 UX 偏好，localStorage 足够；换机/清浏览器数据后恢复提醒可接受）。

## Decisions

- **D1 存储形态：单个 localStorage key 存 JSON 两个字段**。`pack-modal-dismissed` = `{"install":true,"updateVersion":"0.30.x"}`。`install` 布尔（首装关闭）；`updateVersion` 字符串（暂不更新时所见的 `latest_version`，空缺表示无记忆）。备选：两个独立 key（`pack_install_dismissed`/`pack_update_dismissed`）——读写都散在两处，且两者同生同灭于同一弹窗的 close 路径，单 key 一次读写更不易漂移。key 命名沿用先例的蛇形＋语义后缀风格。
- **D2 首装记忆的生命周期：写入于 close，清除于安装成功**。任何非锁定态出口（×／Esc／遮罩，failed/confirm/done 态均可关）只要包仍未装上即写 `install:true`；`sync` 完成成功（done 态确认/轮询到 installed_version）时清除。备选：按天记忆（ExpiryNoticeBar 式）——反馈原话是「能忽略，不再弹」，按天会复发，不取。
- **D3 更新记忆以版本号为锚：暂不更新记 `latest_version`，probe 的版本号≠记忆值即恢复提醒**。备选：永久记忆（同 MigrationBanner）——更新提醒带修复/召回价值，永久静默会让用户永远错过新包；版本锚是最小侵入的重臂方案。已装最新后该字段自然失效（update 弹窗只在 `update_available` 时入场）。
- **D4 拦截点放在 NovelListPage 自动弹两处**（`update_available` 分支与 install 分支各查一次记忆），`openPackModal` 本身不加闸——manual 模式与未来按需弹链路走同一 `openPackModal`，在源头加闸会误伤手动入口。
- **D5 helper 就近放 `lib/packProbe.ts`**（probe 数据的家，读写标记与 probe 消费同域，测试可独立桩）；不新开文件不进 coverage-contract 新户。

## Risks / Trade-offs

- [用户误关首装窗后忘记装包，AI 功能一直不可用] → 兜底已有三层：账号菜单「写作能力」未就绪态常显；AI 报错文案指向该入口；工作台右栏四态卡兜底。若实测仍有人迷路，再立「prompts_missing 按需弹窗」小 change。
- [localStorage 被清（换机/清数据）→ 循环弹窗复发] → 复发即回到现状行为，不劣于基线；且 v0.30+ 网络层已修，装上即止。
- [更新版本锚依赖 probe 成功返回的 `latest_version` 与弹窗时一致] → 记忆写入时以弹窗入场所用 probe 值为准；CDN 指针回滚（版本号变小）同样视为「变化」恢复提醒，语义安全。
- [存量 e2e 依赖「未装必弹」的用例会红] → 属预期行为变更，用例同步改为「首挂弹、关后再挂不弹」；dev 态（source=dev）本就静默，本地 e2e 面不受扰。

## Migration Plan

纯前端小改，随常规版本发布；无数据迁移。回滚＝还原前端改动，localStorage 残留 key 无害（旧代码不读）。

## Open Questions

（无）
