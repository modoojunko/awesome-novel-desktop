# 知识星图 · 组件选型与本体 3D 方案（C端 · 2026-10-30）

**一句话**：默认视图改为「全局图」——**Obsidian 式 2D 力导图**，用 `force-graph 1.52`（vasturiano，MIT，bundle 177KB，同 d3-force 家族）。浅色纸底、概念六色分组、悬停高亮相邻并压暗其余、搜索＋空枝开关；这是 **P0 唯一落地**的视图。蒲公英（3D 放射）/ 大脑（company-brain）/ 关系图（黑洞星云）降为**探索实验**（P1/Lab），入口在右上角切换。P0 选 **`3d-force-graph` 1.80.1（vasturiano，MIT，Three.js/WebGL）＋ `d3-force-3d`**：题材锚在旋臂上，局部用力导向松弛成团；黑洞是自写 shader（事件视界＋吸积盘＋光子环＋透镜 flare），金色光带从核心射向已建树题材；AI 整理关系用带粒子的通道。esbuild 把 three r186＋3d-force-graph 打成单文件 IIFE（`window.THREE`＋`window.ForceGraph3D`，无 CDN）；2D 平铺版用仓内 Cytoscape 3.30.2 兜底。

- 原型：`ai-novel-c端-写作知识库-原型.html` 场景⑥「本体星图」；截图 `kb-captures/6-star.png`（蒲公英）、`6b-brain.png`（大脑）、`6b-relations.png`（关系图）、`6b-star-focus.png`（聚焦仙侠/修真）、`6b-star-node.png`（概念 schema）、`6c-star-edge.png`（概念关系）、`6d-star-ai.png`（AI 整理）
- 自检：`kb-captures/verify-kb-proto.cjs`（80 节点同屏、黑洞核心、21 题材/22 项下拉、聚焦题材、聚焦后 6 个概念名、点条目/概念/关系、AI 整理、隐条目、概念筛选）
- 上游：整体方案 §2.3（概念树）、§2.4（题材是树的根）、§4.5（本体星图）、§5（`kb_concepts`）

## 1. 搜到的候选（anysearch + npm + GitHub 实查）

| 组件 | 版本 / 许可 | 渲染 | 3D 能力 | 本体表达力 | 结论 |
|---|---|---|---|---|---|
| **force-graph**（vasturiano，2D） | 1.52.0 / MIT / bundle 177KB | HTML5 Canvas，d3-force；Obsidian 图视图同路线 | 悬停邻域高亮、缩放平移、按组着色、标签分级 | **P0 全局图用它** |
| **3d-force-graph**（vasturiano） | 1.80.1 / MIT | Three.js / WebGL | 真 3D；`nodeThreeObject` 自定义节点；orbit/fly；`scene()` 加背景；`d3Force()` 可插自定义力 | 把「全部题材/题材/概念/子概念/条目」放成星系；概念关系用 `linkDirectionalParticles`；父子用 link | **P0 选它** |
| **a-funk/3dGraph** | 预发布 / MIT | Three.js + d3-force-3d | 真 3D；`galaxies` 布局 + 6DoF 飞行 | 层级/社区布局可参考；未发 npm、API 在变 | P1 参考（飞进本体） |
| **G6 5 + g6-extension-3d** | 5.1.1 / MIT | Canvas/SVG/WebGL | 官方 3D 扩展 | 布局多但包重 | 备选 |
| **Cosmograph** | 2.5.1 / **CC-BY-NC-4.0** | GPU | 大图星云感，3D 非主路径 | 偏分析/2D；**非商用许可不适合产品** | 不选 |
| **Sigma 4 + graphology** | 4.0.4 / MIT | WebGL | **2D** | 万级节点流畅 | 不选（无 3D） |
| **Longwind1984/galaxy-view** | 0.6.1 / MIT / 54★ | Obsidian 插件；3d-force-graph 1.80 + d3-force-3d + three 0.184 | 轨道旋转/右键平移/WASD+QE 飞行/F 聚焦/R 回远景/闲置巡航；NASA Eyes 风格 | **镜头直接采用它的 CameraDirector**（MIT，已 vendor） |
| **Observatory-Ridge** | 0.1.0 / MIT / 11★ | React Three Fiber 的 `GalaxyView` 组件 | drei OrbitControls；社区着色＋力导向 galaxy ball | 备选；React/R3F 包重，且没有黑洞核心 |
| **Cytoscape + fcose** | 3.30.2（仓内）/ 3.34.4 / MIT | Canvas/SVG | **2D** | 关系图成熟、已审计 | **2D 兜底** |
| 自绘 canvas（v9） | — | Canvas 2D | 假 3D | 概念层级要全自己写 | 已退役 |

### 1.1 神经元背景（用户点名的这几个）

| 项目 | 版本 / 许可 | 形态 | 结论 |
|---|---|---|---|
| **seinx-nn-canvas-animation** | 3.3.1 / MIT | 零依赖 Web Component，108KB；两层节点漂移、连线呼吸、光晕；CDN 一行标签 | **P0 选它**（离线内联，单文件原型可直接用） |
| **tsParticles** | 4.5.0 / MIT | 通用粒子引擎，`links` 按距离连线；React/Vue/Angular 封装 | 备选；能力最全但包大，偏通用粒子而非“大脑” |
| **canvas-nest.js** | 2.0.4 / MIT | 2KB 原生 Canvas 点线网络；鼠标排斥/牵引 | 备选；经典但无呼吸/光晕 |
| **Responsive Neuronal Background** | 21st.dev 组件 | React + Canvas，神经元背景，密度/鼠标活跃度可调 | 不选：React 专用，无法直接进单文件 HTML |
| **@lobehub/ui NeuralNetworkLoading** | 6.10.2 / MIT | React + SVG 加载图标 | 不选：是 loader，不是全屏背景 |

**为什么选 seinx**：它就是“呼吸感”的神经元网络（节点漂移、连线呼吸、光晕），零依赖、单文件 108KB、MIT，能直接内联进离线原型；`tsParticles` 更通用但需要自己配 `links`，`canvas-nest.js` 太朴素，21st.dev 组件绑 React，Lobe UI 只是加载图标。

### 1.2 黑洞/星系视觉有没有现成组件

实查结论：**没有「黑洞 + 可挂节点的图」这种成品**。黑洞类库要么是独立 hero 动画，要么是 2D CSS，挂不上 ontology 节点；图类库又没有黑洞。

| 组件 | 许可 | 形态 | 能不能直接挂节点 | 结论 |
|---|---|---|---|---|
| `@crazygl/hero-black-hole-lens` | Apache-2.0（49KB） | three.js/React hero：引力透镜＋吸积盘＋星尘 | 否，独立 hero，非图 | 视觉参考 |
| `MisterPrada/singularity` | **无 license**（317★） | TSL/WebGPU 黑洞 demo | 否 | 只看 raymarch/TSL 做法，不复制 |
| `vortex-worklet` | MIT（28KB） | CSS Paint Worklet 2D 吸积盘 | 否 | 不适用 |
| `three-g` | MIT（11MB） | three.js 星系粒子＋Barnes-Hut | 否，不是图 | 不选 |
| Cosmograph | CC-BY-NC-4.0 | GPU 图，2D 为主 | 是图，但非商用 | 不选 |

**落法**：图引擎用 `3d-force-graph`（已有 bundle），黑洞用 ~120 行自写 shader/geometry（事件视界 + 吸积盘 + 光子环 + 透镜 flare + 轨道环），不新增依赖、不引入许可风险。

### 1.3 大脑组件（现成）

| 项目 | 版本 / 许可 | 形态 | 结论 |
|---|---|---|---|
| **company-brain-3d** | 0.1.0 / MIT | React 19 + R3F 9 + drei 10；库 133KB；自带 **standalone iframe bundle（~1.1MB）**；JSON 树 → 脑区/神经元、飞入、卡片 | **P0 选它**（默认大脑视图；离线内联） |
| **@encapsa-dev/brain** | 0.1.3 / BSD-3-Clause | React 知识图谱 + 交互 3D 大脑 + 2D 图 + 无障碍 explorer；328KB | 备选；React-only，没有现成 iframe |
| `sevelee/Brain_Neural_Network_Visualization` | 无 license | 个人可视化 demo | 不选（无许可） |

**为什么选 company-brain-3d**：它就是“层级知识库 → 3D 大脑”的现成组件，接受 `{version,title,children}` 的 JSON 树（题材 → 概念 → 子概念 → 条目），自带透镜切换、脑区卡片、飞入、轨道旋转和 standalone iframe；MIT，可离线内联，不依赖我们自己的 3D 代码。

### 大脑数据映射

- 根：`写作知识库`。
- 第 1 层（透镜）：`仙侠/修真`、`都市`、`悬疑`、`架空古王朝`、`未建树题材`。
- 第 2 层（脑区）：每个已建树题材的 6/2/1/1 个概念；`未建树题材` 下是 17 个空枝叶子。
- 第 3 层/叶子：子概念 → 条目；全库 80 个节点全部进脑图。
- 7 条概念关系不在大脑视图里（大脑是层级，不是图）；切「关系图」看关系通道。

## 2. P0 落法（原型已实现）

### 2.0 全局图（Obsidian 式 2D · 默认 · P0 落地）

- **组件**：`force-graph 1.52`（MIT，esbuild IIFE 177KB，`window.ForceGraph2D`），Obsidian 图视图本身就是 d3-force＋canvas，同一路线。
- **融入系统**：v26 起逐字对齐 `base.css`（冷白 240 / 10px / Noto / teal / --shadow-card），旧暖纸 token 全部映射；概念六色分组；工具条与详情卡都是浅色组件。
- **交互（对齐 Obsidian）**：
  - 悬停节点 → 相邻保持亮色，其余压暗（`nodeColor/linkColor` 按 `G2D_STATE.neighbors` 判定）；
  - 点节点 → 右侧浅色卡片显示 类型/条目数/题材/概念；点空白关闭；
  - 搜索即时过滤（命中＋一跳邻居）；「显示空枝」开关 17 个空题材；
  - 滚轮缩放 / 拖拽平移；`enableNodeDrag(false)`——节点仍不可拖，位置与关系交给布局和 AI。
- **着色**：根＝墨黑；已建树题材＝teal（带条目数）；空枝＝灰；概念/子概念/条目＝六概念色（图例在左下）。
- **标签**：根/已建树题材常显；空枝与概念在放大后出现，避免糊成一片。
- **性能**：80 节点全量 2D canvas，冷却 400 tick 后冻结；低端机零压力，无需 WebGL/iframe。

### 2.0b 蒲公英视图（3D 实验，P1）

- 中心根；21 个题材按 `Fibonacci sphere` 均匀铺在球面（半径 285–353，`y=1-2(i+0.5)/21`，`theta=i×黄金角`），从任何角度看都是 360° 放射。
- 每个题材的概念/子概念/条目沿该题材的辐条方向继续向外长：概念 +58~70、子概念 +28~38、条目 +13~19，并带横向偏移，形成“蒲公英种子”而不是一根直线。
- **每个非根节点都向中心拉一条辐条**（79 条）：4 个已建树题材金色、其余灰蓝；再叠加父子层级与概念关系，形成“每颗种子都连回中心”的蒲公英；题材标签全显，概念标签只在聚焦时出现。
- `cooldownTicks(0)` 固定坐标，不走随机力导向；相机用 galaxy-view 的轨道/WASD；背景 seinx 在 dandelion 模式降到 0.28。
- **清晰度**：标签用 3x 超采样 canvas（`starTextSprite`）＋渲染器 `setPixelRatio(2)`；标签屏幕恒定大小；重叠的空枝标签自动隐藏（已建树优先），悬停仍可看名字。
- 切「大脑」/「关系图」不丢数据：大脑是层级投影，关系图是网络投影。


### 2.1 打包

- npm：`three@0.186.0` + `3d-force-graph@1.80.1`。
- esbuild 入口：
  ```js
  import * as THREE from 'three';
  import ForceGraph3D from '3d-force-graph';
  window.THREE = THREE;
  window.ForceGraph3D = ForceGraph3D;
  ```
  `--bundle --minify --format=iife` → 单文件 ~1.5MB，无 CDN、离线可用；随包登记 MIT 声明（three / 3d-force-graph / three-forcegraph / d3-force-3d），版本 pin。

### 2.2 节点＝点，只有根是黑洞

- **普通节点就是一个球＋一层柔和光晕**（`SphereGeometry`＋`Sprite` radial glow），不画星系贴图。
- **根节点不是点**：它的 `nodeThreeObject` 直接返回黑洞组——事件视界（黑球 r14.5）＋吸积盘（PlaneGeometry 190 的自写 shader）＋光子环（r16.8）＋透镜环（r18.4）＋金色 flare（600）＋5 圈轨道环（92/150/224/312/402）＋蓝色星云光晕。
- 五层节点（**全部展开，同一视图**）：

| 层级 | 大小 | 颜色 | 标签 |
|---|---|---|---|
| 全部题材（黑洞） | 事件视界 r14.5＋吸积盘 190 | 黑核＋金盘 | 常显「全部题材」 |
| 题材（21 类） | 已建树 6.8 / 空枝 5.0 | 已建树金白 `#ffd9a0`，空枝 `#8fa3bf` | **21 个题材名全显**：已建树 18px＋条目数，空枝 11px；悬停也有 tooltip |
| 概念（六类） | 5.2 | 概念六色 | 默认不标；**聚焦某个题材时**才标出它的概念（6 个） |
| 子概念（题材细分） | 3.2 | 继承概念色 | 不常显，悬停 tooltip |
| 条目 | 2.0 | 继承概念色 | 不常显，悬停 tooltip |

- **标签是屏幕恒定大小**：`SpriteMaterial({ sizeAttenuation:false })`＋按视口换算 scale，近处不巨大、远处不消失；这是星图可读性的关键。
- **21 个题材全在图上**：题材目录来自前后端同源的 `themeCatalog.ts` / `theme_catalog.py`（21 类，parity 测试守着），不是「有数据才画」。4 个已建树题材有金色光带；17 个空题材是暗星，仍可点、可聚焦。
- 子概念不是装饰：仙侠/修真 → 手法 → 打斗 → 先果后因，点开能看父概念和包含的条目。

### 2.3 通道＝三种边

| 边 | 样式 | 说明 |
|---|---|---|
| **根→已建树题材** | 金色光束（width 1.25 / opacity 0.62）＋1 个金色粒子 | 星系里的「主光带」；点开看题材统计 |
| **根→空题材** | 暗蓝细线（width 0.28 / opacity 0.14） | 不抢主光带，但保留「全部题材」的连通性 |
| **题材→概念→子概念→条目** | 星座细线（width 0.38 / opacity 0.28，弯曲 0.10），概念色/蓝白 | 形成局部星座；概念关系仍是带粒子的通道 |
| **概念关系 `implements / depends_on / applies_to / uses`** | 粗线、类型色、2–3 个方向粒子、箭头 | 点开看类型、强度、说明、两端 |
| **条目关系** | 很细、低透明、默认收起 | 条目之间的具体关系（先果后因→打斗描写等）；「层级」里可打开 |

- 3d-force-graph 1.80.1 无 `linkLineDash`（实测 `is not a function`），3D 版不用虚线；靠颜色/粗细/粒子区分。
- 概念关系的颜色：实现青、依赖橙、落笔金、调用紫、细化蓝、参照灰。

### 2.4 布局与镜头（不再写死层级）

- **单视图，没有总览/题材树切换**；`cooldownTicks(240)` 跑一次局部力导向后冻结。
- **题材在 3D 壳层，不铺盘**：
  - 21 个题材按黄金角排：`r = 190 + (i % 7) × 34 ± 30`，`angle = i × 2.39996 ± 0.28`，`y = 奇偶 ±(80–340)`；4 个已建树题材给固定高度：仙侠 +300、都市 −300、悬疑 +140、架空 −150，保证上下左右都张开。
  - 题材节点 `fx/fy/fz` 固定（保证构图稳定、可复现），概念/子概念/条目不固定。
- **局部星团按 3D 方向生长**：概念/子概念/条目不再只在 XZ 平面绕父节点，而是用 `starDir(seed)` 生成球面方向（`phi/theta`）→ `x/y/z` 三轴都展开；这是“看起来 3D”的关键，不是把相机抬高就完事。
- **局部力**：
  - link：根→题材 distance 120 / strength 0.01；题材→概念 72；概念→子概念 36；子概念→条目 17；后三级 strength 0.78。
  - charge：题材 −18（已锚定）、概念 −34、子概念 −11、条目 −3；根不参与。
  - 自定义 `orbit` 力只做很弱的 y 压扁（`vy += -y × 0.008 × alpha`），不做全局向心，保留 3D 纵深。
- **背景 = 神经元网络**：`<neural-canvas>`（seinx 3.3.1，MIT，108KB）画两套漂移节点＋距离连线＋呼吸光晕；配置成金/青两色（`net1Color #ffd9a0`、`net2Color #5eead4`），`nodeDensity 220`、`nodeSize 0.58`、`lineWidth 0.55`、`lineOpacity 0.16`、`glowIntensity 0.7`、`connDist 0.18`，CSS 层 `opacity .72`。
- **3D 前景**：`#star3d` 透明（`alpha:true`＋`rgba(0,0,0,0)`），压在神经 canvas 上；3D 星尘/远景星层已移除，避免双层噪声；黑洞吸积盘 shader 仍随时间流动，3 圈轨道环倾斜成“陀螺仪”；`FogExp2` 让远处变暗。
- **层级**：神经 canvas `z-index:0`，3D canvas `z-index:1`，UI `z-index:2`；神经背景 `pointer-events:none`，鼠标交给 3D 轨道/WASD。
- **镜头（直接用现成项目）**：采用 **`Longwind1984/galaxy-view`（MIT，54★）的 `CameraDirector`**，不再自己写相机：
  - 左键拖拽 = 轨道旋转（上下左右，无死区）；右键 / ⌘ / Shift + 拖 = 平移；滚轮 = 缩放；
  - `WASD` 前后左右 + `Q/E` 升降（Shift ×3）= FPS 式飞行；
  - `F` 聚焦当前选中，`R` 回远景；闲置 6s 自动巡航（带上下俯仰，拖拽/滚轮立即打断）；
  - 初始取景按节点云 `fitRadius` 和相机 FOV 算距离（`framingPosition`），不再用 `zoomToFit`，不同视口都不会裁边。
  - 只做了适配层：把 `3d-force-graph` 已有的 `OrbitControls` 注入 `CameraDirector`，去掉 Obsidian 插件依赖；相机代码来自 MIT 项目，已在文件头保留出处。
- **`enableNodeDrag(false)`，节点不可拖动**（相机可自由转，节点位置不被作家拉乱）。
- **聚焦**：顶部下拉 22 项（全部题材＋21 题材）；选一个题材，镜头飞到它的星团并打开属性，**不重建图、不切换模式**；「全部题材」飞回全景。
- 位置由「3D 壳层锚点＋局部力」共同决定；关系变化只影响连线，不重排。

### 2.5 交互与属性

- 拖拽旋转 / 滚轮缩放；悬停 tooltip 出节点名与层级。
- 点全部题材（黑洞）：题材目录（21 类）＋已建树清单＋本体规模（10 概念/20 子概念/28 条目）。
- 点题材：本题材条目数、概念/子概念数、「聚焦这个星团」；空题材显示「还没有建树；空枝也在图上」。
- 点概念：**定义、属性 schema（如文风的叙事身份/基调/视角/语言口径/示范段）、概念关系（文笔 实现 → 文风）、条目数**。
- 点子概念：父概念、包含条目。
- 点条目：原条目属性＋「看条目 →」开既有抽屉。
- 点通道：关系类型、强度、说明、两端、置信度、来源（AI/种子）、「这条关系不对」。
- 顶部统计写「21 题材 · 4 已建树 / 17 空枝 · 10 概念 · 20 子概念 · 28 条目」＋第二行「7 条概念关系 · 全部展开 · AI 整理」。
- 概念多选、层级开关（子概念/条目/条目关系）在全景里直接生效；切掉后只隐藏节点，不重排。
- **不手工连关系**：没有「拉一条边」的交互；作家只能查看，以及点「这条关系不对」反馈给下一次 AI 整理。

### 2.6 AI 定期整理（关系形成）

- 星图里的关系不是一次写死的，也不是作家手工连的：AI 定期扫描知识库，按本体约束补/改关系。
- 触发：拆书入库后一次；应用启动时距上次 >7 天一次；作家点「现在整理」一次（AI，不是手工连线）。一次只整理一个题材；没有条目的题材跳过（空枝不跑）。
- 输入：本题材的条目（标题/指令/证据）、概念树（概念/子概念）、现有关系。
- 输出：`{from,to,type,confidence,note,evidence}`，类型限定 6 类。
- 写入：`kb_relations(source='ai', confidence, status, run_id, evidence)`；`kb_organize_runs` 记每次流水。
- 阈值：≥0.75 直接 active；0.5–0.75 进 pending（不上星图）；<0.5 丢弃；旧关系被覆盖时 superseded。
- 星图只显示 `status=active`；顶部显示「AI 整理 · 每周一次 · 上次 10-28 02:14 · 新增 4 · 更新 2」，关系面板显示「AI 整理 · 置信 0.92 · 10-28」；「这条不对」写反馈，下次整理重新评估。
- 模板：提示词仓新增 `kb_organize`（PRO），随提示词包发布；客户端不写死提示词。

### 2.7 大脑视图（实验，P1/Lab）

- **默认视图**：打开星图先看 `<iframe>` 里的大脑；左上角标题「写作知识库 · 大脑视图」，右上角「大脑 / 关系图」切换。
- **加载**：把 `company-brain-3d` 的 standalone bundle（~1.1MB，React 19/R3F 9 全部内联）base64 内联进原型；首次切大脑时解码成 `srcdoc`。iframe 同源，便于宿主控制。
- **切关系图**：先 `removeAttribute('srcdoc')` 卸掉 iframe（释放 WebGL），再初始化 3D；否则两个 WebGL 上下文会把 3D 初始化拖到 ~15s（实测）。卸载后 ~1.8s。
- **交互**：大脑自带轨道旋转/飞入/透镜切换/卡片；卡片显示概念名＋条目数，点击飞入子概念；`autoRotate=0`，不抢视线。
- **样式**：dark 主题，脑区颜色继承概念的六色；`maxWidth:none`，响应式断点调到 1100px，窄屏时卡片沉到底部横滑。
- **限制**：大脑只表达层级；跨概念的 7 条关系、AI 整理关系、筛选/抽屉仍在「关系图」视图。

## 3. 数据契约

| 星图元素 | 数据源 | 关键字段 |
|---|---|---|
| 黑洞（全部题材） | 前端常量 `THEME_CATALOG` / 后端 `theme_catalog.py`（21 类） | 根节点、题材总数、已建树数、总条目数 |
| 题材（21 类） | **题材目录**（`themeCatalog.ts` / `theme_catalog.py`，不复制进 `kb_concepts`） | genre key、name、counts、是否有树 |
| 概念/子概念 | `kb_concepts` | parent_id、name、level（1/2）、definition、properties_json |
| 条目 | `kb_entries` | genre、concept（L1）、concept_id（叶子子概念）、title、instruction、evidence |
| 概念关系/条目关系 | `kb_relations` | from_id/to_id（`concept:*` 或 `entry:*`）、rel_type、strength、note、source（ai/seed）、confidence、status、run_id |
| 整理流水 | `kb_organize_runs` | genre、status、model、entries_scanned、added/updated/skipped、started_at/finished_at |
| 聚焦/筛选 | 题材目录 + 概念树 + 条目 | 题材下拉（22 项）、概念多选、层级开关；都是视图状态，不落库 |
| 属性面板 | 概念/子概念/条目 | 只读 |

## 4. 性能与兜底

| 规模 | 目标 | 手段 |
|---|---|---|
| 演示：21 题材 / 4 已建树 / 10 概念 / 20 子概念 / 28 条目（80 节点） | 60fps | 220 粒子神经背景＋3D 本体＋黑洞 shader |
| 21 题材 / 6 概念 / 80 子概念 / 1,000 条目（约 1.1k 节点） | 60fps | 条目小点、标签只给题材＋聚焦概念；关自动环绕 |
| >2,000 条目 | 30fps | 条目聚合/抽样；或 2D Cytoscape 平铺 |
| 无 WebGL / 低端机 | 可用 | 2D Cytoscape 平铺版（同一棵概念树） |

## 5. 待拍板

1. **题材锚定**：P0 把 21 个题材锚在 3D 壳层（构图稳定），概念/子概念/条目局部松弛；要不要让题材也完全自由力导向（更自然但每次构图会变）？
2. **标签密度**：现在 21 个题材名全显（已建树大、空枝小），聚焦时才标概念；如果嫌满，可以收回只标已建树。
3. **黑洞亮度**：现在金核＋吸积盘＋flare 偏亮，事件视界只留一个黑点；要不要更「黑洞」（更暗、更强透镜）还是更「类星体」（更亮、更像参考图）？
4. **3D 分布形状**：现在是 3D 壳层（题材上下错落）＋球状星尘；要不要改成螺旋塔/双锥/球壳？
5. **聚焦行为**：现在「飞过去＋打开属性＋标概念」；要不要同时把其他题材压暗（聚光灯）？
6. **子概念由谁维护**：P0 种子只读（现在），还是 AI 整理时也可以提议子概念、作家确认？
7. **AI 整理触发与阈值**：每周＋拆书后＋手动（现在）；置信 ≥0.75 上屏、0.5–0.75 待确认——阈值是否合适？
8. **关系类型**：实现/依赖/落笔/调用 4 类是否够？要不要加「冲突/替代」？
11. **全局图细节**：空枝标签何时出现（现在放大后）？概念标签阈值？要不要像 Obsidian 一样按「来源」分组着色（拆书/手录/AI）？
12. **3D 三视图去留**：蒲公英/大脑/关系图作为 Lab 保留，还是生产剥离成独立实验页？
9. **飞入模式**：P0 用 galaxy-view 的轨道/WASD，还是同时做 a-funk/3dGraph 式 6DoF「飞进本体」？
10. **神经元背景强度**：现在 `opacity .72`、220 粒子；要更“大脑”（更密/更亮）还是更克制（只做纹理）？要不要让背景粒子也吃鼠标（代价是 3D 轨道要减少一层交互）？
