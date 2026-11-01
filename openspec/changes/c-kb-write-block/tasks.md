# c-kb-write-block · Tasks

## 批A 选择器核心（后端，可独立合入）

- [x] A1 `kb/match.py`：信号抽取（章纲角色/概要/剧情条目→scene/emotion/chapter_pos/卷位/实体）——只读章纲结构，不调用模型
- [x] A2 别名表：`kb/concepts.py` 扩 `_SCENE_ALIASES/_EMOTION_ALIASES`（每场面类 ≥5 同义词）＋归类函数；归类不出返回 None 不硬猜
- [x] A3 候选短名单：kb_entry_tags 两段式查询（≤200 稳定排序；零 payload_json 全表扫描）
- [x] A4 打分与配额：匹配度×有用率×新鲜度；手法 ≤6＋场景定性 ≤4；≤2K tokens 预算截断；零命中返回 None
- [x] A5 单测：信号归类（含「无场面线索章」）/短名单两段式/配额与预算/零命中/确定性（同输入两次同选集）

## 批B 注入与复用（后端，依赖批A）

- [x] B1 块组装器：块首三句声明＋条件标签条目格式；组装守卫（回声 <8 字跳过兜底）
- [x] B2 回声闸入库：`kb/gates.py` 新检查（与收尾行/分量行/续写行 ≥8 字公共串拒收）＋闸门单测
- [x] B3 生成路径注入：`write/router.py` 收尾行前插块＋kb_match_runs/items 落库＋brief_hash 复用（同章同素材零重选）
- [x] B4 续写补足路径：按章节复用当章最新 run 拼同块；停用库后无块（不注入旧 run）；零命中不出空块
- [x] B5 SSE 事件：`write_block` 事件（块文本＋run 清单引用）转发给前端
- [x] B6 单测：重试字节一致/续写带同块/停用后无块/零命中/未启用库零变化（A/B 对拍提示词逐字节一致）

## 批C 影子并轨＋反馈（后端，依赖批B）

- [x] C1 量化判据常量（句长/段落/词频词眼正则表）＋写法块跳过逻辑
- [x] C2 量化条目影子落库：**落点改章级**（write/write_block 选块后转 Chapter.style_shadow，声明「本章覆盖：知识库·…」经既有 shadow_override_lines 渲染）——快照期章不存在，design.md C2 注记已更新口径
- [x] C3 反馈端点：`POST /api/kb/entries/{id}/pref`（kb_prefs upsert 有用率）＋`GET /api/kb/match-runs` 清单
- [x] C4 冲突率断言：写法块条目 ∩ 影子条目 ＝ ∅（单测）
- [x] C5 单测：影子并轨落库/量化条目不出现在块内/pref 回写改变后续打分


## 批F 架构加固（四角色评审 P0 收口，先于批D）

- [x] F1 run 竞态：插入 catch IntegrityError → rollback → 重查赢家 run 复用（修会话中毒＋误报失败）
- [x] F2 字节一致快照：KbMatchItem 加 `text_snapshot` 列，run 创建时固化；重建走快照（条目编辑不再破坏一致）
- [x] F3 库域指纹：KbMatchRun 加 `domain_fingerprint` 列（启用库 id 集）；复用前必须匹配，换库即重选
- [x] F4 影子残留清理：新写影子前清同章全部「知识库·」行；停用/零命中路径同清；ghost 章过滤补齐；影子 commit 并入 run 单事务
- [x] F5 结构消毒：gates 新检查（换行/行首结构标记/「【本章写法指引】」字样拒收）＋block 组装守卫同口径
- [x] F6 量化影子渲染分源：value 只提数值短语＋condition 拆场面短语；render.py 影子行按 source 分支（「交手场面适用；本章覆盖：…」）
- [x] F7 条件标签只发命中维度（按 selector reason）＋块首 v2 文案
- [x] F8 列预留：run 加 `selector`/`brief_json`；extract_signals 上移 write/write_block.py；digest_candidates 公开化
- [x] F9 「日常」信号死值：文戏别名集删「日常」＋normalize 精确匹配优先＋E1 判例
- [x] F10 spec 同步：⑦ Req 已移 drafts/c-kb-organize/；仲裁句 v2 两份 spec 已同步；零命中「命中章」限定已补
- [x] F11 批F 回归：全量 pytest＋write 链＋新钉（竞态单 run/快照一致/换库重选/影子零残留/消毒拒收）

## 批D 前端（依赖批B3/B5＋批F）

- [ ] D1 提示词弹窗只读区：「本章写法块 · 自动注入不落库」（write_block 事件驱动；未启用库的书零渲染）
- [ ] D2 逐条「有用/没用」标记钮（调 pref 端点；无确认弹窗可改口）
- [ ] D3 入约：新组件入 coverage-contract＋组件测试；文案过 design-language 口径自查
- [ ] D4 e2e：启用库书生成→弹窗见只读块＋未启用书不见；标记→清单回显

## 批E 评估 CI（依赖批A/B）

- [ ] E1 别名归类单测进 CI（每场面类 ≥5 判例）
- [ ] E2 golden 集：按场面类分布 fixture（每类 ≥5 章＋无信号章 2）＋选集一致率 100% 断言；只钉 id 序列不钉 score/reason；regen 单命令＋不变式自验证；放 tests/golden/kb_match/（排批F 后，含「跨 run 影子泄漏=0」扩展断言）
- [ ] E3 回归口径进 tasks 验收清单；CI 门禁挂接（backend CI 必经）
