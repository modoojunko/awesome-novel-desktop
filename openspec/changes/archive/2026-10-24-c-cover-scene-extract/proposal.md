## Why

封面工坊的「封面种子/头像种子」是纯实现细节漏到了界面上：种子只影响同输入重绘的可复现性，而系统已有按书/角色 id 的确定性派生（`_derive_seed`，同书恒定、换图靠改画面描述/画风），用户手填没有任何使用场景，实测只会造成「不知道这是啥」的困惑。同时，封面提示词目前只吃「题材标签＋核心承诺＋世界舞台第一句」，书的主线（`story_arc.fullstory`）与一句话故事（`promise_note`）完全没有参与——封面画面与书的内容脱节，默认只能画泛泛的象征静物。

## What Changes

- **种子退役（封面＋头像对称清理）**：删除 `BookImageSettings.cover_seed` 与 `CharacterImageSettings.seed` 列及全部读写面（schemas/service/router/prompt_builder/备份 v7 manifest/前端输入框与 payload）；seed 一律按书/角色 id 确定性派生（`seed_source` 恒为 `derived`）。老客户端残留提交的 `cover_seed/seed` 字段被服务端静默忽略（Pydantic 默认 ignore），旧备份 v7 包里的 `cover_seed` 键导入时静默丢弃。
- **封面画面描述 AI 提取**：新增提示词仓模板 `image_cover_scene`（system=封面视觉策划＋无字/剪影/单焦点硬约束＋JSON 契约；user=选题/一句话故事/简介/主线/世界舞台素材），后端新端点 `POST /api/novels/{id}/image-prompt/cover-extract`（`image-generate` 权益门＋书模型就绪门），把书级白名单素材蒸馏成一段 80–140 字的画面场景草稿。草稿**只落前端「画面描述」输入框**（用户可改、点保存才生效），不入库、不进生成自动链；`prompt_builder` 组装逻辑零改动（草稿经既有「画面呈现{…}」句参与，名字脱敏兜底照旧）。
- 前端工坊：删两个种子输入框；「画面描述」标签行新增「AI 提取」按钮（免费置灰＋PRO 提示；成功后 toast「草稿已填入，可修改后保存」）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `cover-avatar`：
  - MODIFIED「图与书/角色单一归属与 prompt 白名单」——封面 prompt 白名单去掉 `seed`；补一句「种子一律按书/角色 id 确定性派生」。
  - MODIFIED「图像设置与种子读写」→ 改名「图像设置读写」，去掉 `cover_seed`/`seed` 字段与 PUT 保留特判；老客户端残留字段静默忽略。
  - MODIFIED「设置部分更新」——去掉 `cover_seed` 保留条款。
  - ADDED「封面画面 AI 提取」——新端点契约：门控（image-generate＋书模型就绪）、素材白名单（选题/一句话故事/简介/主线/世界舞台）、产出只作草稿不落库、坏 JSON 502 可重试、模板来自提示词仓 `image_cover_scene`。
- `backup-restore`：MODIFIED「图像资产与图像配置随包（v7）」——manifest 书级去 `cover_seed`、角色级去 `seed`；旧包多出这两键时导入静默忽略。

## Impact

- 代码：`client/backend`（models/image_asset、image_assets/{schemas,service,router,prompt_builder}＋新增 cover_extract.py、backup/{export,importer}）；`client/frontend`（ImageWorkshopModal.tsx、imageApi.ts、image-assets.css）；测试三文件更新＋新增提取端点测试＋迁移样本 `v039-image-seed-columns` 入册（legacy_samples 只增不减）。
- 提示词仓（sibling `awesome-novel-prompts`，同批独立 PR 互引）：新增 `prompts/image_cover_scene.prompt`＋`sync.py` CURATED（新 family `image`）＋`publish.py` TIER_PRO_ONLY；**生产生效需随下个提示词包发布**——包未发布前线上点「AI 提取」走既有 503 `prompts_missing` 四态卡兜底；demo/dev 栈走 `PROMPT_PACK_DEV_DIR` 立即可用。
- DB：每版新建库文件、无 DDL 迁移；删列后 schema fingerprint 变化由既有迁移/carry 链承接（交集搬行，源多列不拦路——迁移样本钉住）。
- 权益：提取与 AI 生成同门控 `image-generate`（PRO/试用以上），另挂书模型就绪门（要调文本模型）。
- 与在途 `c-image-generation`（尚余 S端/归档任务）spec 触点不重叠：它管生成任务/权益，本 change 管设置与提取；后合者 rebase。
