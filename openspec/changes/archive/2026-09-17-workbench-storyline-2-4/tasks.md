# Tasks

> 本变更为「已实现行为的 spec 回填」：实现已随 #383/#386/#388/#389/#390/#392 与同批 PR 合入 main，下列任务以「核验实现与契约一致」为主，验证方式为既有测试证据。

## 1. 二期：主线端点与排队门禁（#383）

- [x] 1.1 `GET /api/novels/{id}/frontier` 派生主线端点（首个未归档；全归档→待写占位）——验证：`tests/test_frontier.py` 绿
- [x] 1.2 prose PUT 与 AI 写章门禁（非 frontier 409；ghost 只读 409）——验证：相关端点测试 + e2e free-writing 门禁断言绿
- [x] 1.3 bar-here 主线口径切 frontier（会话优先→frontier→首章）——验证：`NovelWorkspace` 单测 + 工作台 e2e 绿

## 2. 三期：回退与旧稿支线（#386）

- [x] 2.1 `POST .../revert` 主线截断＋ghost 化＋派生数据按章序清除——验证：`tests/test_revert_ghost.py` 绿
- [x] 2.2 `GET /api/novels/{id}/ghosts` 支线章列表——验证：同上测试文件
- [x] 2.3 操作页签回退卡＋支线章只读横幅——验证：工作台 e2e 绿

## 3. 四期：关系图与文风影子（#388/#389/#390/#392）

- [x] 3.1 `GET .../characters/graph` 与「角色关系」页签（SVG 定距圆布图＋文本兜底）——验证：`tests/test_relations_graph.py` 与前端单测绿
- [x] 3.2 `chapters.style_shadow` 列＋baseline/PUT/suggest 三端点（清洗/门控/解析）——验证：`tests/test_style_shadow_api.py` 11 例绿
- [x] 3.3 写章提示词按行覆盖（quant_section shadow）＋ChapterContext 默认字段——验证：`tests/test_style_shadow_injection.py`＋writer 回归绿

## 4. 四期尾：剧情推演与提示词六来源（本变更同批 PR）

- [x] 4.1 `POST .../simulate`：AI 产物清洗＋确定性兜底（source=ai|fallback）——验证：`tests/test_plot_sim_api.py` 8 例绿
- [x] 4.2 `GET .../prompt-sources` 六来源投影——验证：`tests/test_prompt_sources_api.py` 2 例绿
- [x] 4.3 推演弹窗（按回合走/未定走法不推进/收进章纲写预期策略）与六来源展示（chips＋清单）——验证：`src/__tests__/plotSimAndPromptSources.test.tsx` 4 例绿；`e2e/plot-sim.spec.ts` 3 例绿

## 5. 归档与回归

- [x] 5.1 spec 增量校验：`openspec validate workbench-storyline-2-4 --strict` 通过
- [x] 5.2 全量回归：后端 pytest（plot-sim/prompt-sources/style-shadow/frontier/ghost 相关全绿）；前端 vitest 329 绿；C端 e2e 全量（137+3 例，见 PR 记录）
- [x] 5.3 共享栈重建后 5174/8000 新特性可见（simulate/prompt-sources 端点在线）
