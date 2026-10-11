# c-fewshot-json-contract

## Why

真机反馈（v0.32，测试同学，DeepSeek 供应商）：文风面板点「例句提炼」必现
「AI 学习失败，可重试：Error code: 400 — Prompt must contain the word 'json' in some
form to use 'response_format' of type 'json_object'」。

定诊（2026-10-11）：

- `fewshot-mine` 端点（`settings/ai_router.py`）经 `_distill_llm → _judge_chat(json_mode=True)`
  落 `response_format={"type":"json_object"}`（`ai_client.py`）；DeepSeek 等 OpenAI 兼容
  供应商硬性要求提示词含「json」字样，否则 400 拒收。
- 提示词走分层模板 `style_fewshot_mine.prompt`（提示词仓）；v2 分层迁移时模板自带的
  system 段顶掉了代码内置兜底「只输出 JSON，不要任何其他文字」，而迁移后的模板
  system/user 两段均无「json」字样——输出契约整句丢失。
- 连带缺陷：模板没有任何输出契约（未告知模型输出 `{"lines": [...]}`），即使换不
  enforce 该约束的供应商，`data.get("lines")` 也取不到 → 502「例句提炼返回结构不对」。
- 全仓 51 个分层模板排查：仅 `style_fewshot_mine` 一个被 json_mode 消费的模板缺
  「json」字样（`write_chapter` 流式散文、`polish_text` 非 JSON 输出、`prompt_crafting`
  无运行时消费方，均不触此约束）——孤例，但没有任何守卫阻止下一个模板重演。
- 测试缺口：fewshot-mine 全链零测试覆盖；测试态 AI 为 stub，不看 `response_format`。

## What Changes

- 提示词仓（awesome-novel-prompts，跨仓同批）：`prompts/style_fewshot_mine.prompt`
  system 段补回输出契约——只输出 JSON 对象 `{"lines": [...]}`（1–3 条原文摘录），
  同时满足供应商「提示词含 json 字样」前置约束与下游解析的结构要求。
- 提示词仓新增仓库不变量守卫测试（牙齿所在：模板与测试同仓，C端 CI 无模板源、
  守卫放 C端 会静默跳过）：例外名单（注入片段资产 ∪ 成品文本输出三件）之外的
  全部模板，剥注释后有效文本必须含「json」（大小写不敏感）；倒置默认——新模板
  默认受覆盖，豁免须显式登记。
- C端补 fewshot-mine 行为钉（桩捕获实发提示词，随缺源转跳纪律）：钉「实发
  system+prompt 必含 json 字样」「模板声明 lines 输出契约」「响应按 lines 解析」
  三条；端点本身零生产代码变更。
- 发布链路：提示词包重发包（发布态客户端唯一来源是已装包；不重发，测试同学的
  v0.32 装机拿不到修复）。

不改动（明确出范围）：`ai_client.py` 运行时自动补「json」字样的兜底防御——设计阶段
作为备选评估后不立项（见 design.md「备选与取舍」）；`polish_text`/`write_chapter`/
`prompt_crafting` 三个无 json_mode 消费的模板不动。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `ai-client`: 新增「JSON 模式调用必须自证满足供应商 response_format 前置约束」
  需求——任何 json_mode 请求的生效提示词（system＋messages）必须含「json」字样，
  由静态守卫测试在 CI 强制；补 fewshot-mine 调用点与 lines 解析契约场景。

## Impact

- C端：`client/backend/settings/ai_router.py`（fewshot-mine 无行为变更，仅测试钉）、
  `client/backend/tests/`（新增守卫测试）；无前端改动、无 API 契约变更、无数据迁移。
- 提示词仓（sibling 私有仓）：`prompts/style_fewshot_mine.prompt` 单模板修改 +
  `publish.py` 重发包；C端开发/测试态经 `PROMPT_PACK_DEV_DIR` 直读 sibling，发布态
  需装新包（与 v0.31 起挂账的提示词包重发同批走，注意 prompts 仓 Actions 配额墙）。
- 无界面改动（Design Impact 判定：纯后端提示词契约＋测试，不触任何屏/弹层/共享段，
  免原型先行）；无用户可见文案变更（既有 502/400 兜底文案保留）。
