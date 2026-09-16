## Context

禁用词数据现状三路：anti-ai KV（`fatigue_words_zh` 7 分类＋`structural_tic_patterns` 正则句式）、writing-style KV 的幽灵键 `fatigue_words`（6.0e 迁移遗物，v2 白名单外、UI 无入口）、文风硬约束里点名具体词的禁令句。三路在 `chapter_writer` 组装「原则与禁忌」段时汇合（chapter_writer.py:342-352），quality.py 程序化体检与 AI 体检另读 anti-ai KV。约束：C端 数据全量入库（KV 表，无文件）；桌面应用前后端同发版、无兼容窗口；style-settings-v2 已完成未归档，本 change 的 style-quant/prompt-crafting delta 以其归档后形态为基线。

## Goals / Non-Goals

**Goals:**
- 禁用词/句式数据单源：writing-style KV 的 `banned_words`/`tic_patterns`
- 设定页 8→7 项、禁用词句面板退役、编辑能力全部收敛进文风硬约束区
- 存量书无感迁移，拦截能力不丢（注入＋程序化体检＋AI 体检全保留，只换数据源）
- 冗余代码清零（表单/端点/模板/readiness 检查项/presets 死数据/幽灵合并行）

**Non-Goals:**
- 不改文风三区结构与量化蒸馏逻辑（v2 形态不动，只扩两键）
- 不做词表分类/标签体系（扁平化，见 D2）
- 不动 backup/export 契约（新键随全树打包自动带出，免升 FORMAT_VERSION）
- 不改 S端

## Decisions

**D1 收编形态＝硬约束区扩三块（禁令/禁用词/句式规则）**。备选：文风页独立第四页签（被否——用户拍板「与某个子集合并」）；全部扁平进 rules 自然语言（被否——tic_patterns 是机器可执行的结构化配置，混进自然语言会丢 quality 正则体检）。硬约束本义「这个身份绝对不能做什么」，禁用词与其同类；禁令块上限不变（`_MAX_RULES=100`，「3–5 条」只是 UI 建议值，实现不得按 5 截断），词表/句式两块另设上限（100/20），互不挤占。禁用词/句式两块为 Cfg 折叠组：默认收起、组头 sum 位常显「N 条」（design-language 高密度设定表单口径，先例＝简介「怎么写」六段模板）。

**D2 词表扁平化**。7 分类（总结叙事/抽象情绪/…）核实为纯 UI 组织元数据：chapter_writer 注入、quality 体检、AI 体检、蒸馏 append 四个消费方全部展平使用，分类键零语义。扁平后分类 hint（「本章讲述了、与此同时」类示例）移入块内占位文案。备选：保留分类 dict（被否——多维护一个无消费方维度）。

**D3 迁移＝统一迁移感知读路径＋完成标记位；anti-ai 原键原样保留（回滚安全）**。备选：KV 键改名 `anti-ai-legacy`（被否——KV 复合主键走 `route_relative_path` 路由，无键改名 API；无路由映射的写会漏到本地文件层破坏全量入库；删原键则回滚版本读旧键落空，禁用词能力静默归零，且断导出/导入兜底）；建书后一次性脚本（被否——桌面单机无脚本通道）。机制：
- 统一读函数（内部先迁移再 `read_style`）供全部消费方使用：style GET/PUT 入口、chapter_writer 写章组装、quality 体检、auxiliary 注入、ai_router 蒸馏/AI 体检——体检与组装不经过设定页也有迁移兜底（否则存量书未开面板前体检假通过）。
- 迁移动作：读 anti-ai KV（`PATH_TO_KEY` 映射原样保留，不新增 legacy 路由常量，避免 `SINGLE_FILE_TYPES` 凭空暴露通用端点）→ 词表 NFKC＋casefold 去重并入 `banned_words`、`structural_tic_patterns` 平移 → 写 style KV＋落完成标记（标记为 KV 文档内非白名单键，GET 边界剥离）。
- 幂等靠标记位（不能靠「每次重复合并」——作者删词后重迁会回灌）。存在性判定用 has_key＋内容非空双判（`read_yaml` 区分不了「行不存在」与「内容为空」）。
- **anti-ai 原键永久保留不删不改**：回滚版本读原键恢复全部能力；每书一行死数据（约 1KB），清理属后续独立版本。
- GET/PUT 入口顺序约定：先迁移、再读 raw、再合并写，避免迁移写覆盖并发 PUT。

**D4 蒸馏 append 服务端写入＋前端 commit 后回读合并**。收编前机器 append 写 anti-ai 键、人类 PUT 写 style 键，物理隔离所以 v2 的「机器段只走服务端函数」裁定即足；收编后两写共址同一文档，蒸馏 commit append 后作者持旧表单快照整键保存会覆盖丢词（确定性路径，非低概率竞态）。缓解：蒸馏 commit 成功后前端回读 style GET，只把 `banned_words`/`tic_patterns` 两键合入表单态与脏快照基线（不整表 set，保住用户未保存的三区编辑）；边界声明「人类保存＝以所见为准覆盖」。备选：append 按版本号 CAS（被否——为单用户桌面场景引入并发机制不成比例）。

**D5 旧端点与死代码直接删除**。桌面应用前后端同包发版、无第三方调用方：`POST /settings/anti-ai/words` 删除、通用 `/settings/anti-ai` GET/PUT 端点加退役分支（写拒绝给退役文案，沿伏笔退役先例；GET 一版周期原样返回现值，无前端消费方）、`AntiAiSettingForm.tsx` 删除、anti-ai.yaml.template 删除＋`filesystem/init.py` 种子条目删除（不删则新书种子会写入空 anti-ai KV 行，误触发迁移存在性检测）、`prompts/settings_anti_ai.prompt` 死文件删除、presets.py `fatigueWords` 删除（全仓零消费方实勘）、readiness `_check_anti_ai` 删除。

**D6 模板预填搬家**。writing-style.yaml.template：删 `fatigue_words` 幽灵键注释块；新增 `banned_words`（anti-ai 模板 7 分类 37 词全量展平平移，不做主观精选）与 `tic_patterns`（原模板 8 条句式规则平移，dict 形状）；anti-ai.yaml.template 删除。新书面貌与 v1 时代拦截能力等价。

**D7 归一口径兑现**：词去重统一实现为 `unicodedata.normalize("NFKC")` 后 casefold——style-settings-v2 的 spec 已承诺「半/全角、大小写归一」但实现只有 casefold，本变更触达这些行时顺带兑现，补测试钉住。

**D8 句式注入截断钉住**：提示词「禁止以下句式」维持现行为取前 5 条（编辑上限 20、机器体检全量 20），prompt-crafting delta 已写明；放开与否留待真实使用反馈。

## Risks / Trade-offs

- [迁移触发点分散多个内部读者，漏一处即体检/注入假通过] → 统一迁移感知读函数，全部消费方强制走它；e2e 补「仅跑体检/写章（不进设定页）的旧书」迁移场景
- [迁移后作者删词被标记位正确拦截，但标记位若 GET 忘剥离会污染前端表单] → GET 边界剥离进白名单测试；vitest 断言响应键集合
- [存量 5 个 e2e spec 邻近区受牵动，改动面大易假红] → 实勘收敛：settings-forms/creation-flow/design-parity-book 改写、foreshadow-settings 注释随手改、workbench-features/style-quant 仅回归；按 runbook 本地 docker 全量跑；`confirmPanel` 顺序无关判据沿用
- [parity 重录牵出设定页其他像素漂移，且 settings CASE 仅覆盖左栏＋简介面板、文风面板新版面不在门禁内] → 原型先行＋ADJUSTMENTS 登记；tasks 1.2 评估为文风面板新增 parity CASE，重录 diff 逐屏人工过目
- [扁平化丢分类提示，作者不知该填什么词] → 禁用词块 hint 文案给分类示例词；模板预填 37 词本身即示范
- [style-settings-v2 未归档，本 change 先归档会撞基线] → tasks 首项固定「先归档 style-settings-v2」，顺序门禁
- [幽灵键 fatigue_words 剥离与迁移叠加] → 归一函数内先并 `banned_words` 再剥键，单次归一完成；测试覆盖「幽灵键＋anti-ai 双源同时存在」去重
- [回滚后幽灵键疲劳词不还原（归一已剥离）] → 影响限幽灵键存量词（UI 不可见的少数派），anti-ai 原键词全部可回滚；接受并在发版说明不提

## Migration Plan

1. 前置：归档 style-settings-v2（sync specs）
2. 后端一次合入：归一边界扩两键（dict 专用归一）＋统一迁移感知读路径＋完成标记＋消费方切源（chapter_writer/quality/auxiliary/ai_router）＋端点退役/readiness 8→7/模板/init 种子/presets/prompts 清删
3. 前端：三原型改＋ADJUSTMENTS 登记 → 表单三块/SettingsView/useOnboarding/NovelWorkspace 改 → design:check＋parity 重录
4. 本地 docker 全量 e2e＋pytest＋vitest
5. 回滚：无 schema 变更，git revert 即可；anti-ai 原键保留保证回滚版本读旧键恢复全部拦截能力（唯一不还原的是幽灵键 fatigue_words 的存量词，影响面见 Risks）

## Open Questions

（无——收编宿主、词表扁平、句式规则保留三项均已拍板。）
