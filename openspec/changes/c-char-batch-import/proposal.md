# c-char-batch-import — 角色批量导入：下载模版 → Excel 填好 → 上传一次建一批卡

## Why

作家反馈「角色设定希望能批量添加」：现在建卡只有「添加角色」按钮逐张建空卡再切卡编辑，立 10 个龙套要重复 10 次同一套动作；而作家梳理人物名单的自然产物就是一张表格（或让 AI 照列头填一份）。口径经五轮拍板收敛为**单路径模版导入**（粘贴 JSON、逐行宽松格式、YAML 均已砍），方案与交互原型已定稿并通过产品/前端/架构三路评审＋前后端实现评审（拆解与待明确项均有默认值）。

## What Changes

- **模版下载**：弹窗「下载模版」生成 xlsx，双 sheet——「角色」（固定中文列头：名字*、类型、一句话人设、别名(用·分隔)、性别、年龄、种族、势力·身份、外貌标签、语言特征、背景、剧情定位；含 3 行「示例-」样例行）＋「填写说明」（逐字段填法＋示例＋通用规则）。
- **文件导入→预览→建卡**：选择文件后前端解析（SheetJS；xlsx 为主、CSV 兜底＋BOM/GBK 回退），预览表格行内可改名字/类型/人设、可删行；重名（库内/批内）黄条跳过；示例行黄条不导入；每书一位主角标红拦截；解析失败红条不静默、确认按钮禁用。
- **落库契约扩展（后端）**：`POST /api/novels/{pid}/characters` 载荷新增可选 `aliases: string[]` 与 `dossier: object`（白名单严格取八格、逐格 strip+clamp 300，非法键/形态 400），与既有 `prefill` 并存（同格冲突 dossier 胜）、向后兼容；单事务原子建卡，每卡恰 1 个请求。服务端 clamp：name[:50]、aliases ≤20 条各[:50]。
- **建卡编排（前端）**：逐卡串行 create；`409 name_taken` 计跳过继续，其他错误停批（toast「已建 K/N——第 K+1 张失败」，撤销只撤已建 K 张）；建完 toast「已建 N · 跳过 M」＋「撤销本次全部」（循环既有 DELETE，自带单卡撤销）；新卡落列表末尾并自动选中第一张。
- **弹窗内置「字段怎么填？」折叠块**：与模版「填写说明」sheet 同一文案源（常量 `IMPORT_FIELD_GUIDE`）。
- 明确不做：JSON 粘贴入口（五轮拍板砍）；认知 30 格进导入；Word/PDF 模版；模版内下拉/数据校验；弹窗「本次默认角色类型」选择器（类型由模版「类型」列定义，不填默认配角）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `character-settings`: 新增「批量导入（模版文件）」要求——模版双 sheet 契约、列头中英文识别、示例行防呆、重名跳过幂等、主角约束、护栏（10MB/100 行/GBK 回退）、停批与撤销、「字段怎么填」同屏同源；「角色卡与字段契约」新建角色场景扩展 aliases/dossier 一次性落卡与 clamp。

## Design Impact

- **受影响端**：C端（S端零改动）。
- **受影响屏/弹层**：设定 · 角色面板（原型 `docs/design-c/prototypes/character-settings.html`）＋「批量添加角色」弹层（新增）。
- **对象状态**：复用既有语义——解析错误/行级校验用 warn/err 语气（pill-warn/pill-err 同族）、建卡中按钮 busy 态、toast 回执（含撤销出口，补救句带可点击动作，合 §13 口径）；不新增提示语气、不触碰共享段（不改 base.css 令牌与 pill/notice/sk/panel/f-err 家族）。
- **原型先行**：需要——`character-settings.html` 补「批量添加」按钮＋弹层（下载/选择文件、预览表、行级状态、折叠说明块、建卡中/结果回执）形态，偏差登记 `ADJUSTMENTS.md`；交互基准＝`docs/design-c/drafts/ai-novel-c端-角色批量添加与拖拽排序-原型.html`（已验证）。
- **设计工件产出**：实现侧自查（design:lint / design:check / tsc / e2e 门禁全绿）。

## Impact

- `client/backend/settings/character_service.py`：`create_character` 扩参 aliases/dossier（新增纯函数校验器，照 `_prefill_dossier` 纪律；dossier 胜 prefill 合并）；clamp（name[:50]、aliases 20×50、八格[:300]）。
- `client/backend/settings/characters_router.py`：载荷透传两键。
- `client/frontend/src/lib/characterImport.ts`（新）：列头归一化映射（中/英/变体）、行解析（`sheet_to_json raw:false` 防自动转格式）、normItem/rowStatus、模版构建输入、`IMPORT_FIELD_GUIDE` 常量（弹窗折叠块与说明 sheet 同源）。
- `client/frontend/src/components/novel/settings/BatchAddModal.tsx`（新）＋`CharacterManager.tsx` 接线（「批量添加」按钮文案避开 e2e「添加角色」substring）；`charactersApi.ts` create 扩参透传。
- 依赖：xlsx（SheetJS）经官方 CDN tarball 0.20.x 引入（registry 0.18.5 有 CVE），dynamic import 独立 chunk；登记 `coverage-contract.ts`（纯函数 100%，指针/文件薄壳 v8 ignore 有据）。
- 测试：后端 create 扩参用例（全字段/非法键 400/非对象/非字符串/clamp/prefill 合并 dossier 胜/老载荷回归）；前端 characterImport 矩阵（列头/行级/BOM+GBK/护栏/模版生成→回读同源契约）、BatchAddModal 用例、e2e（下载模版回读、导入建卡落库、重复导入幂等）。
- 原型：`docs/design-c/prototypes/character-settings.html`＋`ADJUSTMENTS.md` 登记。
