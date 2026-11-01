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
