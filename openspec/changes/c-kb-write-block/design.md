# c-kb-write-block · Design

设计权威＝`docs/design-c/drafts/ai-novel-c端-写作知识库-整体方案.md` §7.1（终态消费两层组装）＋ §12（容量/扩展三铁律）。本文件只记实现决策与落点。

## D1 注入点与两路径

- 生成路径 `write/router.py:209`、续写补足路径 `write/router.py:507`——均在 `WRITE_CLOSING_LINE` 追加之前插块：`prompt = f"{prompt.rstrip()}\n\n{block}{WRITE_CLOSING_LINE}"`（块含尾部空行）。
- 块为纯运行时拼接：SHALL NOT 写入章级提示词行、SHALL NOT 进 `prompt_sources.py` 持久化编辑区（该端点只读库行不变）。
- 弹窗只读区数据源＝生成响应事件（SSE 新增 `write_block` 事件携带块文本＋清单引用），前端不二次拉取。

## D2 选择器（kb/match.py 新模块，kb SHALL NOT import write/ 方向不变）

- 信号抽取（只读章纲）：出场角色＝章纲角色字段直取；scene/emotion/chapter_pos＝概要与剧情条目文本经 `kb/concepts.py` 既有词表＋**新增别名表**（`_SCENE_ALIASES/_EMOTION_ALIASES`，每场面类 ≥5 同义词）确定性归类；卷位＝卷纲＋章节序。归类不出→不硬猜（scene 为空即不出题材场景条目）。
- 候选短名单：`kb_entry_tags` 两段式（dim=concept 手法/文风/文笔 ＋ scene/emotion/chapter_pos 命中 ∪ slot 基线），≤200 条稳定排序（id 序）；**SHALL NOT 对 payload_json 全表扫描**（§12 铁律）。
- 打分＝匹配度×有用率×新鲜度；有用率读 `kb_prefs`（账号级 (user_id, entry_id)，未标记＝1.0）；新鲜度＝updated_at 衰减（30 天半衰）。配额：手法 ≤6、场景定性写法 ≤4；估算 >2K tokens 时按分数截断。
- 零命中→返回 None（调用方整块不拼）。

## D3 复用语义（重试字节一致）

- `kb_match_runs`：章＋brief_hash 唯一索引已建（批1）。首生成＝创建 run＋items（decision/score/reason 逐条）；同章同 hash 重试＝复用 run 拼块，SHALL NOT 重新选择。
- brief_hash＝章纲素材摘要 sha256（characters＋summary＋plot_items 序列化）；素材变→新 run（旧 run 保留不清理，查询单 run 时取最新）。
- 续写/补足：按章节复用当章**最新** run（不比对 hash）——spec「按章节复用」口径。

## D4 量化维度影子并轨

- 判据：条目文本含量化词眼（句长/字数/段落/词频 + 数字/比较式，正则表常量）→ 该条目不走写法块，走 `write/style_shadow.py` 的影子覆盖渲染（put_style_shadow 链，声明「以本场值为准」）。
- 影子写入时机＝启用库快照/同步时随基线落（非写章时）——`kb/snapshot.apply_members` 扩：量化场景条目落影子块；写法块组装时跳过这些条目（防同槽双写＝冲突率断言 0 的来源）。

## D5 回声闸（<8 字公共串）

- 入库闸（`kb/gates.py` 新检查）：条目 instruction/example 与收尾行/分量行/续写行（`WRITE_CLOSING_LINE` 等常量）最长公共子串 ≥8 字 → 判据式拒收（可读文案「与系统固定文案撞句，请改写」）。存量条目不回扫（生成时组装侧跳过兜底）。
- 组装守卫：写法块拼装前对每条再跑一次 <8 字检查（防存量脏数据），命中即跳过该条并记 run.reason。

## D6 留痕与反馈

- run/items 落库在生成准备期（选择完成后、模型调用前）——失败章也有 run（status 字段）。
- 反馈端点：`POST /api/kb/entries/{id}/pref`（body useful: bool）→ kb_prefs upsert（useful→weight↑ drop→weight↓，语义：有用率＝useful/(useful+drop)）；清单端点 `GET /api/kb/match-runs?novel_id&chapter_ref`。
- 前端：提示词弹窗只读区（「本章写法块 · 自动注入不落库」）逐条附「有用/没用」钮——数据来自 SSE write_block 事件；标记即调 pref 端点（无确认弹窗，可重复点＝可改口）。

## D7 评估进 CI

- 别名单测：每场面类 ≥5 同义词判例（`tests/test_kb_match_aliases.py`）。
- golden 集：`tests/test_kb_match_golden.py`——按场面类分布造章纲 fixture（每类 ≥5 章）＋固定知识库 seed，断言选集一致率 100%（同 seed 确定性）。
- 冲突率断言：同槽双写次数＝0（写法块条目 ∩ 影子条目 ＝ ∅）。

## D8 明确不做

- 不做 P1 LLM 选择器（规则不够时降级提示，不入库）；不做逐段选择；不做跨题材混合块；不动 S 端与提示词包（块文案代码常量）。

## D9 终态路线与四角色评审决议（2026-11-02 四 Agent 并行评审：后端/架构/测试/提示词）

四角色评审 40+ 条发现合并去重后的决议。P0 三条全在写章主链上，收进**新增批F（架构加固，先于批D）**。

### 批F（P0 修复，先于批D 实施）
1. **run 竞态**：同章双开流首生成，后到者撞 `uq_kb_match_run` 唯一键被宽 except 吞 → 会话 pending-rollback 中毒、成功生成误报失败。修：插入处显式 catch IntegrityError → rollback → 重查赢家 run 复用。
2. **重试字节一致破口**：KbMatchItem 不快照文本，条目编辑后同 run 重建出不同块。修：items 加 `text_snapshot` 列（run 创建时固化），重建走快照。
3. **brief_hash 不含库域**：换库后同章同素材复用旧库 run。修：run 加 `domain_fingerprint` 列（启用库 id 集），复用前必须匹配；spec 补「启用库域变更后 SHALL 重新选择」。
4. **影子残留**：素材变更/停用库后旧「知识库·」影子行继续注入（绕过停用语义的侧信道）。修：新写影子前清同章全部「知识库·」行；`_binding_domain` 判空路径与零命中路径同样清；ghost 章过滤补齐。
5. **条目文本结构消毒**（design §7.1 补丁5 兑现）：指令含换行或行首结构标记（#/---/-/【）或「【本章写法指引】」字样 → 入库硬拒＋组装守卫同口径（防伪节标题/伪块首注入）。
6. **量化影子渲染分源**：value 只提取数值短语（「句长不超过12字」），condition 拆场面短语；渲染「句子与段落：句长不超过12字（交手场面适用；本章覆盖：知识库·…）」——「约 X」槽位不再塞整句（语法断裂）＋场面条件不再被抹成全章覆盖。
7. **条件标签只发命中维度**：`_tag` 改按选择器 reason（本章命中维度）发标签，消除「选择器 OR vs 标签 AND」错位；块首 v2：「以下条目只约束写法，不改变剧情，不新增人物、事件或设定；与反AI结构红线或输出契约（含场景分量与字数要求）冲突时，红线与契约优先；中括号＝本章已命中的入选条件，以·分隔场面、情绪、章位；带场面标签的条目只在该类场面执行，其余条目全章适用。」（两份 spec 同步）
8. **列预留一次到位**（P1 选择器前置，与 2/3 共用一次列交集迁移）：run 加 `selector`（rule|llm|rule_fallback）/`brief_json`；`extract_signals` 上移 write/write_block.py（kb 从此不认识章纲表）；`digest_candidates()` 公开化（候选摘要喂模型用）。
9. **「日常」信号死值**：文戏别名集删「日常」（独立场面类被文戏吞并）；normalize 精确匹配优先。
10. **spec 减负**：「AI 关系整理」Req 移出本 delta（随⑦独立变更）；「混合型消费」Req 是一阶段已实现行为——保留但 proposal 记账；仲裁句 v2 两份 spec 同步。

### P1/P2 记账（批F 不做，挂账）
- style_shadow PUT 全量替换会抹 KB 行（双写者冲突）→ 批D 前端保存链路保留「知识库·」行或后端 PUT 改合并
- 新鲜度语义漂移（updated_at 衰减 vs 设计稿「近 N 章未用过」防轮播；last_used_at 不被 match 写）→ P1 前定口径，倾向 (b) 命中写 last_used_at
- kb_match_runs/items 无清理策略＋备份全量导出增长 → 定「每章保留最新 run」＋挂 sweep 通道；spec 措辞改可实现口径
- SSE items 缺 title/concept、转影子条目三处不可见 → 批D 前补（decision="to_shadow" 复用列）
- pref 语义（缺缺省记没用/增量 vs 改口/无 GET 态）→ 批D 前定稿；多 genre 塌缩；LCS 条目互检；分两遍 signals；零命中负缓存；候选 SQL 加 value IN；match-runs N+1
- 仲裁句双写＝否（收尾行是冻结常量，涟漪大；扩块首第二句已覆盖分量轴）

### P1 选择器模板（M4，提示词工程师草案已备）
`kb_select.prompt` 走提示词包；LLM 只做「裁剪/重排」永不扩选，P0 先跑；候选=手法前40＋写法前20 的摘要形态；输出 `{"picked":[{n,reason}],"note"}`；模型只见编号不见 id；解析失败/超时/超配额 → 降级回 P0（selector=rule_fallback）；重试字节一致靠 run 缓存不靠模型确定性。缺失模板＝功能不存在（P0 照常），不记 error。

### ⑦ kb_organize 模板要点（M5 预研）
system 只提案关系永不改条目＋rel_type 六类白名单逐字照抄＋置信标尺锚定（<0.5 不输出）＋evidence 必填双端原文引用；user 每批 ≤100 条分批多 run＋已有关系对喂入防重提＋「这条不对」反馈对入禁推清单。

### 里程碑
M0 批F 架构加固（本变更内）→ M1 批D 前端 → M2 批E 评估 CI（含跨 run 影子泄漏=0 双断言）→ M3 归档（delta 减负后）→ M4 P1 LLM 选择器（PRO，独立变更）→ M5 ⑦ AI 整理（独立变更＋提示词包）。
