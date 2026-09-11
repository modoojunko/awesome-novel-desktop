# world-setting-v2 技术设计

## Context

- 设计事实源（已评审定稿，本 change 的实现基准）：
  - 前端评审稿 `docs/design-c/drafts/world-setting-draft.html`（v2.7，交互全演示，前端已确认无意见）
  - 后端架构规范 `docs/design-c/drafts/world-setting-backend-architecture.md`（574 行，DDD 四层落位映射 + D1-D12 拍板 + 迁移映射表 + 测试规范）
  - 三方工程评审（架构/前端/后端）P0-P2 清单已全部吸收：P0 修入 v2.5-v2.7，P1/P2 进本 change 任务
- 现状约束：C端存储为本机 SQLite 单库（novel.db，aiosqlite，零 PG）；alembic 不覆盖 KV 值 → 迁移只能做「读边界归一化 + 惰性落盘」；settings 为 KV（project_settings 表 (root_path,key)→JSON）；`inject_world_setting` 与 `_check_world` 仍按旧十字段消费（P0-3/P0-4/P0-5，见架构规范 §3.5 T1-T6）

## Goals / Non-Goals

**Goals:**
- 五可见格 + 06 名目条目折叠组的面板落地（前端评审稿 1:1）
- 契约 v2（校验/归一化/legacy 回滚/映射表）与旧消费方同步改造（readiness/注入/prefill）
- 右栏 AI 五行 + 一致性体检 + lore-keeping（归档回写）全链路
- 测试与界面测试（pytest / vitest / playwright e2e）作为一等任务交付

**Non-Goals:**
- 角色面板、主线、伏笔等其他设定面板的改版（人物 lore 只出路由提示，不落地）
- S端 任何改动
- `_legacy` 子树的主动清理（留待后续 cleanup change）；story/engine 旧引擎整体去留（只做 terrain 读 stage 的最小修复）
- ai_router「路由内读 story.yaml」的层级违例收敛（控制爆炸半径，默认不动）

## Decisions

沿用后端架构规范 D1-D12 拍板（详见规范 §9 与附二大白话版），此处只列影响任务拆分的关键项与前端补充决策：

- **D-全局0 实现基线＝设计文档，非旧实现**：实现只以「前端评审稿 v2.7 + 后端架构规范」为依据从零新建；旧世界设定实现（WorldSettingForm.tsx、字段级 AI 弹窗路径、旧 AI 字段集、旧 settings_world.prompt、ai_prefill 世界预填）一律删除，不作为参照或改造对象。旧系统唯一的残留接口是**数据**：老书已填 KV 按映射表一次性迁入（normalize_world 纯函数，输入旧 dict 输出新 dict），迁移动机是保住作家已写内容，不是兼容旧代码。

- **D-前端1 组件拆分**：新增 `KvListEditor`（受控 `rows:[{key,value}]` + `suggests?` + key/value 占位 + maxItems）承载 05 铁律与 06 名目；04 势力独立 `FactionRows`（{name,note}[]，无 suggests，4 行软提示）。建议名目一律 `button.cap`（键盘可达），禁 span+click。
- **D-前端2 右栏接线**：SettingsView world 分支照 genre 模式接 `AiWriterAssistant`（rows=w1/w2/w3/w5/w6）+ 面板 `runWorldAi` 句柄 + `onReceiptChange`；格头「AI 帮填」快捷钮与右栏行走**同一入口**（ref 分发 + onBlocked 分流），禁止绕过 guard 直调。
- **D-前端3 采纳快照**：采纳/撤销必须取 ref 即时值（React 化的闭包坑，题材页 02 为反面教材）；回执语义与 ChangeReceipt.record 一致（后一条顶前一条）。
- **D-后端1 归一化挂读边界**：`normalize_world()` 应用在 GET/readiness/写章加载/AI 输入组装四处；存储字节不动，PUT 才写 v2（`_legacy` 落盘）。纯函数 + roundtrip 测试。
- **D-后端2 端点注册顺序**：`/ai/world/check`、`/ai/world/lore-suggest`、`/ai/world/lore-apply` 注册在 `/ai/{stype}/{field}` 通配路由**之前**，并加路由解析回归测试（intro 先例）。
- **D-后端3 铁律注入**：constraints 渲染进写章红线区（独立预算 ≤300 字、逐条完整），世界块（600 字预算内）不含铁律；截断以整条为单元 + 显式「N 条从略」。
- **D-后端4 lore 幂等**：lore-suggest stateless；lore-apply 以 `(key, origin)` 幂等合并（factions 按 name），origin=`vol-N-ch-M`；`ai_summary` 偏好与 lore 建议解耦。

## Risks / Trade-offs

- [回执单条语义：连续采纳只保留最后一次撤销] → 题材页既有拍板语义，口径已写明，e2e 断言只验最后一次
- [v2 落库后旧消费方未同步 = 确认 400 / 注入变空] → T1-T6 修复清单为 change 必做任务（后端组），合并前跑全量 pytest + schema_check
- [自由条目注入 prompt 的注入风险] → 后端长度上限 + 控制字符过滤 + 「数据区与指令区分离」（用户文本只进数据占位符）；前端 esc() 只防 XSS 不防 prompt 注入，安全口径以后端为准
- [世界块 600 字预算被历史账本增长击穿] → 历史注入取「最近 N 条」顺序截断 + 显式从略；钉选策略留后续批次
- [draft HTML 与 React 的 parity 漂移] → 实现按 prototypes/CLAUDE.md 规范自查；徽标用三态服务端口径（draft 内 syncBadge 仅演示）、回执条落 panel-foot（非 draft 的内容区底）

## Migration Plan

1. 合并前：后端 `normalize_world()` + `_legacy` 机制先上线（读边界生效，旧数据原样保留）
2. 前端五格上线后：作家首次 PUT 即写 v2；未触碰的书保持旧字节，读时归一化
3. 回滚：回退部署版本即可读 `_legacy`（旧代码认旧形状）；一个版本周期后另立 cleanup change 处理 `_legacy`
4. `settings_world.prompt` 重写与 `ai_prefill` 退役随同一 change 上线，避免新旧形状混写

## Open Questions

- lore-suggest 的确认入口形态（世界页 06 内联 vs 写作页轻提示）——后端契约两种皆兼容，前端实现时定
- D3 上限数字的产品终值（基线已给，可调）
