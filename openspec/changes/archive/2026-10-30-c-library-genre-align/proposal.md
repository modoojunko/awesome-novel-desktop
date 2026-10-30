# c-library-genre-align — 库卡题材与开书题材目录一致

## Why

开书的题材是**封闭目录**（`genres/theme_catalog.py` 的 21 个大类，中文名即存储值；题材面板第 01 格按目录校验，未知 400），而角色库的题材格是自由文本（编辑器手输、拆书产物原样落入），会出现「库里『武侠』、开书目录里没有这个大类」的错位：库内筛选分栏与开书题材无法对齐，收录进来的书内角色题材也可能漂移。

## What Changes

- **库卡题材取值域＝开书题材目录大类**：`clean_payload` 用 `genres.theme_catalog.normalize_theme()` 归一并对齐——目录内大类直过；历史自由文本（如「古装玄幻」）包含匹配归一；不在目录内 400（可读文案指向题材目录）；空＝「未分题材」。
- **收录继承同口径**：书内收录时读 `story.yaml` 的 `genre`（开书第 01 格落的值）并过同一归一函数，目录外旧数据归零为未分题材。
- **拆书收录同口径**：产物 genre 文本（模型自由词）过同一归一函数，命中目录大类才落库。
- **前端编辑器**：题材自由输入框改为目录选择器（未分题材＋THEMES 大类，复用 `lib/themeCatalog.ts` 与开书面板同源）。
- 明确不做：库内自建题材大类（开书目录封闭，库不开口子）；子类（sub_genre）维度（库卡 v1 只存大类；后续需要再加）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `character-library`: 「角色卡的字段契约」里的题材格补「取值域＝开书题材目录大类（中文名即存储值；未知 400；空＝未分题材）」，收录/拆书导入的题材按同一目录归一。

## Design Impact

- **受影响端**：C端（S端零改动）。
- **受影响屏/弹层**：角色库编辑/新建弹窗（题材格由输入框改为目录选择器）；库页题材分栏自动收缩到目录大类。
- **对象状态**：无新增状态；选择器空值＝未分题材。
- **原型先行**：库页无 parity 基线（既有豁免）；drafts 原型不追补，ADJUSTMENTS 追加登记。
- **设计工件产出**：实现侧自查。

## Impact

- `client/backend/genres/theme_catalog.py`：新增 `THEME_NAMES` 与 `normalize_theme()`（目录归一单源；前端镜像不变，目录本体既有 parity）。
- `client/backend/library/service.py`：`clean_payload` 题材校验/归一；`_story_genre` 与 `_deconstruct_genre` 同归一口径。
- `client/frontend/src/components/library/CardEditorModal.tsx`：题材 `<select>`（未分题材＋THEMES）。
- 测试：后端归一/400/收录继承/拆书归一；前端选择器选项与保存值；覆盖率契约 100%。
- 数据影响：无迁移（角色库为新功能，无生产存量）；历史自由文本在读取路径统一归一。
