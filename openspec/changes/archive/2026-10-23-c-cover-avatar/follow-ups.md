# c-cover-avatar · 后续阶段索引

本文件只做索引；阶段 2/3 已建立真实 OpenSpec change，不再是“说明文字代替验收”。

## 已完成

- **c-cover-avatar-backup**：`FORMAT_VERSION=7`、images manifest/BLOB、书/角色图像设置、`image_configs` 配置段、迁移 Key 转接与 `dead_image_keys` 报告；roundtrip 测试已绿。

## 待实现

- **c-cover-avatar-ui**（阶段 2）：图像配置页、上传型封面/头像工坊、PATCH 设置、链接刷新、书卡/角色卡展示、免费只能上传的 UI 门控。
- **c-image-generation**（阶段 3）：`image-generate` 权益、provider adapter、`image_jobs`/`image_batches`、生成/测试/试画/批量、逐候选 seed/hash、计费台账。

## 仍未拍板

- standard 档是否只能上传（当前按“只能上传”实现假设）。
- trial 是否与 PRO 同权（当前按同权假设）。
- 角色删除撤销是否连头像一起回（当前立即删头像，撤销回无头像卡）。
- 新书默认配置规则（当前：显式 is_default 优先，否则自动补一个）。
