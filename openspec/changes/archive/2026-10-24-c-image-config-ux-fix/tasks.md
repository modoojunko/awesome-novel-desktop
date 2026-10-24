# Tasks: c-image-config-ux-fix

## 1. 原型先行（C端硬性流程）

- [x] 1.1 `docs/design-c/prototypes/model-config.html`：图像模型弹窗改单「模型」格（删「模型清单」textarea）、加「测试连接」按钮与结果行（通过=ok、失败=err，失败文案带可读摘要）、删底部「连接测试 / 试画 / 拉取模型清单在后续版本开放」提示；配置卡片模型 chips 区改「模型：{id}」单行＋测试状态胶囊。验证：原型打开人工走查新增/编辑/测试三态。
- [x] 1.2 `docs/design-c/prototypes/ADJUSTMENTS.md` 登记本次偏差条目（单模型收敛、测试连接、卡片改版、预设 5.0、新建态测试通过后保存重置为未测试的说明）。验证：条目可逐条与 1.1 对拍。

## 2. 后端

- [x] 2.1 `image_assets/service.py` create/update：请求未显式携带 `models` 时派生 `models=[default_model]`。create 端点 `body.model_dump()` 会带默认值，须以 `model_fields_set` 判显式性（先例 router.py cover_seed），显式空数组亦按派生处理；`default_model` 为空时派生 `[]` 不落 `[""]`；显式非空清单原样尊重。换供应商清空 last_test_* 的既有行为补测试钉。验证：pytest 新增 4 例（派生/显式尊重/空数组按派生/换供应商清空）。
- [x] 2.2 新增 `POST /api/image-configs/test`：body 可选 `config_id`＋`provider/base_url/default_model/api_key`；带 id 缺 Key 用存量，`config_id`＋非空 `api_key` 并存以 body 为准；复用 generation.py 适配器发最小试画（avatar 档、极简 prompt、n=1、不落资产；适配器 URL 回包下载后即弃）；端点内 `asyncio.wait_for` 约 75s deadline，超时按失败归类并落可读摘要；成功/失败写 last_test_* 三列（仅带 id 时），`last_test_error` 落库前截断 500；错误分类复用既有分类器；挂 `ai_feature("image-generate")`＋`require_tier_access`；同用户 30s 节流用 module-global dict，留测试重置缝。验证：pytest 新增——成功落库、失败带可读摘要、超时归类失败、免费用户 403、无 id 不写库、节流 429（用重置缝隔离状态）。
- [x] 2.3 后端全量 pytest 绿（worktree 独立 venv，`uv venv` 建在 gitignored `venv/`；全量必带 `PROMPT_PACK_DEV_DIR`）。验证：`pytest` 0 红。

## 3. 前端

- [x] 3.1 `lib/imageApi.ts`：火山预设 models 刷为 `["doubao-seedream-5-0-260128","doubao-seedream-4-5-251128","doubao-seedream-4-0-250828"]`（预填取首）；新增 `testConfig()` 封装；`ImageConfig` 接口补 `last_test_error`/`last_tested_at`；`createConfig` 类型放宽 models 可省。验证：单测断言预设首项与 API 路径。
- [x] 3.2 `ImageConfigPanel.tsx`：表单删 modelsText/「模型清单」格，提交不带 models；加「测试连接」按钮（保存前后均可测；测试中 disabled＋loading；结果行 ok/err 呈现，失败带摘要；文案告知「测试会真实生成一张小图」；429 节流呈现「测试过于频繁」而非裸报错）；删底部旧提示；配置卡 chips 区改「模型：{default_model}」＋测试状态胶囊（ok/err，含 last_test_error 摘要）。验证：`imageConfigPanel.test.tsx` 更新——表单无清单格、测试成功/失败/429 三种呈现、免费用户置灰＋后端拒绝分支、旧提示不再出现。
- [x] 3.3 门禁：vitest 全绿、`tsc --noEmit` 绿、`npm run design:lint`＋`design:check` 绿（原型与实现 parity）。验证：三条命令 0 红。
- [x] 3.4 e2e 对拍：`e2e/image-workshop.spec.ts`、`tier-features.ts` 如有配置表单/清单断言则同步更新，并补一条「测试连接失败呈现摘要」的桩断言。验证：相关 e2e spec 绿。

## 4. 收尾

- [ ] 4.1 真机六供应商试画抽检（volcengine 5.0 系/aliyun/zhipu/openai/minimax/openai-compat 各一次成功＋一次坏 Key 失败），兼作 c-image-generation tasks 4.2 的输入证据。验证：六家截图/响应摘要留档 change 目录。
- [ ] 4.2 归档随实现 PR 走：sync delta → 移档 archive，同 PR 带上（sync 前 fetch 确认基线）。验证：`openspec validate` 绿、PR 内 archive 就位。
