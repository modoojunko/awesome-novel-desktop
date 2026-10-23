## Context

- 图谱查看器是导出的独立单文件 `client/backend/deconstruct/assets/graph_viewer.html`（约 669 行手写
  HTML/CSS/JS），由 `deconstruct/render.py` 注入 JSON 岛与书名生成；契约要求单文件、离线、禁 CDN。
  关系网视图 `drawNet()` 直接消费装配层算好的 `layout.net`（确定性圆周坐标），没有布局/缩放/标签避让。
- `layout.net` 同时供 `图谱.svg` 的确定性渲染；`图谱.json` 的 graph/6 契约不包含渲染实现。
- 工作台「角色关系」页签 `RelationsGraphPane.tsx` 是另一套 756 行手写 SVG；其 spec 明确绑定
  「确定性定距圆布图（SVG）」，且当前 14 角色量级可读。本次不换它的渲染器。
- 真机数据：258 章产物 241 个实体、55 条边，其中只有 42 个节点有边；默认全部实体＋全部标签时
  成为不可读圆环。原型（drafts）已验证换库与默认口径的观感，用户已拍板「默认风格＋关系多的更近」。

## Goals / Non-Goals

**Goals:**

- 关系网用成熟图库承担布局/缩放/拖拽/点选/标签避让，删掉手写圆环与全量标签的默认口径。
- 默认口径：全部有关系的节点上屏、节点大小＝关系条数、枢纽居中/互相靠近、标签按需。
- 保持图谱.html 单文件离线；库文件固定版本内联，许可可审计；图谱.json/svg 字节不变。
- 渲染器失败有文本兜底，不出现空白画布。

**Non-Goals:**

- 不换工作台角色关系的 SVG 渲染器（spec 绑定确定性圆布图，14 节点已可读）。
- 不改图谱.json（graph/6）契约字段、装配逻辑、导出清单结构、API/DB。
- 不做图谱三件套的应用内预览（本次只改导出的 图谱.html）。
- 不引入前端打包链或 npm 依赖到 backend 资产；vendor 文件直接入库。

## Decisions

### 1. 选 Cytoscape.js + cytoscape-fcose（不用 vis-network / ECharts / Sigma / D3）

- Cytoscape 是图论原生库：布局（fcose/concentric）、缩放拖拽、选中、事件、标签与节点样式都由库提供；
  fcose 支持按元素函数配置斥力与理想边长，正好表达「枢纽更近」。
- vis-network 接入更简单，但物理态抖动、样式定制弱；ECharts graph 体积更大且非图论专用；
  Sigma+graphology 的 WebGL 优势要到千级节点才体现，集成成本更高；D3 仍需自己写图渲染，不满足
  「不要自己写」。
- 依赖：cytoscape 3.30.2、cytoscape-fcose 2.2.0、layout-base 2.0.1、cose-base 2.2.0，全部 MIT。

### 2. Vendor 内联，不引 CDN；固定版本＋hash＋许可

- 新目录 `client/backend/deconstruct/assets/vendor/` 存四个官方发行文件与 LICENSE；`render.py`
  在 `graph_viewer.html` 模板里用占位符注入（与现有 JSON/书名注入同一套「唯一占位符」校验）。
  注入前先断言 vendor 文本不含任何模板 token，并对 `</script` 做转义，防止升级引入 HTML 提前闭合。
- 使用官方 dist 原文（cytoscape 用 `cytoscape.min.js`，其余为 UMD 原文），不做二次压缩，便于审计；
  体积约 +700KB（真机 373KB → 约 1.07MB），对离线导出可接受。
- **许可**：`cytoscape.min.js` 自带 MIT 头，fcose/layout-base/cose-base 的发行文件没有——除
  `THIRD-PARTY-NOTICES.txt` 的四段声明外，导出的 图谱.html 内也要放版权与 MIT 文本（注释/页脚），
  因为单文件可能被单独拷走；vendor 目录保留各自 LICENSE，三者同源更新。
- **打包**：`bundle_manifest.DATAS` **新增** `("client/backend/deconstruct/assets", "deconstruct/assets")`。
  当前 v0.38 安装包没有这个目录（已核实 `.app` 内无 `graph_viewer.html`），既有导出会因模板缺失报 400；
  本次必须一并补上，并在打包冒烟里断言模板＋四个 vendor 都在安装包内。
- 版本与 sha256 记录在 vendor/README，并由后端测试校验文件 hash 与声明一致。

### 3. 只替换 `drawNet()`，其余三视图与 SVG 不动

- 章链/地点树/场景图是业务定制（进度轴/归属树/框内图钉），图库没有直接等价物；保留手写实现。
- `layout.net` 继续供 `render_svg` 使用（字节确定性不变）；HTML 侧忽略 `layout.net`，由客户端布局。
- 选中/侧栏交互沿用现有 `selectWho`/`selectPlace` 等入口，Cytoscape 事件转发到同一套选择逻辑。

### 4. 默认范围、节点大小与布局

- 可见节点＝至少一条边的节点（`edges` 双端点并集）；无关系实体不上图，统计区报「有关系的节点 N／
  其余为无关系实体」。
- 节点大小＝关系条数（不是共场权重 `w`），`20 + 26·sqrt(deg/maxDeg)`，约 20–46px；关系条数映射
  保留为可调常量。
- 布局：先按关系数跑 Cytoscape `concentric` 得到初始坐标（关系多者内圈），再用 fcose
  `randomize:false` 松弛；`nodeRepulsion` 随关系数递减（下限约 5200）、`idealEdgeLength` 随两端
  关系数递减（下限约 70），`gravity` 0.32。显式 `cy.fit(visible)`，并把 `minZoom` 降到足以容纳
  241 节点全显（原型实测需约 0.03），防止大图圆环跑出视区。
- **确定性边界**：fcose/cose-base 内部仍有 `Math.random()`（谱布局初始化/采样），`randomize:false`
  只保证不使用随机初值。验收只要求「同一输入重开的层次关系稳定」（枢纽中心距排序、低关系在外围），
  不要求坐标逐次一致；若后续要逐次一致，需固定 PRNG 或预置坐标，不在本次范围。
- 无关系节点若出现在小图（工作台量级），排到底部横带、虚线圆；本次只在大图默认隐藏。

### 5. 标签策略与避让

- 可见节点 > 20：默认只常驻标注关系数 Top 12；其余标签在 hover/聚焦时显示；提供「全显」开关。
  ≤20：默认全标。
- 标签四向锚点（右/左/下/上）贪心放置：按关系数从高到低，为每个常驻标签试四个位置，选第一个不与
  已放标签盒相交的锚点；近似文本框用字符宽度估算（CJK 11px、ASCII 6.2px、最大宽度 96px、两行高 28px）。
  这是启发式而非精确排版；枢纽优先占位，低关系节点填缝。
- 字号/配色沿用查看器现有视觉（11px、纸面底、角色色与极性边色不变）。实现 SHALL 从查看器
  `:root` 的 oklch 变量取色（Cytoscape 初始化时读 `getComputedStyle`），**不得直接抄原型的裸 hex**；
  确有新增色值先登记为查看器令牌，不引入 design-system 共享段。

### 6. 降级

- 关系网初始化包在 try/catch：图库缺失/初始化异常时，在关系网区域渲染文本关系清单
  （双方＋类型＋方向），其他三视图与统计照常；不吞错误，console 保留一条 warn 便于反馈。
- fcose 插件缺失但 Cytoscape 可用时，退回 `concentric` 布局而不是整体失败。

### 7. 工作台角色关系：本次不动渲染器

- spec 明确「确定性定距圆布图（SVG）」，换库属于契约变更；且 14 角色/17 边的小图当前可读。
- 本次只保持配色/图例语义与拆书关系网一致（现有实现已是主角绿/反派红/配角白、敌对红/友好绿/中性灰），
  不新增共享组件，避免触碰 design-system。若后续要统一交互，另立 change 并先改 workbench spec。

## Risks / Trade-offs

- **[HTML 体积 +~700KB]** → 离线单文件优先；图谱数据本身已 500KB 量级，增量可接受；不做二次压缩以保
  可审计性。
- **[fcose 在大图（241 节点全显）耗时]** → 默认只显示 42 个有关系节点；「全部节点」是对照开关，241 节点
  量级 fcose 仍可接受（原型实测 <1s）；必要时对该模式退回 `concentric`。
- **[标签避让是启发式，极端密集仍可能叠字]** → 默认只标 12 个枢纽＋悬停补名；「全显」明确是用户主动选择；
  后续可换精确标签布局库，不改数据契约。
- **[供应链]** → 固定版本＋sha256＋MIT 许可文本＋无 CDN；升级 vendor 必须同批更新 hash 与声明。
- **[fcose 内部随机]** → `randomize:false` 只关初值随机；验收只比「枢纽中心距排序/低关系在外围」的
  层次，不复用坐标；同一图连续两次打开做回归。
- **[安装包缺模板]** → `DATAS` 新增 `deconstruct/assets` 目录；打包冒烟断言模板＋四库存在。这是既有
  v0.38 包的真实缺口（安装包内无 `graph_viewer.html`），本次一并修复。
- **[241 节点全显裁剪/耗时]** → `minZoom` 0.03＋显式 fit；全显模式加耗时与不裁切检查，超预算退回
  `concentric`。
- **[旧内核兼容]** → Cytoscape 3.x 面向 Chromium 108/WebView2 无已知阻塞；导出文件通常在用户浏览器打开，
  产品内暂不内嵌预览。

## Migration Plan

- 纯渲染层变更，无数据/API 迁移；旧的已导出 图谱.html 保持原样，新导出使用新查看器。
- 回滚：还原 `graph_viewer.html`/`render.py` 并删除 vendor 目录即可；图谱.json/svg 与任务数据不受影响。
- 发布验证：导出真机 258 章产物 → 断网双击 图谱.html → 四视图可用、关系网默认 42 节点、枢纽居中、
  标签可按需显示、SVG 与旧版字节一致。

## Open Questions

（无；默认标签数 12 与节点大小映射作为可调常量，调整不改变本次 spec 的行为边界。）
