# C端 · 书封与角色头像（图像模型）设计说明

> 2026-10-22 · 原型基线：main `d4bf73fa` 真机抓取 + 独立栈 Playwright 渲染
> 原型：[`ai-novel-c端-封面与角色头像-原型.html`](ai-novel-c端-封面与角色头像-原型.html)
> 源模板：[`ai-novel-c端-封面与角色头像-原型.src.html`](ai-novel-c端-封面与角色头像-原型.src.html)
> 抓取物：[`cover-art-captures/`](cover-art-captures/)
> 重建/自检：`python3 docs/design-c/drafts/build-cover-art-proto.py` → `python3 docs/design-c/drafts/check-cover-art-proto.py`

---

## 1. 一句话

给「书」一个首图（封面），给「人」一张脸（头像），两者共用一套**按书设置的画风**；图像模型在模型配置里单独一页签，与写作大模型分开配置、分开计费。生成只在用户点按钮时发生。

## 2. 为什么现在做

作者对一本书的设定，除了文字，还有「它长什么样」。当前：

- 书架书卡只有 40px 的「首字方块」，没有封面位；
- 角色设定列表是 22px 的首字圆点，详情是 52px 的「章印」方块，没有头像；
- 模型配置只有「写作大模型 / 朱雀检测」两页，没有图像模型的位置。

火山引擎 Seedream、阿里云百炼 Qwen-Image、智谱 CogView、OpenAI `gpt-image-1` 这类模型已经在作者手边，图像生成的调用成本与稳定性都到了可用线；产品不再只绑 MiniMax 一家。这个功能不是「给写作加一个玩具」，而是把**设定页已有的文字资产**（书名、题材、简介、角色外貌、身份、一句话人设）变成可看的形象资产。

## 3. 原型怎么看

顶部演示条按功能分三组：封面（书架/封面工坊）、角色（角色设定/头像工坊）、图像模型（列表/创建/编辑/测试）：

| 屏 | 真实入口 | 看什么 |
|---|---|---|
| ① 书架 | 「我的作品」书卡 | 封面成为书的第一眼；无封面时是字标占位，不空白 |
| ② 封面工坊 | 封面悬浮「换封面」/ 书卡菜单「封面…」 | 画风、描述、生成中、2 张候选、使用/上传 |
| ③ 角色设定 | 书内 设定 → 角色 | 头像落在列表圆点与详情章印；详情章印可点开 |
| ④ 头像工坊 | 详情章印 / 列表头「批量头像」 | 设定依据、画风跟随、固定种子、2 张候选；批量只补没头像的 |
| ⑤ 图像模型 | 模型配置 → 图像生成 | 独立页签；列表卡 + 添加/编辑弹窗 + 卡上测试连接（与写作大模型同一套做法） |

原型里的封面/头像是 `assets/*.svg` **示意画面**，不是图像模型真实输出；只用于评审版式、状态与交互。真实产品里生成的是无字画面，书名与印章由前端排版叠上去（见 §6.3）。

## 4. 设计结论

### 4.0 图与书/角色的关系（单一归属）

图不是全局素材库，每张图必须有明确归属：

| 图 | 归属 | 数据 | 读哪些书/角色信息 |
|---|---|---|---|
| 封面 | 书 | `image_assets.novel_id`，`character_id` 为空；每本书一条 current | 书名、`story.yaml.genre/sub_genre`、`NovelGenre.core_promise`、简介前 240 字、`world-setting.yaml` 的 stage；**不读正文/章纲** |
| 角色头像 | 角色 | `image_assets.novel_id` + `character_id`；每个角色一条 current | 角色卡 `dossier` 的性别/年龄/种族/外貌/势力 + `persona`；**不读 background/plot/正文** |
| 图像模型 | 配置 | `image_configs`，通过 `book_image_settings.image_config_id` 绑到书 | 只决定“用哪家/哪个模型”，不属于某张图 |

- 候选/当前/上一张的状态只作用于所属 owner：封面换图不影响角色头像，单角色换头像不影响书封面。
- 书级画风 `book_image_settings.style_key` 是封面和所有角色头像的共同前缀；角色级 `character_image_settings.avatar_prompt/seed` 只覆盖这个角色的画面主体/种子。
- UI 关系：封面只出现在书架书卡/书内详情；头像只出现在角色列表和角色卡详情。两者共用“本书图像模型”，但资产 id、current/previous、撤销 token 各自独立。

- **接口就地携带**：`GET /api/novels`、`GET /api/novels/{id}` 直接下发 `cover`（asset_id/url/thumb_url/width/height/version/source/style_key）；`GET /characters`、`GET /characters/{id}` 直接下发 `avatar`。前端不再先拿 asset_id 再查统一图片接口；只保留签名二进制读取 `GET /api/image-assets/{id}?variant=&exp=&sig=`。
- **删除即级联**：删书时删除该书全部 `image_assets` 与 BLOB；删角色/合并角色时删除该角色的 `avatar` 资产与 BLOB。角色删除目前有撤销窗口，但按本条口径**图片不随撤销恢复**（撤销回来的是无头像卡）；如果要保留“撤销连头像一起回来”，需要把资产快照并入 `CharacterOp`，属于后续增强。
- **不变**：图像模型配置通过 `book_image_settings.image_config_id` 绑书，不随单张图删除；换模型不影响已生成图片。

服务端 prompt builder（阶段 1 已提供只读预览，生成阶段复用）：

- `GET /api/novels/{id}/image-prompt` → 封面 prompt + `sources`；
- `GET /api/novels/{id}/characters/{cid}/image-prompt` → 头像 prompt + `sources`；
- 返回 `prompt_hash/style_key/seed`；生成时把最终 prompt 原文与 hash 快照写进 `image_assets`，保证“这张图是用哪版设定生成的”可追溯。

### 4.1 图像模型独立配置（已拍板 A）

模型配置页新增第三页签「图像生成」，**完全沿用写作大模型（api-config）那套既有做法**，不另立形态：

- **列表页**：图像模型卡（供应商图标、配置名称、Base URL、连接状态徽标、Key 掩码、模型/目标尺寸 chips）+「添加图像模型」磁贴；页头主按钮随页签改名（图像页＝「添加图像模型」）。示例卡为「主线 · 火山引擎」，默认供应商不再写死 MiniMax。
- **卡片三个动作**：**测试连接 / 编辑 / 删除**——与写作大模型卡完全一致。
  - 「测试连接」结果写在卡片页脚的结果行（`.cfg-foot .res`，绿＝连接正常 / 红＝失败原因），不跳页、不弹窗；
  - 「编辑」打开与添加同一个弹窗（预填）；
  - 「删除」走独立确认弹窗。
- **添加/编辑共用一个弹窗**（520px，字段顺序照抄写作大模型）：
  配置名称* → 供应商（方块网格；编辑态默认当前供应商 +「更换」）→ Base URL* → API Key → **能画这两种图**（只读：小说封面 768 × 1024 / 角色头像 512 × 512）→ 模型名称；
  底部：测试连接 / 取消 / **保存**；表单内单独一个「试画一张（会计费）」。
- **保存不自动测试**：保存只保存；「测试连接」是免费探活（只验证地址与 Key，不出图、不计费）；「试画一张」才真实画 1 张 512 × 512，按钮旁明写会计费。
- **编辑态换供应商**：默认显示当前供应商 +「更换」；点「更换」展开 6 家，选新供应商先弹确认，确认后清空 Key/模型/测试结果、取消在途生成，**不自动改配置名**；「取消更换」回到原供应商。
- **能力只读**：系统按供应商/模型判断能画什么，作者不能勾；OpenAI 兼容等不确定的接口在高级里手动声明。
- **删除确认弹窗**（460px）：标题「删除配置」，正文「确定删除配置「xx」？」+「删除影响」盘点 chips（模型 N 个 / 封面 768 × 1024 / 头像 512 × 512）+ 尾注「已生成的图片保留，此操作可撤销」；底部 取消 / 确认删除。删除是软删，8 秒内可撤销。
- Key 与写作大模型分开保存、互不顶替；写作大模型不会自动拿来画图。

**PRO 门槛（已拍板 N）**：AI 生成只对 PRO 及以上开放；免费用户只能上传自己的封面/头像。生成/测试/批量入口保留但显示「PRO 以上可用」+ 升级；降级后已生成的图片和配置保留，重新升级即可继续用。后端生成/测试接口必须真拦（`tier_required`），不能只靠前端置灰。

**每本书单独绑定（已拍板 O）**：`book_image_settings.image_config_id` + `image_model` 记录「这本书用哪家图像模型」；新书默认用当前默认配置；封面/头像工坊页脚显示「本书图像模型」，并提供入口切换。

**模型名称不是裸输入框**，沿用 `ApiConfigForm` 的组合框能力：

- 标题行右侧是**「获取模型」**按钮 + 拉取状态（`已拉到 N 个模型` / `该接口未返回模型清单`）；
- 未填齐 Base URL / Key 时按钮禁用（编辑态 Key 可留空，用已存 Key 拉）；
- 点击后展开模型清单，选中即回填；也可直接手填模型 id；
- 拉取失败给「重新拉取」出口，且不挡住手填；
- 编辑态清单来自已存模型，留空保存表示保留当前模型（与写作大模型「留空则保留当前模型」同口径）。

**与写作大模型的主要差异**有三处：① 弹窗里多一段「能画这两种图」，只读展示；② 编辑态允许「更换供应商」（写作大模型锁死），但必须二次确认、清 Key、不改配置名；③ AI 生成有 PRO 门槛。其余字段、措辞、按钮、状态、模型拉取、删除口径完全同源。实现时可直接复用 `ApiConfigForm` / `ApiConfigCard` / `DeleteConfirmDialog` 的骨架，只在图像分支上加能力段、更换逻辑与门槛。

**为什么用「用途＋尺寸」而不是比例**：接口层只认比例（3:4 / 1:1），但作者看到「支持比例 3:4」不知道这东西会出现在哪、有什么用。这里按产品实际要出的两张图表达：
- **小说封面 768 × 1024**（3:4）——书架书卡与书内详情共用；
- **角色头像 512 × 512**（1:1）——角色列表与角色卡详情共用。

同一个口径贯穿四处：弹窗能力段、列表卡 chips（`小说封面 768 × 1024` / `角色头像 512 × 512`）、删除影响盘点、封面/头像工坊的「尺寸」行。比例只是实现细节，界面不出现。

**为什么不复用写作配置**：火山方舟的图像接口是 `/api/v3/images/generations`，阿里云百炼是 `/api/v1/services/aigc/multimodal-generation/generation`，与各自写作 Base URL 不同；OpenAI 对话与图像也是两组模型 id。把图像模型塞进写作配置会在 Base URL 与模型清单上互相污染。独立页签也让「按张计费」与「按 token 计费」在账面上分开。

### 4.2 画风按书统一（已拍板 B）

一本书只有一套画风：封面、角色头像、以后可能的章节插图都共用。理由：

- 同一本书的角色头像如果各自一种画风，人物卡放在一起会像拼贴；
- 封面上是水墨，头像却是厚涂，读者对「这本书长什么样」没有统一印象；
- 生成时把画风前缀拼进 prompt 即可，不需要模型侧训练或 LoRA。

画风是**书级设定**，不放在全局模型配置里。原型封面工坊里可选：水墨 / 电影写实 / 国漫 / 版画 / 极简；头像工坊显示「跟随本书 · 水墨」，并提供「改全书画风…」跳回封面工坊。

改画风不会自动重画已生成的头像/封面（见 §5.4）。

### 4.3 书卡改版：封面作为第一眼（已拍板 C）

书卡从「首字方块 + 文字」改为「左侧 104×139 竖版封面 + 右侧信息」：

- 封面 3:4，圆角 8px，投影克制；
- 无封面时不空白：字标占位；**占位块本身是按钮**，点它直接进封面工坊，不要求用户先找 ⋯ 菜单；有章节的书显示「生成封面」，0 章书弱化为「可稍后添加」；
- 悬浮封面出现「换封面」；书卡菜单第一项是「封面…」（第二入口）；
- 卡片底部保留「AI 封面 · 水墨」这类来源说明，避免用户忘了这是生成的；
- 三列栅格在 1080px 降两列、720px 降一列，封面列同步缩到 88px。

**为什么不做顶部大图**：书架是扫读场景，竖版大图会把一屏书数从 6 本压到 2 本；左侧竖版在保持扫读密度的同时给出「书的样子」。

### 4.4 头像落位（已拍板 D）

- 角色列表：从 22px 放大到 **30px 圆形**（28–32 区间），30 个角色时能看出脸型/发型/颜色；详情仍是 52px 方章印；
- 头像工坊入口就在章印上，不额外加一排按钮；
- 生成依据只取这张角色卡的：性别·年龄·种族、外貌标签、势力·身份、一句话人设；**不读正文**，避免把后期剧情画进脸里；
- **首版不做参考图**：按本书画风 + 固定种子生成，不承诺「完全同一个人」；文案写「换一张脸可能变」，不写「脸不跑偏」；
- 首次生成和再次生成一样都是 2 张候选，不再区分「第一次先定一张脸」。

### 4.5 批量头像（已拍板 E）

角色一多（10–30 人），逐个点会疯。角色列表头提供「批量头像」：

- 只列**没有头像**的角色，已有头像的自动跳过并在摘要里报「已跳过 N 位」；
- 每人 1 张，先报人数/张数/预计耗时，再开始；
- 开始后逐位生成，行内状态「待生成 / 生成中 / 已生成 / 失败」；可停止，已完成的保留；
- 失败的那位单独重试，不影响其他人；批量同样遵守「不自动、先确认」。

## 5. 交互状态

### 5.1 封面工坊

| 状态 | 画面 | 可做什么 |
|---|---|---|
| 无封面进入 | 预览区是设计过的空位（字标 +「还没有封面」+ 一句引导） | 写描述、生成、上传、取消 |
| 已有封面 | 大图预览 + 当前候选 | 改画风/描述、重新生成、上传、取消 |
| 生成中 | 预览区遮罩 + 三步进度（理解书名 → 构图光线 → 落色细节） | 等；关闭会先确认「关闭会取消这次生成」，明确确认才中止；批量关闭≠取消（先停止或等完成） |
| 出结果 | 大图 + 2 张候选缩略图 | 点候选切换、使用这张、再生成一次 |
| 使用 | 关闭弹窗、书卡封面即时替换、toast「封面已更新」 | 继续别的操作 |
| 失败 | 预览区显示失败卡（不吞错） | 看原因、改描述再试、改用上传 |

封面弹窗固定 3:4，候选一次 2 张；生成按钮旁明写「一次 2 张 · 约 20 秒」，不做无提示的批量扣费。

### 5.2 头像工坊

- 左侧：大图预览 + 当前版本号（第 N 版）+ **2 张候选**；
- 右侧：画风（跟随本书）、设定依据 chips、可改的画面描述；没有「保持形象一致」开关，改成一句说明「首版按本书画风 + 固定种子生成，不读取旧头像作参考」；
- 不满意可在结果页「再抽 2 张」，不一次给 4 张；
- 没有头像的角色打开时预览区是字标空位，生成后才出现图。

### 5.3 未配置图像模型

封面/头像入口**仍然在**，但点开不是空白表单，而是一张说明卡：

> 还没有配置图像模型。封面和头像需要能画图的模型（如火山引擎 Seedream、阿里云百炼 Qwen-Image、智谱 CogView）。
> [去配置] [上传自己的封面/头像]

不在未配置时把「生成」按钮做成可点后报错。免费用户不会看到「去配置」作为主要出口：生成按钮显示「PRO 以上可用」+ 升级，上传仍然可用。原型当前默认展示 PRO 已配置路径；免费/未配置态在实现时按此文案补。

### 5.4 替换与历史

- **只保留上一张**：采用新封面/头像后，8 秒内可点「撤销」恢复上一张；不做 3/5 版历史 UI；数据表保留 `version` 字段，以后要扩不用改表；
- 改画风不触发重画；只影响下一次生成；
- 删除角色时头像进入待清理队列（不立即物理删除，留撤销窗口）；
- 删除书是软删，不立即清图片；彻底删除时才清理。

### 5.5 图像模型的添加 / 编辑 / 测试（沿用写作大模型口径）

| 位置 | 形态 | 关键状态 | 不允许发生 |
|---|---|---|---|
| 列表卡 | 卡 + 页脚结果行；chips 写「小说封面 768 × 1024 / 角色头像 512 × 512」 | 未测试 / 测试中… / 连接正常（绿）/ 失败原因（红） | 测试结果弹到别处；测试失败不给原因 |
| 添加/编辑弹窗 | 520px 弹窗 | 校验错误（`.ferr` 红条）/ 测试中…（按钮转「测试中…」）/ `.tresult` 绿红 / 模型清单拉取中·已拉到·拉取失败 / 编辑态「更换供应商」与「取消更换」 | 没填 Key 就保存；Key 明文回显；测试把用户填的 Key 弄丢；清单失败挡住手填；换供应商后沿用旧 Key |
| 删除确认弹窗 | 460px 弹窗 | 取消 / 确认删除 | 不盘点影响就删；删已生成图片 |

弹窗内「测试连接」＝**免费探活**（只验证地址与 Key，不出图、不计费）；「试画一张（会计费）」才真实画 1 张 512 × 512；「保存」不测试、不花钱。卡上「测试连接」同义免费探活。模型清单是独立探针：只拉 `/models`（或图像端点的模型列表），不发生成请求、不计张数。

**免费探活不是六家都成立**：没有 `/models` 或模型清单与图像端点不同时，如实显示「无法免费验证，请试画」，不能把生成请求叫探活。测试状态三分：`unverified`（保存未测）/ `reachable`（探活通，未出图）/ `draw_ok`（试画通）；「连接正常」只对应 `draw_ok`，否则写「地址与 Key 可用（未出图）」。

**图像端点未必提供 `/models`**：火山方舟、百炼、CogView 的图像接口与各自对话接口可能不是同一组模型清单，OpenAI 的 `gpt-image-1` 也不保证出现在 `/models` 里。因此「获取模型」失败不阻断保存：按供应商给已知候选（Seedream 4.0/4.5/5.0、Qwen-Image 2.0、CogView-4、`gpt-image-1`）+ 手填模型 id 兜底；清单只作便捷，不参与保存校验。

## 6. 数据、接口与素材

### 6.1 存储（已拍板：存数据库）

图片转 WebP 存进 SQLite，不落磁盘旁路目录（已拍板 B）：

- **`image_assets`**：一条逻辑资产（`id/novel_id/character_id/kind/status/version/sha256/mime/width/height/bytes/source/provider/model/style_key/prompt_hash/prompt_text/negative_prompt/prompt_template_version/seed/undo_token/undo_expires_at/job_id/created_at/adopted_at/expires_at`）；阶段 1 `status = candidate | current | previous`；
- **`image_asset_blobs`**：`PRIMARY KEY(asset_id, variant)`，`variant = full | thumb`，`data BLOB`；同一逻辑资产一条元数据、两条变体字节；列表查询只查元数据；单张 ≤10MB、单用户总量默认 1GB；
- **不变量**：每个封面/头像同时只有一条 `current`、至多一条 `previous`（部分唯一索引只作用在逻辑资产，不按 variant 重复）；采用时作废旧的 `previous`、物理删除更早的候选；`expires_at` 按状态取值：candidate 24h、previous 8s；`undo_expires_at` 单独记 8s 撤销窗口；启动 sweep + 上传/采用前按用户 sweep；
- **归属不另加列**：不设 `novels.cover_asset_id`/`characters.avatar_asset_id`；`cover`/`avatar` 由 `image_assets` 的 `status='current'` 派生，避免双写指针漂移；
- 目标尺寸：小说封面 768 × 1024、角色头像 512 × 512；上传与生成共用同一条管线：解码 → **等比缩放 → 居中 cover-crop** → 精确目标尺寸 → 重编码 WebP → 缩略图（208×277 / 96×96）；禁止直接拉伸；
- **只保留上一张**：采用新图后上一张标 `status='previous'`，8 秒内可撤销；不做 3/5 版历史 UI，表里保留 `version` 字段以后扩；
- 整库版本迁移天然带 BLOB；但**用户 zip 备份/单书导出不会自动带 BLOB**，必须走 §11.3 的备份格式 v7 显式纳入；不需要额外磁盘 assets 目录；
- 删除角色时头像资产与卡在同一事务删除（撤销角色卡不恢复头像）；删除书时清该书全部资产与 BLOB；`VACUUM`/WAL checkpoint 与单张/总量上限写进运维检查；
- 图片读取：`GET /api/image-assets/{asset_id}?variant=thumb|full&exp=...&sig=...`，HMAC 绑 asset+variant+exp（签名 URL 自证，不挂 Bearer）；`Cache-Control: private, max-age=3300`、`nosniff`；签名 1h，缓存必须短于签名，禁止 `immutable`；不直接暴露 `DATA_ROOT`。
- 资产端点：`POST /api/novels/{novel_id}/image-assets`（multipart）、`GET /api/novels/{novel_id}/image-assets?kind=&character_id=&status=`、`POST /api/image-assets/{id}/adopt`、`POST /api/image-assets/{id}/undo`；只有 candidate 可 adopt，首次采用撤销 = 删除 current 并回占位。

### 6.2 图像模型配置（已拍板：独立表）

新建 **`image_configs`**，不复用 `api_configs`（已拍板 A）：

- 只共享 `api_configs/crypto.py` 的 Key 加密、`http_client.py`、日志与错误分类；不复用 `ApiConfig` ORM 和聊天查询；
- 字段：`id/user_id/name/provider/base_url/api_key/models/default_model/declared_capabilities/is_default/status/last_test_status/last_test_error/last_tested_at/created_at/updated_at`，`UNIQUE(user_id, name)`；Key 落库前用 `api_configs.crypto` 加密；软删时同名新建要能“让位”（复用 api_configs 的软删规则）；
- `is_default` 只允许一个默认配置；第一条 active 配置自动默认；显式取消或删除默认时优先补另一个 active 配置；没有 active 配置时默认空；
- OpenAI 兼容口的 `declared_capabilities` 给高级手动声明（封面/头像/参考图/seed），其余供应商由适配器自动判断；
- **每本书单独绑定**：`book_image_settings.image_config_id` + `image_model`；新书默认用当前默认配置，封面/头像工坊可切换；
- **PRO 门槛**（已拍板 N）：生成/测试接口检查 tier；免费用户只能上传，不能生成/测试/批量（权益键在阶段 3 落地）；
- **保存与测试分开**（已拍板 #3）：保存不自动测试；「测试连接」免费探活；「试画一张」单独计费并明示（阶段 3）；
- 编辑换供应商（已拍板 #4）：阶段 1 的 `PUT /api/image-configs/{id}` 在 provider 变化时保守清空未随请求提交的 Key/Base/模型/测试状态，并把绑定书的 `image_model` 清空；专用 `replace-provider` 端点与取消在途 job 随阶段 3。
- 端点：`GET/POST /api/image-configs`、`PUT/DELETE /api/image-configs/{id}`、`POST .../restore`、`GET /api/image-configs?include_deleted=true`；阶段 1 不接 test-connection/test-draw/models/replace-provider，它们随阶段 3 另立 change；每书绑定用 `GET/PUT/PATCH /api/novels/{id}/image-settings`（PUT 全量、PATCH 部分更新）。
- 枚举：`provider = volcengine | aliyun | zhipu | openai | minimax | openai-compat`；`status = active | deleted`；`last_test_status = unverified | reachable | draw_ok | failed`。
- UI 复用 `Modal`、`VendorGrid`、`ModelPicker`、`SecretField`、`TestResult` 等 primitives，不把图像逻辑塞进聊天表单。

### 6.2.1 首版供应商（已拍板：六家全上）

火山引擎、阿里云百炼、智谱、OpenAI、MiniMax、OpenAI 兼容都接。实现按接口族分批，界面六家都保留；兼容口只承诺 OpenAI images 形态，中转站差异走「手填 Base + 试画」兜底。腾讯混元因 TC3 签名 + 异步任务，单独排期。

### 6.3 供应商适配（首批）

| 供应商 | 接口 | 模型与尺寸 | 鉴权 |
|---|---|---|---|
| **火山引擎（豆包 Seedream）** | `POST {base}/images/generations`；Base `https://ark.cn-beijing.volces.com/api/v3` | `doubao-seedream-4-0-250828` / `doubao-seedream-4-5-251128` / `doubao-seedream-5-0-260128`；`size:"3:4"` 原生 **768 × 1024**，`size:"1:1"` 1024 × 1024；`response_format` 支持 url / b64_json；`watermark:false` | Bearer API Key |
| **阿里云百炼（通义千问 Qwen-Image）** | `POST {base}/services/aigc/multimodal-generation/generation`；Base `https://dashscope.aliyuncs.com/api/v1` | `qwen-image-2.0-pro` / `qwen-image-2.0`；`size:"1728*2368"`（**注意：1728×2368 实际≈0.73，不是 3:4**，以 API 实际支持为准）；`"2048*2048"`（1:1），总像素 512²–2048²；`n` 1–6；同步返回 | Bearer API Key（北京/新加坡 Key 与域名不可混用） |
| **智谱 CogView** | `POST {base}/images/generations`；Base `https://open.bigmodel.cn/api/paas/v4` | `cogview-4` / `cogview-3-flash`；`864x1152`（**恰好 3:4，等比缩放到 768 × 1024，不需要裁切**）、`1024x1024`、`768x1344` 等 | Bearer API Key |
| OpenAI | `POST {base}/images/generations`；Base `https://api.openai.com/v1` | `gpt-image-1`；官方 1024×1536（2:3）/1024×1024/1536×1024，没有原生 3:4，裁切/补边到 768 × 1024 | Bearer API Key |
| MiniMax（可选，非默认） | `POST {base}/image_generation`；Base `https://api.minimax.chat/v1` | `image-01`；`aspect_ratio` 3:4 / 1:1；`response_format` base64 | Bearer API Key |
| OpenAI 兼容 | 同 OpenAI | 中转站路径与参数差异大，按「用户填 Base + 模型 + 试画一张」兜底 | 视中转而定 |
| 腾讯混元（后续） | TC3-HMAC-SHA256 签名 + 提交/查询异步任务 | `hunyuan-image-3.x`；需 SecretId/SecretKey 两把凭据 | 与 Bearer Key 形态不同，首批不接 |

**默认供应商＝火山引擎 Seedream**（`size:"3:4"` 原生即 768 × 1024，不需要裁切，最贴合书封）；MiniMax 保留为可选，不再作为默认或唯一供应商。阿里云百炼、智谱、OpenAI 作为并列选项；腾讯混元因 TC3 签名 + 异步任务，单独排期。

### 6.3.1 申请 Key 与 Base URL 入口（新建弹窗内直接可点）

| 供应商 | 申请 API Key | Base URL 从哪看 |
|---|---|---|
| 火山引擎 | <https://ark.volcengine.com/region:cn-beijing/apiKey> | 固定 `https://ark.cn-beijing.volces.com/api/v3`；<https://docs.volcengine.com/docs/ark/base-url-and-authentication?lang=zh> |
| 阿里云百炼 | <https://bailian.console.aliyun.com/cn-beijing/model/settings/api-key> | 固定 `https://dashscope.aliyuncs.com/api/v1`；<https://help.aliyun.com/zh/model-studio/base-url> |
| 智谱 | <https://bigmodel.cn/usercenter/proj-mgmt/apikeys> | 固定 `https://open.bigmodel.cn/api/paas/v4`；<https://docs.bigmodel.cn/cn/guide/start/quick-start> |
| OpenAI | <https://platform.openai.com/api-keys> | 固定 `https://api.openai.com/v1`；<https://platform.openai.com/docs/api-reference/images> |
| MiniMax（可选） | <https://platform.minimaxi.com/user-center/basic-information/interface-key> | 固定 `https://api.minimax.chat/v1`；<https://platform.minimaxi.com/document/image_generation> |
| OpenAI 兼容 | 无官方入口 | 由中转/自建服务提供，通常以 `/v1` 结尾 |

弹窗里选中哪个供应商，这两个链接与「控制台哪一页」的说明就换成哪一家；链接 `target="_blank"`，不离开原型。

适配成本：火山方舟与智谱都提供接近 OpenAI images 的请求形态（`/images/generations` + Bearer），适配成本最低；百炼是 DashScope 自有 `multimodal-generation` 形态，需要单独适配；OpenAI 只需把 3:4 裁切到 768 × 1024。

调研来源（2026-10-22，anysearch）：
- 火山方舟图片生成 API：<https://ark.volcengine.com/region:cn-beijing/docs/image-generation-api>（模型 id / 尺寸表另见 Seedream 4.0–5.0 指南）
- 阿里云百炼 Qwen-Image 文生图：<https://help.aliyun.com/zh/model-studio/qwen-image-api>
- 智谱 CogView-4：<https://docs.bigmodel.cn/cn/guide/models/image-generation/cogview-4>

**关键：不让模型画中文字**。中文标题在图像模型里几乎是随机笔画；产品生成的是**无字画面**，前端按真实字体排版书名、作者名、印章。示意素材里把标题画进图里只是为了让人一眼认出是哪本书，真实实现不要这么下发 prompt。

### 6.4 Prompt 组成

封面（只读简介，不读正文）：

```
{画风前缀}，{题材气质}，{简介前 120–200 字的核心画面}，
竖版 3:4，主体偏下/偏侧，上方留出书名位置，无文字、无水印、无边框
```

头像：

```
{画风前缀}，{性别 · 年龄 · 种族}，{外貌标签}，{势力 · 身份}，
{一句话人设的气质}，半身像，中性背景，正面/四分之三侧，无文字、无水印
```

- 不把 `dossier.plot`（剧情定位）和 `background` 全量喂进去：两者最容易带出后期剧透；
- 解释性文字（“他表面…其实…”）要转成视觉描述再下发，不能原样拼接；
- 首版不传参考图：头像按本书画风 + 固定种子生成，不读取旧头像，也不传整页截图。

### 6.5 失败与安全

- 供应商内容审核拒绝：保留供应商返回的可读原因，提示「改一句描述再试」，**不自动改写 prompt 重试**；
- 额度不足/鉴权失败：给出「去配置 / 去充值」出口；
- 超时：可取消；已产生的费用按供应商口径处理，UI 不承诺退款；
- 生成内容只存在本机；发送给供应商的只有拼好的 prompt，不发送正文、设定全文或书库索引。

## 7. 成本与风控

- **PRO 以上才能生成，费用用户自带 Key**（已拍板 N/#15）：AI 画图只对 PRO 及以上开放；PRO 用户自己填火山/阿里/OpenAI Key，费用直接付给供应商，爱小说不代付、不送张数；免费用户只能上传；
- **按张计费，不进 token 账**：图像模型按张/按次计价，与现有 token 用量不是同一账本；单独记「图像生成次数/张数/耗时」，卡上显示「上次生成 14 秒 · 2 张」；
- **永不自动生成**：封面/头像只在明确点击后发生；批量先看人数/张数/预计耗时；
- **不默认重画**：改画风、改角色卡都不会自动重画；用户点「重新生成」才产生新费用；
- **保存不花钱**：保存不自动测试；「测试连接」免费探活；「试画一张」单独点击并明示计费；
- **成本上限**：单次生成张数上限（封面 2、头像 2、批量每人 1）在适配层硬限制，防止中转站返回 n=9 之类意外。

## 8. 边界与遗留

- **导入自有书**：导入时不生成封面；书卡走字标占位，进书后可生成；
- **拆书产物**：拆书结果页不自动配图；后续可做「按拆出的角色批量生成头像」，但不在首版；
- **备份/导出**：图片存 DB BLOB；整库版本迁移天然带，但用户 zip 备份/导出全书必须用格式 v7 显式纳入 assets（见 §11.3）；ManuscriptDownload 仍只含正文。
- **多设备**：图片在本地，不随账号同步；换机靠备份包；
- **旧书**：无字段即无封面，不做回填；
- **性能**：书卡列表只加载缩略图（建议 208×277 webp），原图在详情/工坊加载；批量生成串行或小并发，避免供应商限流。

## 9. 拍板清单

| # | 问题 | 推荐 | 代价/备注 |
|---|---|---|---|
| A | 图像模型配置放哪 | **独立 `image_configs` 表**（已拍板） | 不与写作配置共用表；UI 仍放第三页签 |
| B | 画风作用域 | 按书统一，封面/头像共用 | 换书要重选画风；不能全站一套 |
| C | 书卡封面布局 | 左侧 104×139 竖版 | 书卡信息密度略降，一屏仍可 3–6 本 |
| D | 头像形状 | 列表圆 **30px**（28–32）+ 详情方 52px（已拍板） | 列表行高略增；30 个角色能看清脸 |
| E | 批量头像 | 首版就做 | 多一层弹窗与串行调度 |
| F | 计费口径 | 图像单独按张记账，不混 token；PRO 自带 Key（已拍板） | 需要 image_jobs/usage 台账；平台不代付 |
| G | 封面比例 | 3:4（界面只显示 768 × 1024） | OpenAI 无原生 3:4，需裁切/补边；比例是实现细节，界面不出现 |
| K | 头像尺寸 | 512 × 512 | 1:1 比例各家都有，但 512 分辨率不一定原生；先按原生出图再下采样，未采用的候选不永久保留 |
| H | 允许上传 | 封面、头像都允许（JPG/PNG → 768×1024 / 512×512）（已拍板） | 免费用户唯一可用路径；服务端统一裁切/压 WebP |
| I | 创建/编辑形态 | 与写作大模型同一个弹窗（能力只读，无参考图）（已拍板） | 无新形态＝零学习成本；能力由系统判断，作者不勾 |
| L | 默认图像供应商 | 火山引擎 Seedream（768×1024 原生） | MiniMax 不再默认；已有 MiniMax 配置仍可编辑 |
| M | 编辑态换供应商 | **允许，二次确认；清 Key/模型/测试，不改名**（已拍板） | 与写作大模型锁死不同；换错可「取消更换」；后端要显式 replace-provider |
| J | 图像测试的粒度 | **测试连接＝免费探活；试画一张＝单独计费**（已拍板） | 保存不测试；免费探活失败不挡手填；付费试画必须明示 |
| N | AI 生成门槛 | **PRO 及以上；免费用户只能上传**（已拍板） | PRO 仍自带 Key，费用付给供应商；后端真拦 `tier_required` |
| O | 多配置怎么用 | **每本书单独绑定**（已拍板） | 新书默认当前默认配置；工坊显示「本书图像模型」 |
| P | 头像候选/批量 | **头像 2 张；批量只补没头像的、每人 1 张、可停止**（已拍板） | 首版成本最低；4 张/全员重画后置 |
| Q | 图片存哪 | **SQLite BLOB + WebP**（已拍板） | 整库迁移天然带；用户 zip 备份需格式 v7 显式纳入；db 会变大，需限单张/总量 |

## 10. 验证记录（2026-10-22）

- 独立栈：`main d4bf73fa` + `vite:5291` → `uvicorn:8101`，`DATA_ROOT=/tmp/cover-proto-data`（不碰共享 demo 栈）；
- 抓取：书架、设定→角色两页真实 `.app-shell` + 全量 `real-all.css`（305KB），入库 `cover-art-captures/`；
- 图像模型屏宿主沿用 2026-10-20 `modelconfig-captures/dom-config-list.html`（真实两配置渲染，仅新增页签），已复制进 `cover-art-captures/` 并逐字校验；
- 自检：`check-cover-art-proto.py` **ALL PASS**（HTML 闭合、全部 class 可溯源、CSS/宿主逐字一致、18 个 SVG 内联、无外链、关键锚点 55 项）；
- Playwright 走通：封面工坊（PRO→生成中→2 候选→采用→8 秒撤销；免费→生成按钮变「PRO 以上可用」、上传仍可用）、头像工坊（2 候选→采用→撤销；无头像角色显示字标空位）、批量头像（只列 2 位无头像，已有头像自动跳过，完成后补齐）、图像模型（页签切换→添加弹窗→保存/免费探活/付费试画三分→获取模型清单→编辑弹窗「更换」→确认后清 Key、不改名→取消更换回滚→删除确认→8 秒撤销→卡片恢复）；
- 第二轮评审修复：免费作用域（写作页签不再误禁；配置管理开放，只锁生成/测试/批量）、8 秒撤销、批量停止/本次撤销、关闭未采用候选确认、配置字段转义、朱雀页签、删除盘点改「关联书籍」、编辑留空模型保留旧值、卡片测试更新徽标、书卡来源标签、0 章封面占位降级；
- 第三轮评审修复：关闭确认可取消、关闭≠取消、批量关闭先停止、换供应商后禁止回填旧模型、测试三态（未测试/地址可用/已试画）、删除旧撤销失效、批量未配置守卫、第二套演示配置 + 书级图像模型选择器（封面/头像页脚跟随）；
- 交互过程 console error = 0；
- 截图：`cover-art-captures/proto-shots/01…29*.jpg`（01–17 封面/头像，18–25 图像模型列表、弹窗与模型清单，26 编辑态更换供应商，27 免费态 PRO 门槛，28 批量只补无头像，29 付费试画）。

## 11. 第二轮内部评审补充：冻结前必须补齐的契约

第二轮评审结论：视觉与流程可以进入实现，但**全量图像生成 no-go**，以下四层契约冻结前不要写第一张表。原型只负责把交互摆出来，这些是后端/数据约束。

当前状态：原型侧 P0/P1 已修（见 §11.7）；下面这些是**冻结清单**，代码尚未实现，冻结并通过评审后才解除 no-go。

### 11.1 任务层（必须新建，不复用 `job_runner`）

- 表：`image_jobs`（`id/user_id/novel_id/character_id/parent_id/kind/status/phase/provider_task_id/request_json/result_json/error_json/requested_n/returned_n/billed_n/idempotency_key/cancel_requested/created_at/started_at/finished_at/duration_ms`）+ `image_batches`（父任务：`id/user_id/novel_id/status/total/done/failed/created_at/finished_at`）+ `image_batch_items`（`batch_id/character_id/job_id/status/error/attempts`）。
- 状态机：`queued → submitting → generating → downloading → persisting → succeeded | failed | cancelled | cancelled_billed | interrupted`；批量父任务额外 `total/done/failed`。
- 端点：创建返回 `202 {job_id}`；`GET /image-jobs/{id}` 轮询；`POST /image-jobs/{id}/cancel` 设置 `cancel_requested`；批量 `POST /avatar-batches`、`GET /avatar-batches/{id}`、`POST .../cancel`、`POST .../retry/{item}`。
- 约束：`idempotency_key` 唯一；同一目标（书封面 / 角色头像 / 批量父任务）最多一个 active job（部分唯一索引）；启动时 sweep `running` 为 `failed/interrupted`；**关闭弹窗 ≠ 取消**，取消必须显式点；已接单无法中止时标 `cancelled_billed`，不假装没发生。
- 不占用 `job_runner` 的全局单飞槽；批量串行或最多 2 并发，遇 429 用 `Retry-After` 暂停。

### 11.2 资产层（BLOB 生命周期）

- `image_assets` 逻辑资产 + `image_asset_blobs(asset_id, variant)` 复合主键；`undo_token/undo_expires_at`、`expires_at`（candidate 24h / previous 8s）、current/previous 部分唯一索引、启动 sweep、删除清理，见 §6.1。
- 端点：`POST /api/novels/{id}/image-assets`、`GET /api/novels/{id}/image-assets`、`POST /api/image-assets/{id}/adopt`、`POST /api/image-assets/{id}/undo`；采用/撤销用 `undo_token` 幂等。
- 采用/撤销/连续采用必须在**同一事务**内完成：新图 `current`、旧图 `previous`、更旧 `previous` 物理删除、写 `undo_token/undo_expires_at`；撤销反向交换；8 秒窗口由服务端 `undo_expires_at` 强校验，前端 toast 用现网 `UndoToast` 的 8 秒口径，不再自造 5.2 秒。
- 只有 `candidate` 可 adopt；current/previous 重复 adopt 返回 409 `asset_not_candidate`；唯一索引并发冲突转 409 `asset_state_conflict`，不 500。
- 图片读取走签名 URL 或 fetch-blob，`variant=thumb|full`，列表 DTO 直接带 `{asset_id, thumb_url, width, height, version, source, style_key, url_expires_at}`，避免 N+1；签名 1h、缓存 `max-age=3300`。
- 单张 ≤10MB、单用户总量默认 1GB；上传与生成统一解码/像素上限/重编码 WebP/EXIF 清理；Pillow 加入 requirements 与打包链；下载供应商 URL 限制 http(s)/重定向/超时/大小，防 SSRF。

### 11.3 备份 / 导出 / 迁移

- 已实现（`c-cover-avatar-backup`）：`FORMAT_VERSION` 6 → **7**；每书 `images/{asset_id}-{variant}.webp` + `images/manifest.yaml`（sha256/mime/宽高/kind/variant/source/style + 书/角色设置）+ 配置包 `image_configs` 段；`test_backup_images.py` roundtrip 通过。
- 导出/导入白名单已补 `image_assets`（用 `status='current'` 表达当前图，不写 `cover_asset_id`/`avatar_asset_id`）/`book_image_settings`/`character_image_settings`/`image_configs`；config-only 包也读 `format_version` 做闸；旧读取器只拒 `>7`，v6 旧包正常跳过图像段。
- 导入：重映射角色 id，`image_config_id` 按配置名恢复（缺失置空 + warning），`image_configs.api_key` 用新库钥匙重加密；旧包没有 images/image_configs 段时正常跳过。
- 迁移：`migration/engine.py` 已覆盖 `image_configs`，报告 `dead_api_keys`/`dead_image_keys`，`dead_keys` 保留总数；schema 指纹变化走 c-db-per-version。
- Pillow 需加入 `requirements.txt` 与 `scripts/check_py_licenses.py` 白名单，并验证 PyInstaller/Nuitka 打包。
- 备份 roundtrip（生成 → 备份 → 换目录恢复）列为发布门禁。

### 11.4 每书绑定与书级设置

- `image_configs.is_default`（唯一默认）；第一条 active 自动默认，取消/删除默认时优先补另一个 active 配置。
- 书级切换：`PATCH /api/novels/{id}/image-settings {image_config_id, image_model}` 只改绑定，不清画风/描述/seed；整份保存用 PUT。封面/头像工坊显示「本书图像模型」并提供真正可选的列表，不是只跳全局配置页。
- 新增 `book_image_settings`（`novel_id/style_key/cover_prompt/cover_seed/image_config_id/image_model`）+ `character_image_settings`（`character_id/avatar_prompt/seed`）；画风/封面描述/封面种子是书级，头像描述/种子是角色级，不能把 `avatar_prompt` 放书级。
- 「再抽 2 张」的种子策略：`candidate_seed = character_seed + batch_index * 2 + candidate_index`；不支持 seed 的供应商（如 `gpt-image-1`）走 prompt 变体/随机，UI 不承诺固定种子。
- 共享配置 `replace-provider` 时，事务内清空/标记所有绑定书的 `image_model`，确认弹窗写明“影响 N 本书”；配置软删/模型被移除时，绑定书进入 `model_unbound` 而不是静默换供应商。
- `ImageState` 预检：`ready / no_config / model_unbound / no_key / tier_required / unsupported_size`，前端不重复推导。

### 11.5 PRO 门控与试用

- 新增 feature key `image-generate`，按 `docs/contracts/entitlement-defaults.json` 六步 SOP 同步 S 端权益、`features.ts`、`STANDARD_FALLBACK`、路由装饰器与对拍测试；不要复用 `require_ai_access`（它会查写作 Key），用 `require_tier_access`。
- 权限矩阵：`none/free/standard/expired → 只能上传`（standard 不享受 AI 生成）；`trial → 按 PRO 同权`；`pro/max → 可用`；降级后旧图保留。
- 旧权益快照没有 `image-generate` 时的降级口径：trial/pro/max 视为可用、其余不可用；上线前要求 S 端快照版本包含该 key。免费用户的配置管理（查看/新增/编辑/删除）不花钱，可以开放；只锁生成/测试/试画/批量。
- 上传端点永远免费；生成/测试/试画/批量返回 `tier_required`，不能只靠前端置灰。

### 11.6 供应商适配器

- 统一接口：`probe()`、`fetch_models()`、`capabilities(model)`、`build_request(canonical)`、`parse_response()`、`download(url)`；canonical 请求固定 `{purpose, prompt, width, height, n, reference_asset_id?, seed?}`，响应固定 `{candidates:[{bytes|url, width,height, native_w,native_h}], billed_n}`，错误固定 `auth/quota/rate_limit/moderation/timeout/network/invalid/empty`。
- 三套 wire：OpenAI-ish（火山/智谱/OpenAI/兼容）、DashScope `multimodal-generation`（百炼）、MiniMax `/image_generation`；不要用一个 `data[0].url` 通吃。
- 尺寸：目标 768×1024 / 512×512；供应商原生比例不同，统一“等比缩放 → 居中 cover-crop → 精确目标尺寸”，断言不变形；`1728×2368` 不是 3:4，OpenAI 没有原生 512×512。
- 能力矩阵按 `(provider, model)` 记录 `supports_n/supports_seed/supports_reference/watermark/size`；OpenAI images 无 seed，固定种子文案要按供应商降级；首版不做参考图。
- 免费探活不可统一承诺；没有免费探活的供应商如实显示“请试画”，不要把生成叫探活。

### 11.7 原型已修 / 仍待修

已修：免费作用域（共享页头不再误禁；配置管理开放，只锁生成/测试/批量）、8 秒撤销、批量停止/本次撤销、关闭未采用候选确认、配置字段转义、朱雀页签、删除盘点改「关联书籍」、编辑留空模型保留旧值、卡片测试更新徽标、书卡来源标签、0 章封面占位降级、旧参考图文案清理、测试/试画请求序号与关闭/切屏定时器清理、免费态上传主按钮、弹窗 aria 与窄屏结果行换行；第三轮又修：关闭确认可取消、关闭≠取消、批量关闭先停止、换供应商后禁止回填旧模型、测试三态（未测试/地址可用/已试画）、删除旧撤销失效、批量未配置守卫、第二套演示配置 + 书级图像模型选择器。

仍待首版前收掉：模型组合框键盘导航/过滤、上传中/校验/裁切/失败/撤销状态、试画尺寸可选封面 3:4 或头像 1:1、「再抽 2 张」前确认替换上一批、来源标签从 asset 派生而不是内存状态。

### 11.8 阶段 1/2 实现状态（2026-10-23）

后端垂直切片已落地（`openspec/changes/c-cover-avatar`）：

- `image_configs`（加密 Key/默认/软删恢复/include_deleted）、`image_assets` + `image_asset_blobs(asset_id, variant)`、`book_image_settings`（含 cover_seed）、`character_image_settings`；
- 上传（JPG/PNG/WebP→WebP，768×1024/512×512 + 缩略图，10MB/30MP/4096，拒绝 GIF/BMP/TIFF）、采用/撤销（只有 candidate 可 adopt、8s `undo_expires_at`、current/previous、sweep）、资产列表、签名读取（短缓存）、每书/角色设置 API（含角色 GET）；
- 角色/资产/设置统一归属校验，堵跨用户读写；删除角色/合并角色/删除书的资产级联在同一事务；
- prompt v3：书名/角色名（含自由文本内嵌）脱敏，封面不读简介原文，正向无文字 + negative + canonical hash + 模板版本 + cover/avatar/candidate seed；
- 并发 adopt/undo 条件更新与 409；签名密钥故障降级；PATCH 设置、links 刷新、候选丢弃、UTC 时间、资产 DTO 统一；
- `tests/test_image_assets.py` 18 passed；后端全量 2417 passed / 296 skipped，相关组（角色/书架/api key/backup/db lifecycle/bundle manifest）153 passed。

已落地 `c-cover-avatar-backup`：`FORMAT_VERSION=7`（images manifest/full/thumb + 书/角色设置 + image_configs）、迁移 `image_configs` Key 转接、`test_backup_images.py` roundtrip。

阶段 2 上传型前端已落地（`openspec/changes/c-cover-avatar-ui`）：

- `lib/imageApi.ts`：配置/资产/设置/链接刷新统一封装；XHR FormData 上传带进度；签名 URL 统一 `mediaUrl()`。
- 模型配置页第三页签「图像模型」：六家配置 CRUD/默认/软删恢复/include_deleted、换供应商确认、删除解绑书数提示。
- 封面/头像工坊：上传、候选列表、采用、8 秒撤销、丢弃、当前图展示、书/角色设置 GET+PATCH、prompt/negative/hash 预览。
- 书卡封面入口与封面图展示；角色列表/详情头像展示与头像入口；删除文案说明图片级联与撤销口径。
- 免费用户可上传；生成/试画/批量只保留「后续版本开放」占位。
- 前端验证：`tsc` 全绿；`vitest run` 1772 passed；coverage contract 100%；`npm run build` 通过；`design:lint` 通过。

阶段 2 验证收官：`e2e/image-workshop.spec.ts`（隔离栈：专属 vite＋uvicorn 18000＋/tmp DATA_ROOT）钉「API 建书 → 上传 → 候选 → 采用 → 书架可见封面 → 首次采用撤销回无图 → 再采用书架可见」；书卡封面入口同步进 `docs/design-c/prototypes/list.html`，`design:lint`＋design-parity（书架/配置/预览 10 场景）全绿。8s 撤销支持跨弹窗续期（采用结果上抛书架层，重开工坊以 `initialUndo` 续撤销）。

仍未落地（见 `c-image-generation`）：`image-generate` 权益、provider adapter、`image_jobs`。

## 12. 不在本原型范围

- 章节插图、场景图、地图、关系图头像；
- 封面模板市场 / 字体选择器 / 手工排版器；
- 图像模型的多账号轮询、失败转移、并发队列；
- 角色头像的「同一角色多套表情」；
- 图片 CDN、云同步、跨设备。
