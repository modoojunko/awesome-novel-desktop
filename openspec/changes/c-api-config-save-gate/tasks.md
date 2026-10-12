# tasks — c-api-config-save-gate

> 前置：`c-ai-availability-fixes` 组 5（「你好」禁思考最小生成判据）实现完成是 2.2 的开工条件（design Risks 硬前置）。

## 1. 原型先行（C端）

- [ ] 1.1 `docs/design-c/prototypes/model-config.html` 补三形态（创建/编辑两态）：保存判败原位展示且弹窗不关、保存中 busy（按钮「保存中…」＋spinner）、改连接字段后过期错误清除；验证＝原型可点过各形态且无布局漂移
- [ ] 1.2 `docs/design-c/prototypes/ADJUSTMENTS.md` 登记本次偏差（保存判败原位展示＋保存中 busy 为新增形态，偏差原因＝内测坏 URL 假阳性整改）；验证＝登记条目在册

## 2. 后端保存门禁

- [ ] 2.1 确认探测判据在位（`connection.py`：200 必须 API JSON＋「你好」禁思考最小生成、收到格式正确回复才判 ok，`c-ai-availability-fixes` 组 5）；本 change 复用不重写判据；验证＝坏 URL（`https://platform.deepseek.com/api_keys` 形态）返回 `endpoint_mismatch`，真端点发「你好」收到格式正确回复判 ok
- [ ] 2.2 `create_api_config`/`update_api_config` 落库前探测：创建恒测；编辑按「值变化」触发（`base_url`/`api_format` 比对已存值、`api_key` 非空为变更；Key 留空用已存密钥，不报「API Key 为空」）；判败不落库、422 detail＝`{code: "probe_failed", status, message}`（message＝探测原文案）；判过按 `test_api_config` 同款持久化 `last_test_status/last_test_error/last_tested_at/models`；验证＝pytest：坏 URL 422 库无行、真端点 201、判过后库列已写
- [ ] 2.3 触发与豁免边界钉：仅改名/仅改 models 零探测（探测桩零调用）；「非 ok 即拦」参数化钉（endpoint_mismatch/auth_error/timeout/network_error/rate_limited/unknown 各断言 422 且库无行）；备份导入/迁移/朱雀 upsert 不受门禁影响钉；验证＝pytest
- [ ] 2.4 响应契约：成功响应携带嵌套 `probe`（ok/status/models/note），不与配置顶层 `status`/`models` 撞名；验证＝pytest 断言形状
- [ ] 2.5 存量测试桩改造：conftest autouse 桩 `api_configs.service._test_connection`（钉死打桩点，防 `from .connection import test_connection as _test_connection` 别名陷阱）；`test_api_key_config.py` 等存量 CRUD 用例免触网；验证＝全量 pytest 离线可跑全绿

## 3. 前端接线

- [ ] 3.1 判败留在弹窗：422 `probe_failed`（经 `lib/api.ts` 既有 `detail.message` 提取）呈现在连接测试结果位（tresult bad）；分流规则＝probe_failed→tresult、409 撞名/网络/503→ferr；改连接字段即清过期错误；验证＝vitest：判败弹窗不关＋错误文案可见＋「判败→改字段→旧错误消失→重存成功」状态机
- [ ] 3.2 删创建后二次 `testConfig`：卡片状态与徽标取保存响应 `probe` 且经 `refreshStatus` 回读不回退（持久化兜底）；成功 toast 固定「已添加「X」· 连接正常」（note 不进 toast）；保存按钮 busy 态（「保存中…」＋spinner）；验证＝vitest：保存只发一次相关请求＋状态回读不打回「未测试」＋busy 态断言
- [ ] 3.3 `lib/api.ts` `detail.message` 提取路径补单测钉（对象形状 detail）；验证＝api-error-message 测试绿

## 4. e2e

- [ ] 4.1 新增用例：坏 URL 保存被拦（弹窗不关、错误可见、配置列表无新行）＋真实端点成功臂（本地假上游桩，参照 ai-assist `STUB_BASE` 桩服务器先例——`page.route` 拦不到后端出网探测）；验证＝e2e 通过
- [ ] 4.2 存量改造：`config-page.spec.ts` ②③「127.0.0.1:1 网络错误照常入库」用例改写（造数换桩上游或后端种子；②的删除/Undo 链路另找铺垫）；验证＝config-page spec 全绿

## 5. 回归（实际输出结论记录在 PR/归档总结）

- [ ] 5.1 后端全量 pytest（用 `client/backend/.venv` 解释器）：全绿，零新增红
- [ ] 5.2 `npm run design:lint` 全绿；`npm run design:check` 全绿（像素差 <0.2%，书架屏存量光栅漂移按先例除外）
- [ ] 5.3 双端类型检查：C端 `tsc --noEmit` 全绿（本 change 纯 C端，S端零改动）
- [ ] 5.4 前端 vitest 全量＋C端 e2e config-page 相关 spec 全绿
- [ ] 5.5 共享段判定核对：不触碰 base.css 令牌/基础组件类与 pill/notice/sk/panel/f-err 家族（依据 proposal Design Impact），`scripts/design-cross.mjs` 不适用；验证＝判定依据引用在回归结论中
- [ ] 5.6 `openspec validate --strict`：本 change 与 `c-ai-availability-fixes` 双 change 同验通过（归档 sync 判据 delta 先行或同批）
