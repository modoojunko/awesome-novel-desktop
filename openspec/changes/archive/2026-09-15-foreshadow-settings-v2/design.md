# foreshadow-settings-v2 · Design

## Context

现行伏笔＝`settings/hooks.yaml` KV 三数组（active/resolved/abandoned）整存整取，前端裸表单（`HooksSettingForm.tsx`），AI 仅旧单字段端点。设计稿 `docs/design-c/drafts/ai-novel-c端-伏笔设定.html`（v3）经两轮八份评审（前端/后端/架构师/UX＋前端/后端/测试/产品）与用户八项拍板定稿。同构先例：character-settings-v2（真表＋CRUD＋ops token＋AI 四行＋升级演练）。C端 生产＝本机 SQLite 单后端，`PRAGMA foreign_keys=ON` 级联真生效。

## Goals / Non-Goals

**Goals:**
- 伏笔升级真表 `novel_hooks`，章节引用精确到 chapter id，归档/写章消费方零猜测
- 台账＋伏笔卡＋AI 四行的面板重写（自动保存、ops token 撤销、确认门禁保留）
- 存量库经「留档＋空库＋v1 包恢复」升级，伏笔零丢失（导入器 v1 读窗是硬验收）

**Non-Goals:**
- mentioned_in_chapter_id 本期只迁不增（归档 UI 归写作期 change）
- 工作台侧埋坑体检入口留写作期 change
- ConfirmGuard 组件不新造（面板切换守卫沿现役两处 confirm）
- 不引入乐观锁/rev（单用户单编辑面单写路径；角色 rev 服务的是多面板 merge 场景，伏笔没有）
- 不做归档状态并入（mentioned 退出状态枚举，用独立列）

## Decisions

1. **真表而非 KV 加键**（用户拍板）：伏笔被 AI 注入、归档、AI 行作用域按 id 引用，KV 自由文本无法承载；表设计与角色 v2 完全同构（UUID 主键＋novels 单调 seq 计数器），消费方/测试/迁移基建全部复用。备选「KV＋id 字段」被否：数组归属与条目内 status 双源、章引用仍无 FK 语义。
2. **章引用存 chapter id（FK SET NULL），导出包存 ref**：运行态精确匹配（mentioned 标记、排除本章注入、埋坑体检）；包格式与运行态解耦——导入器恢复章时重新生成 id，包存 id 必悬挂。删除章/卷级联裁 SET NULL（ChapterCharacter/CharacterGate 先例同构；CASCADE 错杀伏笔、RESTRICT 打断现役删章流，均否），前端悬挂显示「章节已删」。
3. **持久化＝字段级防抖 PATCH＋串行队列**（沿 CharacterManager）：`save()`=flush 队列，gap3「确认前先保存」继续成立；「存草稿」对伏笔隐藏。备选「保留批存按钮＋整表 PUT」被否：与真表 CRUD 双模型并存必然漂移。
4. **撤销＝服务端 ops token**（沿角色先例）：删除即落库，撤销按原 id 原样恢复；「8 秒」仅是回执条 UI 自清窗口，token 有效期到下次操作/刷新。备选「延迟 DELETE（窗口内不发请求）」被否：窗口内崩溃即静默丢删、且与自动保存心智冲突；「重新 POST」被否：id 变号破坏「被引用都用 id」。
5. **AI 四能力＝无状态建议端点 `POST /ai/hooks/{action}`**（draft/payoff/audit/check，白名单字典，注册先于 `/ai/{stype}/{field}` 通配）：采纳一律前端组合 CRUD；h2 采纳＝前端 patch＋flush。上下文构建后端读真表与章纲（h3 判定常量服务端出，不采信模型自由文本）；缺输入走降级免调用（world_check D7 先例）。旧 `/ai/hooks/description`＋`settings_hooks.prompt`＋FIELD_GENERATABLE 项同批退役，旧端点 400 退役文案。
6. **确认判据「≥1 条描述非空（任意状态）」**：语义＝「这本书用过伏笔设定」；checker 数据源 KV→真表（`_check_hooks` 重写为真表查询，判据与 readiness spec 口径不变的部分不动）。确认后内容指纹变化→面板徽标「内容有变 · 待重新确认」（charStale 先例）。前端确认预检仅提示，按钮恒可点，后端门禁兜底。
7. **升级链走既定「指纹变更→整库留档＋空库→v1 包恢复」**，不写库内迁移：导入器补 v1 hooks 读窗（三数组→行；mentioned→active＋mentioned 列；章引用归一绑 ref，绑不上置 NULL 不丢行；priority/type 混形归一）；FORMAT_VERSION 2→3；`PATH_TO_KEY`/`SETTINGS_TEMPLATES` 摘 hooks（一处改三处生效）。
8. **词表单源 `settings/hooks_model.py`**（9 slug＋3 status＋长度 300＋priority 归一函数），前端镜像＋parity 测试（沿 character_model 先例）；priority 存储 Integer、API 兼容 int/str/high 归一、注入与展示统一 高/中/低。
9. **切片三批（用户拍板）**：批1 免费基座（表＋CRUD＋升级链＋面板＋选择器＋门禁）；批2 体检＋起草（PRO 锚点）；批3 拟收束＋一致性。一个 change，tasks 分批勾选；迁移（批1）是最大工程风险，独立暴露。
10. **落地顺序铁律**：原型转正（drafts→prototypes＋ADJUSTMENTS 登记，含 hk-* 词表映射表）→ 批1 → 批2 → 批3；每批 design:lint／design:check＜0.2%／tsc／相关 e2e。

## Risks / Trade-offs

- [第二次全量留档（角色 v2 刚消耗过一次）] → 若两版之间无对外发布则用户只感知一次；发布说明预告「升级留档＋导包恢复」；升级演练含删库救回 roundtrip。
- [导入器 v1 读窗遗漏＝伏笔静默丢失] → 读窗列入 P0 任务与六阶段演练断言（混形/mentioned/绑不上 ref/空描述样例逐条对拍）；pytest 迁移用例与演练双层把关。
- [卷章树响应补 id 的前端连带改动] → useOutline/useWorkbench 消费点同批适配（加字段向后兼容，旧前端多收一键不炸）。
- [300+ 章选择器可用性] → 按卷 optgroup 起步；验收场景含 300 章书目；搜索式选择器留后续。
- [8 秒回执窗口的 e2e 稳定性] → `page.clock` 快进（仓库首例，install 须先于 goto）；断言用常驻信号（保存态/徽标）而非 toast。
- [手动输入章号（未建章）被降级裁掉] → 讲解层明示「章未建先留空」；体检「建议收束章」一键补填登记为写作期 change 的第一个还债项。

## Migration Plan

1. 批1 合入即触发：老库启动→schema 指纹不符→`.legacy-*` 三件套留档→空库→提示从备份恢复（沿角色 v2 用户路径）。
2. 六阶段演练（扩 `upgrade_drill.py`）：seed-old（含混形种子）→ boot-new → import-v1（伏笔逐条对拍）→ export-v2 → roundtrip-v2（删库救回）→ downgrade；幂等重跑断言。
3. 回滚＝回退版本＋从 `.legacy-*` 留档或备份包恢复；format_version 3 导入端保留 ≤3 读窗，无前向锁死。

## Open Questions

无——落地口径（撤销路线/任意状态/未来章降级/charStale/三批/覆盖警示口径/退役 400/priority Integer）已全部经二轮评审与用户拍板落纸于设计稿 v3 稿头。
