# c-fewshot-json-contract — 设计

## Context

调用链（定诊 2026-10-11，实锤）：

```
文风面板「例句提炼」
→ POST /settings/ai/style/fewshot-mine（settings/ai_router.py）
→ _distill_llm → _judge_chat(json_mode=True)
→ ai_client：OpenAI 兼容路径落 response_format={"type":"json_object"}
→ DeepSeek：提示词须含「json」字样，否则 400 invalid_request_error（本例）
```

提示词来自分层模板 `style_fewshot_mine.prompt`（提示词仓）。端点取
`load_layers("style_fewshot_mine")` 的 system 段，**非空即顶掉**代码内置兜底
「只输出 JSON，不要任何其他文字」（`ai_router.py` `_s_fw or ...`）。v2 分层迁移
把 system 段写实后，「只输出 JSON」这句输出契约没有跟过去——模板 system/user
两段均无「json」字样，也没有任何 `{"lines": ...}` 结构说明。

关键事实：

- 全仓 60 模板排查：缺「json」的**分层调用模板**仅 4 个——本案
  `style_fewshot_mine` ＋ 3 个非 JSON 输出模板（`write_chapter` 流式散文、
  `polish_text` 润色散文、`prompt_crafting` 提示词成品），后三者不走 json_mode，
  不触供应商约束。**孤例，非面**。
- 该 400 只在 enforce 该规则的供应商出现（DeepSeek 实锤；GLM/Anthropic 路径
  不 enforce 或无 response_format）——开发自测未复现的原因。
- fewshot-mine 全链零测试（backend/前端/e2e 均无）；测试态 AI 为 stub，
  不看 `response_format`，测不出来。
- C端 CI **无提示词模板源**（conftest 缺源转跳三层，c-prompt-source-flip 判例）
  ——任何依赖模板文本的 C端 测试在 CI 里静默跳过，没有牙齿。
- 提示词仓自有 pytest 内容闸门（`sync.py lint`＋`pytest tests/`），模板与测试
  同仓同 CI 面（Actions 配额 10-10 起停摆，闸门以本地为准）；已有
  「`assert "JSON" in text`」先例（intro 模板族测试）。
- 用户已归档 3 章，数据侧无问题——失败纯在请求格式。

## Goals / Non-Goals

**Goals:**

- 例句提炼在 enforce json 字样约束的供应商上恢复可用：提示词含「json」＋
  声明 `{"lines": [...]}` 输出契约（连带修掉缺输出契约的潜在 502）。
- 仓库不变量守卫：任何调用模板丢「json」字样在测试链即红，新模板默认受覆盖。
- 发布链闭环：新提示词包可发包到装机器（否则测试同学的 v0.32 装机拿不到修复）。

**Non-Goals:**

- 不动 `ai_client.py`（运行时自动补「json」的兜底防御——见备选取舍）。
- 不动 `polish_text`/`write_chapter`/`prompt_crafting` 三个非 JSON 输出模板。
- 不给 fewshot-mine 补前端/e2e 覆盖（本 change 只钉请求侧契约与解析行为；
  端点本身无行为变更）。
- 不清理 `prompt_crafting` 的过期消费者注释（触发端点随「AI 润色」全链退役
  已消失，归 test_prompt_dead_refs 既有流程管，与本 change 无关）。

## Decisions

### D1 主修落在提示词仓模板，C端零代码变更

`style_fewshot_mine.prompt` system 段补输出契约，一词两用：

- 「json」字样满足供应商 `json_object` 前置校验（system 与 user 消息合并后
  参与校验，放恒定 system 段即可、且吃前缀缓存）；
- `{"lines": [...]}` 结构声明钉住解析契约，消除缺输出契约的潜在 502
  （`data.get("lines")` 取不到 →「例句提炼返回结构不对」）。

C端 `ai_router.py` 不改：`_s_fw or 兜底` 的语义本来正确（模板优先、兜底保底），
错在模板内容。备选「把兜底 JSON 句拼接到模板 system 之后」被否：在调用方补丁
掩盖模板契约缺损，且治不了其他模板的同病。

### D2 守卫主落提示词仓测试链（倒置默认＋白名单例外），不在 C端 做 AST 扫描

提示词仓新增仓库不变量测试：**例外名单外的一切模板**（含未分层新模板）剥注释
后有效文本必须含「json」（大小写不敏感），缺即红并指名。例外名单
＝ 注入片段资产（`test_prompt_layering.py` 的 `ASSETS` 六件——非独立调用）∪
成品文本输出三件（`write_chapter`/`polish_text`/`prompt_crafting`——输出
散文/提示词成品，不走 json_mode）。倒置默认的理由：新模板默认要求 JSON 契约，
豁免须显式登记——比「正向枚举 json_mode 消费名单」安全（正向名单漏登记即
静默失控）。

备选「C端 AST 扫全部 `json_mode=True` 调用点→解析模板名→断言含 json」被否：
C端 CI 无模板源，守卫在 CI 静默跳过（无牙齿）；本地有源时的覆盖与提示词仓
守卫重复；调用点→模板名的映射对动态命名（`settings_{stype}` 族）脆。

### D3 C端补行为钉（桩捕获实发提示词），跟随缺源转跳纪律

fewshot-mine 端点测试：桩化 `_judge_chat`/客户端捕获实发 system＋prompt，
断言（a）含「json」字样（b）模板声明 lines 键（c）响应按 lines 解析返回。
测试随既有 conftest 缺源转跳纪律（无模板源 skip——CI 无牙齿已知，
牙齿在 D2；本钉的价值在本地与有源 CI 面上防端点回归）。

### D4 发布链按提示词仓既有四步走

`publish.py`：① build＋上传 v{N}（latest.json 暂不翻）② S端 登记 CEK
③ verify＋真机 smoke ④ 最后翻 latest.json。开发/测试态经
`PROMPT_PACK_DEV_DIR` 直挂 sibling，模板改动即时生效；发布态客户端唯一来源
是已装包——**不发包＝修复不落地**。发布版本目录不可变，重复版本号被前置闸拦。

双仓联动纪律（提示词仓 AGENTS.md）：C端先合，提示词仓同批对齐，两侧 commit
互引 `c-fewshot-json-contract` 标记；模板正文直改 `prompts/*.prompt`，
manifest 由 `sync.py` 生成勿手改，闸门本地跑（`sync.py lint`＋pytest，
venv ≥3.10）。

## Risks / Trade-offs

- [守卫例外名单被滥用（把该带 JSON 契约的模板塞进名单）] → 豁免须显式登记＋
  每条注明理由，每次增删在 review diff 中可审（名单制纪律；`MIGRATION_PENDING`
  的「只减不增」是迁移清单专用语义，豁免名单天然可增）。
- [模板改了但发布包没重发，装机端长期带着病] → tasks 把 publish 四步列为
  独立任务不与编码合并；与 v0.31 起挂账的提示词包重发同批清。
- [`{"lines": ...}` 结构示例进入 system 段吃掉少量前缀缓存 token] → 单模板
  一次调用、量级可忽略；输出契约本属 system 段职责（分层协议明文）。
- [其他供应商未来收紧约束（如强制小写 json）] → 现契约「大小写不限」由守卫
  以不敏感匹配强制，供应商侧再收紧时只需改守卫正则一处。

## Open Questions

（无——范围与拍板已定：ai_client 运行时兜底不立项，记为备选。）
