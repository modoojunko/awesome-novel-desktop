## 1. 原型先行与口径对齐

- [x] 1.1 以 `docs/design-c/drafts/ai-novel-c端-图谱关系网选型-原型.html` 为唯一视觉基准，逐项列出实现要对齐的默认值（全部有关系的节点、节点大小＝关系条数、枢纽同心圆初值＋fcose、枢纽标签 12、四向标签避让、minZoom 容纳 241 节点全显）；在 change 目录记录「原型→实现」对照清单，确认无遗漏项（对照 proposal 的 Design Impact：该产物不进 `prototypes/*.html` 与 design:check 矩阵，故不新增 ADJUSTMENTS 条目，需在实现 PR 说明此判定依据）
- [x] 1.2 实现完成后用 Playwright 对导出的 图谱.html 截图（关系网默认态／聚焦态／全显态／工作台 14 节点对照），逐项比对原型，偏差处更新对照清单或修正实现

## 2. Vendor 依赖、注入与打包

- [x] 2.1 新增 `client/backend/deconstruct/assets/vendor/`：cytoscape 3.30.2（dist/cytoscape.min.js）、cytoscape-fcose 2.2.0、layout-base 2.0.1、cose-base 2.2.0 官方发行文件＋各自 LICENSE；附 `vendor/README.md` 记录版本、来源 URL、sha256；在 图谱.html 内加入四库版权与 MIT 文本（注释/页脚），与应用包 `THIRD-PARTY-NOTICES.txt` 同源；验证四文件 hash 与 README 一致、许可文本齐全且单文件内可读
- [x] 2.2 `render.py` 增加四个 vendor 占位符注入（沿用现有「唯一占位符」校验与 JSON/书名先后的顺序纪律）；注入前断言 vendor 文本不含任何模板 token，并对 `</script` 做转义；验证渲染出的 HTML 含四个库特征串、不出现脚本提前闭合
- [x] 2.3 `client/packaging/build/bundle_manifest.py` 的 `DATAS` **新增** `("client/backend/deconstruct/assets", "deconstruct/assets")`（当前 v0.38 安装包缺该目录，图谱 HTML 导出会 400，本次一并修复）；更新 `THIRD-PARTY-NOTICES.txt` 四段 MIT 声明；验证打包清单包含模板＋四个 vendor＋许可，且这是一条新增条目而非「随包自动收录」

## 3. 关系网渲染实现

- [x] 3.1 `graph_viewer.html` 用 Cytoscape 初始化替换 `drawNet()`：可见节点＝至少一条边的节点，无关系实体不上图并在统计区报数；节点大小＝关系条数（20–46px 平方根映射）；其余三视图、侧栏选择入口、`selectWho` 等交互保持不变；验证默认态显示 42/241 节点、55/55 边（真机 258 章产物）
- [x] 3.2 布局：先按关系数跑 `concentric` 生成初始坐标，再以 `randomize:false` 跑 fcose（高关系节点更小斥力、枢纽间更短理想边长、gravity 0.32），`minZoom` 降到约 0.03 并显式 `fit`（产品态不提供「全部实体」开关——孤立实体不进关系网，241 实体全显仅原型对照态）；验证关系条数最高的若干节点到几何中心平均距离小于低关系节点，且同一图连续打开两次的枢纽中心距排序一致（不要求坐标逐像素相同）——已入 Playwright 冒烟（hubOrderRun1/2）
- [x] 3.3 标签：可见节点 >20 默认只标关系数 Top 12，其余悬停/聚焦显示，提供「全显」；≤20 默认全标；实现四向锚点贪心避让；验证 42 节点默认 12 个常驻标签、悬停出名字、全显可切换；14 节点默认全标
- [x] 3.4 降级：`cytoscape.use(fcose)` 包 try/catch；Cytoscape 初始化异常时关系网区域回落文本关系清单（双方＋类型＋方向），fcose 缺失时退回 `concentric`；验证人为破坏库加载后页面不空白、其余视图与统计可用
- [x] 3.5 保留筛选与既有语义：ego 聚焦（点人只高亮关系圈）、TopN 可选过滤、边色/节点色/图例文案与原查看器一致；实现从查看器 `:root` 的 oklch 变量取色（运行时 `getComputedStyle`），**不得抄原型的裸 hex**，新增色值先登记为查看器令牌；验证点人聚焦不联动地点树、TopN 过滤生效、无新增裸 hex

## 4. 回归与验收

- [x] 4.1 `client/backend/tests/test_deconstruct_render.py` 增断言：HTML 含 vendor 特征串与四库许可文本；「无外链」只检查 script/link/img 的 `src`/`href` 属性（先剥 JSON 岛，避免书内 quote 的 URL 误判），并加一条「quote 含 `http(s)://` 仍通过」的夹具；四 vendor 文件 sha256 与 vendor/README 一致、`THIRD-PARTY-NOTICES.txt` 含四段声明；`图谱.svg` 输出与改动前逐字节一致（黄金样本或同输入两次渲染对拍）；跑 `pytest tests/test_deconstruct_render.py tests/test_deconstruct_graph.py tests/test_deconstruct_pipeline.py tests/test_deconstruct_api.py -q` 并记录实际通过数
- [x] 4.2 查看器交互冒烟（Playwright/Node，固定小图夹具）：打开生成的 HTML，断言默认可见节点数/边数、常驻标签数、悬停出名字、点节点后关系圈高亮、破坏库加载后文本关系清单出现；把脚本与夹具入库，记录实际通过输出
- [x] 4.3 跑 `ruff check deconstruct/graph.py deconstruct/render.py tests/test_deconstruct_render.py`，记录实际结论
- [x] 4.4 真机验收：导出 258 章任务 → 断网双击 图谱.html → 四视图可用、关系网默认 42 节点/枢纽居中/标签按需、SVG 与旧版一致；「全部实体」开关不进产品（孤立实体不进关系网），42 节点全显态即默认态；记录导出文件体积与截图
- [x] 4.5 打包验收：本地 `build_mac.sh`（venv python3.12）构建成功，`.app/Contents/Resources/deconstruct/assets/` 内含 `graph_viewer.html`＋四个 vendor js＋LICENSE＋README，包内并有 `THIRD-PARTY-NOTICES.txt`（v0.38 包缺整个目录，本次 DATAS 新增条目生效）。运行期解析与 dev 栈同一路径逻辑（`__file__/assets`），dev 栈导出已实证；安装包内真机导出回归挂发版验收
- [x] 4.6 工作台角色关系图不改渲染器（spec 绑定确定性 SVG 圆布图；14 节点已可读）；用现有 `npm run design:lint` 与 `npx tsc --noEmit` 证明本次未触碰前端与共享段，记录实际输出；不跑 design:check 的判定引用 proposal 的 Design Impact

## 5. 归档

- [x] 5.1 实现 PR 合入前执行 `openspec sync` 把 delta 合入 `openspec/specs/deconstruct-book/spec.md`，把 change 移入 `openspec/changes/archive/`，跑 `openspec validate --specs` 与 `openspec validate c-graph-net-cytoscape` 记录实际结果；归档与实现同一 PR（既有流程约定）
