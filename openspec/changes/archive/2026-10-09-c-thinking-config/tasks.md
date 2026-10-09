# tasks — c-thinking-config

## 1. 后端存储链

- [x] 1.1 `models/api_config.py` 新增 `thinking_enabled`（Boolean，默认 0）＋
  `thinking_effort`（String(10)，默认 low），带 DDL 默认（迁入链按列交集自动带回）；
  验证＝pytest 全量绿（schema fingerprint 变更走既有迁入链用例）
- [x] 1.2 `schemas.py`：`ThinkingEffort` Literal；Create/Update/TestRaw 三请求体与
  `ApiConfigResponse` 携带两字段（Update None=不更新）；验证＝pytest CRUD 用例
- [x] 1.3 `service.py`：create 落库、`_config_to_dict` 回读、`test_api_config` 探针按
  配置发、update 字段白名单加两项；`router.py` create/test-raw/update 三入口接线；
  验证＝pytest `test_create_config_thinking_fields_roundtrip`／`…_defaults_off_low`
- [x] 1.4 `backup/export.py`＋`importer.py`：备份包携带两字段（加键不升
  format_version；旧包缺键兜底关/low）；验证＝pytest 备份 roundtrip 全量绿

## 2. 后端下发与重试

- [x] 2.1 `connection.py`：`_generation_payload` 按配置发思考参数＋思考开启预算放大
  （`_PROBE_MAX_TOKENS_THINKING=1024`）；`test_connection` 签名穿链三处探针调用点；
  验证＝pytest `test_chat_probe_thinking_enabled_sends_effort`
- [x] 2.2 `connection.py`：`_post_with_thinking_retry` 带思考参数的 400 不看文案一律
  去参重试（thinking＋reasoning_effort），预算同步放大，两次都 400 回更贴切那份；
  验证＝pytest `test_chat_probe_glm_forced_thinking_rejected_retries_stripped`
  （GLM 纯中文拒法回归钉）＋存量 `…_retries_without_thinking`／`…_model_rejected_strict`
- [x] 2.3 `ai_client.py`：构造器收两字段；`_thinking_params`（开＝enabled＋effort，
  关＝disabled，记忆 base 跳过）；openai chat/stream 去参重试＋记忆；anthropic chat
  重试剥 extra_body effort、stream 补开流前去参重开（原先无重试，开思考会被
  budget_tokens 拒硬失败）；判据扩中文「思考」/reasoning/effort；
  验证＝pytest TestThinkingConfig 四钉＋存量 thinking 用例
- [x] 2.4 `settings/ai_router.py`：`_judge_chat` 显式关思考压过配置（volume-plan-ai
  口径不变）；ai_client 显式传 thinking 时配置 effort 不搭车；
  验证＝pytest `test_explicit_thinking_override_suppresses_config_effort`＋judge 存量

## 3. 前端

- [x] 3.1 `types/api-config.ts`：`ThinkingEffort`＋`ApiConfig` 两字段
- [x] 3.2 `ApiConfigForm.tsx`：思考模式 seg（开/关）＋思考强度 seg（低 low/高 high/
  深 max，关闭时 `.lock` 灰置、值保留）＋开启时提示行；编辑态回读；提交/测试负载携带；
  验证＝vitest 思考参数 describe 两用例
- [x] 3.3 `useApiConfigs.ts`＋`ApiKeyConfigPage.tsx`：addConfig/testRawConfig 负载
  类型与传参；验证＝vitest 全量绿＋tsc 零错

## 4. 设计工件

- [x] 4.1 原型 `docs/design-c/prototypes/model-config.html` 弹层补两控件形态
  （思考模式 seg＋思考强度 seg 关闭灰置＋开启提示行，含交互 JS 与 readForm 读数）；
  验证＝原型可点、无布局漂移（复用 .seg/.label-row/.cf-hint，零新形态）
- [x] 4.2 `docs/design-c/prototypes/ADJUSTMENTS.md` 登记（控件为新增形态；强度交互
  形态＝seg 分段钮，问答预览稿的下拉形态在实现时按设计语言归一为 seg）
- [x] 4.3 design:lint 过（零新增违例）；design:check 预期零差异——`#modalConfig` 不在
  design-parity 两 spec 场景清单（与 c-prose-model-select 登记 #4 同例），无基线像素变更

## 5. 回归

- [x] 5.1 后端全量 pytest：1861 passed／0 failed；ruff 0.16.3 零新增
- [x] 5.2 前端全量 vitest：1367 passed；tsc --noEmit 零错
- [ ] 5.3 真机冒烟：GLM-5.3-flashx 配置开思考 low → 连接测试通＋正文生成通；发版随包
