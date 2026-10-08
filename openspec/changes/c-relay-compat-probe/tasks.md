# c-relay-compat-probe — 任务

> 实现先于立项补档（2026-10-08 内测中转站反馈热修，PR #747）；本档为评审后补立，已完成项如实勾选。

## 1. 裸域名同源归一

- [x] 1.1 `connection.normalize_openai_base` 单源（段判 v+数字，防 Gemini `/v1beta` 中段误伤）＋models 探测／主链对话探针／404 降级地址三处接入
- [x] 1.2 `ai_client` openai 分支 base 归一传 SDK＋`_base_url` 同步归一形（anthropic 分支不动）
- [x] 1.3 用例：归一化表（裸域名/尾斜杠/v1/v4/compatible-mode/v1beta/11434/空）＋裸域名主链探针＋版本段不动＋Gemini 兼容层路径归位＋405 钉子改点名归一地址

## 2. 清单 403 降级

- [x] 2.1 `test_connection`：models 403 并入 404 降级链（两格式同享，note 按 403/404 分文案）＋401 硬判保持＋openai 无 id 判负提示填写模型名
- [x] 2.2 `fetch_models`：openai 格式 403 回 ok＋空清单＋候选＋`MODEL_LIST_FORBIDDEN_NOTE`；anthropic/ollama 403 保持鉴权失败硬判
- [x] 2.3 用例：探测侧（403＋已选模型通／403 双拒如实判 auth／403 无 id 判负／401 硬判不降级／anthropic 403 降级）＋清单侧（openai 403 回说明／anthropic 403 硬判）

## 3. 门禁

- [x] 3.1 后端 pytest 全量绿（2099 passed 1 skipped）；ruff 0.16.3 绿
- [x] 3.2 openspec validate change＋model-api-config strict 双绿
- [ ] 3.3 真机冒烟：lunarfox 裸域名与 `/v1` 两种填法全链（Key 失焦拉清单 → 测试连接 → 保存 → 正文生成）；Gemini 官方兼容层直配（#741 遗留顺带修）
- [ ] 3.4 归档：specs sync 主 spec＋todo 收口（随归档 PR）
