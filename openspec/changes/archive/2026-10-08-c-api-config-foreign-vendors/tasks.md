# Tasks — c-api-config-foreign-vendors

## 1. 后端：探针 404 降级放开到 openai 格式（降级三件套改造）

- [x] 1.1 `connection.py` 降级管道改造三件套：① fallback 元组改 `(url, headers, reply_fn)`——openai 分支补 `POST {base}/chat/completions`＋Bearer＋`_openai_reply_text`，anthropic 分支把 `_anthropic_reply_text` 装进 fallback（修复 404 分支提取器烤死 anthropic、openai 降级恒判负）；② payload 移出 `_build_probe`、404 分支按 `_probe_model([], vendor_id, preferred_model)` 现解——anthropic 尾垫 `_ANTHROPIC_PROBE_MODEL`、openai 无 id 不降级判负（顺带修齐存量分歧：anthropic 降级从恒用占位 id 改为认已选模型）；③ `NO_MODEL_LIST_NOTE` 拆 anthropic/openai 双文案（openai 版去掉「改成 openai 重测」尾句），三个消费点各自选版——`test_connection` 404 降级路径、`fetch-models` anthropic 404 分支、`model-candidates` 端点按配置 `api_format` 选版——`test_api_format.py` 用例矩阵：404＋手填模型 id（openai-compat 主路径＝Gemini 直配流）→ 降级通过、回复提取正确；404＋无 id → 判负不发生成请求；降级探针 404/405 → 判负点名实际地址；anthropic 降级用例扩断言探针 id＝preferred（`test_models_404_falls_back_to_messages` 现未断言 id）
- [x] 1.2 存量用例语义翻转适配：`test_openai_format_no_fallback_on_404` 按新语义改写（404＋无 id → 判负）而非删除；复验 fetch-models 轻探针零生成语义未被波及（fallback 元组形状变更不破坏其解构；openai 格式 404 仍判失败提示核对），对应用例保持绿；跑 `client/backend` 全量 pytest 确认零新增红

## 2. 前端：登记值修正＋引导文案

- [x] 2.1 `vendorDefaults.ts`：openai 登记值改 `https://api.openai.com/v1`、ollama 改 `http://localhost:11434/v1`（注释登记依据：SDK 实证裸域名生成 404）；`ProviderIcon.tsx` `FORMAT_PLACEHOLDER` openai 示例改带 `/v1`——vitest 断言预填值的用例同步更新
- [x] 2.2 `ApiConfigForm.tsx`：选「OpenAI 兼容」时在 Base URL 区域下方渲染兼容模版引导文案（Gemini 官方兼容层地址＋手填模型 id 说明＋反代/转发说明），样式随表单既有 hint 行；vitest 断言显隐与文案要素
- [x] 2.3 检查 e2e 中钉了旧预填 URL（`https://api.openai.com`）的 spec 并同步；隔离栈跑 api-config 相关 e2e 绿

## 3. 收尾

- [x] 3.1 `openspec validate --specs` 全绿（重点 `model-api-config` delta 与主 spec 合流无场景遗漏）；todo.md 登记进度；真机冒烟项（OpenAI 预填只填 Key 全链、Gemini 兼容层直配、引导文案显示）随归档验收执行
