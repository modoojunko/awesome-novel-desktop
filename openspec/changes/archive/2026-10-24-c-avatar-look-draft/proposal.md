## Why

封面工坊已有「AI 提取」（c-cover-scene-extract），头像工坊的「头像描述」却还是全手写——角色卡里明明有外貌档案（dossier.look）、势力身份、一句话人设，作者却要自己把它翻译成「只写外貌/服饰」的画图语言。头像描述的空置率远高于封面画面描述（有角色卡打底时封面描述可从主线蒸馏，头像的外貌翻译门槛更高），补一个对称的 AI 起草。

## What Changes

- 提示词仓新模板 `image_avatar_look`（family=image，TIER_PRO_ONLY）：system＝头像视觉策划＋只写外貌服饰/无字/头肩构图/不编造特征硬约束＋JSON 契约；user＝题材/性别年龄种族/外貌档案/势力身份/一句话人设五素材。素材不教模型发明角色卡没有的特征（未写发色不得凭空定色）。
- 后端新端点 `POST /api/novels/{id}/characters/{cid}/image-prompt/look-extract`（`image-generate` 门＋书模型就绪门＋角色归属校验）：蒸馏出 60–120 字外貌描述草稿（守卫 LOOK_MAX=140 与 prompt_builder avatar_prompt 截断对齐），只返回前端填「头像描述」输入框，不落库、不进生成链。
- 前端头像工坊「头像描述」行加「AI 起草」按钮（免费置灰；成功填 textarea＋toast 可改后保存），与封面「AI 提取」同构。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `cover-avatar`：ADDED「头像外貌 AI 起草」——端点契约（门控/素材白名单/草稿不落库/坏 JSON 502 可重试/模板 `image_avatar_look`）。

## Impact

- 代码：`client/backend`（cover_extract.py 增 extract_avatar_look/collect_avatar_material/parse_look＋_chat_json 复用；router 增端点）；`client/frontend`（ImageWorkshopModal 头像分支按钮＋draftAvatarLook；imageApi 增 extractAvatarLook）；测试两文件。
- 提示词仓同批独立 PR 互引（分支 c-avatar-look-draft）；生产生效随下个提示词包发布，dev/demo 栈 PROMPT_PACK_DEV_DIR 立即可用。
- 门控与封面提取同档：`image-generate`（PRO/试用以上）＋书模型就绪。
