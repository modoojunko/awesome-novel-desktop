## 1. 世界块渲染：预算参数修活

- [x] 1.1 `settings/world_model.py`：`render_world_block` 增加 `char_budget: int | None = WORLD_BLOCK_BUDGET` 参数（`None`＝不截）；`world_summary_text` 透传预算；保持既有默认行为不变（未传参的调用方零感知）
- [x] 1.2 从略注按类别：条目装箱跳过时按 势力／历史与旧账／世界细节 分别计数（「另有 N 个势力从略」），替换单一混称
- [x] 1.3 单测：预算传 `None` 时三段骨架＋全部条目齐全；传小预算时整条跳过＋分类从略注逐字断言

## 2. 拆卷素材（volumes/ai_plan.py）

- [x] 2.1 `_book_material`：`world_brief` 改传 `None`（全量）；`cast_brief` 改全名单一行卡（角色表全量、主角置顶、删除 chosen/in_view 聚光机制）；删除 `_chapter_material` 为聚光构造的 spotlight 拼接（死代码）
- [x] 2.2 新增已拆卷清单块：每卷一行（卷号＋标题＋主旨＋坎类型·一句话＋卷末落点）；options＝全部既有卷、expand＝排除目标卷自身、check 不含
- [x] 2.3 新增无卡出场名单派生块（全书已拆章，`ghost_of IS NULL`，名字＋章号列表，与 `_aggregate_cast` 同口径）；`known_entities` 并入这些名字
- [x] 2.4 主线全景改全量不截（退役 ≤2000）；`_blocks` 按规格顺序插块（世界块→人物全名单→已拆卷清单→无卡名单→其余照旧）——复核确认读取侧本无截断（2000 为作者写入上限）
- [x] 2.5 pytest：fixture 断言更新——势力三家全进块、全名单行数＝角色表行数、已拆卷清单行数与内容、无卡名字进 known 集合且申报不进 warnings；「世界摘要 ≤1200」类旧断言清理
- [x] 2.6 check 端点补世界块：`volume_check.prompt` 增世界块占位并注入 `world_brief` 全量（现状 check 只注 `world_rules`，不含世界块）＋fixture 断言

## 3. 拆章素材（chapters/ai_plan.py）

- [x] 3.1 `_chapter_material`/`_blocks_chapter`：追加 ⑩ 世界观块（全量）；⑥ 改核心人物全名单＋本卷无卡出场名单子块（本卷章纲派生）；`known_entities` 并入。模板 `chapter_split.prompt` 不改——新块经 `<<material_blocks>>` 占位符吸纳，对拍三件套不受影响
- [x] 3.2 pytest：素材顺序断言（⓪→⑩）、势力全量、全名单不截 6 张、无卡名字申报豁免

## 4. 门禁与收尾

- [x] 4.1 `volume_rules` 逐字对拍测试复核（rules 文本不动，锚点切分不受影响）；`test_volume_plan_ai` / `test_chapter_plan_*` 全绿
- [x] 4.2 ruff 零新增 ✅；真书冒烟：**素材侧 PASS**（活库快照＋真实装配路径实测：三家势力注记全部进包、零从略、素材 3148 字）；**模型在环实调已补做**（2026-09-27 隔离栈实跑拆卷出卡，见 `model-check.md`）：三家势力**零假阳性**（旧口径下必响）、模型**零自造**（三条 warning 涉及词全部可溯源本书文本）。
      **残留两条已登记**：①「豢养派旧贵族」＝主线散文 ↔ 势力表两套词汇（决策记录 §5 已列「提示词治不了、数据侧另立项」）；②「主战派」＝世界设定注记内子派系词被窄口径判"设定里没有"（比对集合只收势力名；新发现，候选后续）。
- [x] 4.3 spec 措辞复核：两份 delta 与实现逐条对得上（块序号、从略注措辞、已知侧定义）
- [x] 4.4 `settings/ai_router.py` 五处设定体检回归确认（死参数修活后世界块从实际 600 变真实 1200）：全量 pytest 含 settings 体检套件绿、无超时
