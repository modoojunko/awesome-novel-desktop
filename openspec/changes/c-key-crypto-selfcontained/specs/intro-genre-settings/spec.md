## MODIFIED Requirements

### Requirement: AI 就绪状态的单一事实源

- 「本书 AI 是否就绪」SHALL 由**后端一次判定、前端只消费**，SHALL NOT 由前端用本地配置列表自行推导（消除前后端判据漂移）。
- `GET /novels/{id}/ai-model` SHALL 扩展返回 `{ api_config_id, model, config_name, ai_state, effective_model, reason?, message? }`：
  - `ai_state ∈ {ready, member_required, no_key, missing_model, invalid}`（**与 `detail.reason` 同枚举**）——**覆盖「AI 为什么不可用」的全部原因**，前端门控只读这一个字段、一次分派（不再 `useFeature` + `ai_state` 两处判）；判定优先级 `member_required > invalid > no_key > missing_model > ready`。`member_required` 只拦「调用 AI」，**不拦模型配置本身**。
  - `ready` 判据 SHALL 为：`ai_config_id` 与 `ai_model` 均非空 **且 本书绑定的配置存在** **且 该配置有可用 Key** **且 `ai_model ∈ json.loads(config.models)`**（与绑定校验共用同一谓词——`refresh-models` 后旧模型被移除不得再报 ready）。
  - **「有可用 Key」SHALL 含可解密性**：存储的 Key SHALL 解密出**非空明文**方视为可用——字段非空但密文无法解密（加密钥匙更换/丢失）SHALL 归入 `no_key`，SHALL NOT 放行至调用层（防裸 500）。判定「用户是否有任一可用 Key」（未绑定配置时的回退判据）SHALL 采用同一可解密口径。
  - `no_key` 粒度 SHALL 为**本书绑定配置级**（非「用户任意配置有 Key」）；引导文案 SHALL 区分三种情形：未填写 Key（去模型配置添加）、最近连接测试失败（检查或重测）、**Key 无法解密（提示重新粘贴保存——加密钥匙已更换，原密文不可恢复）**；三情形判别 SHALL 取「**解不开 优先于 测试失败**」的固定优先级（死文配置同时处于测试失败态时，文案 MUST 指向重新粘贴保存）。
  - `effective_model` SHALL 为按权威链算出的实际生效模型（`project.ai_model` 唯一权威），前端只显示、不推导。
- 前端 `useModelStatus` SHALL 删除本地四态推导，直接消费 `ai_state`/`effective_model`；AI 行门控按 `ai_state` 分派；错误兜底的 `detail.reason` SHALL 与 `ai_state` **共用同一枚举**（`no_key`/`missing_model`/`invalid`）。

#### Scenario: 前后端判据不再漂移

- Given 某书 `ai_config_id` 有值但 `ai_model` 为空
- When 查看该书 AI 就绪状态
- Then 后端下发 `ai_state="missing_model"`，前端据此拦在「先选模型」，不会放行调用（不再出现「前端放行、后端 503」）

#### Scenario: 配置已删的 invalid 由后端判定

- Given 某书绑定的 API 配置已被删除
- When 查看该书 AI 就绪状态
- Then 后端下发 `ai_state="invalid"`（不再是仅前端派生态）

#### Scenario: 模型被刷新移除后不再报就绪

- Given 本书绑定模型 x，其后配置的模型列表刷新且不再含 x
- When 查看该书 AI 就绪状态
- Then `ai_state` 不再为 `ready`（`model ∈ config.models` 谓词生效）

#### Scenario: 密文无法解密时拦截在引导而非 500

- Given 某书绑定配置的 `api_key` 字段非空（`enc:` 密文），当前加密钥匙无法解出明文，且该配置 `last_test_status` 同时为失败态（auth_error）
- When 调用该书的任一 AI 端点（如卷规划 `/volumes/ai/options`）
- Then 请求 SHALL 被门控以 **503** + `detail.reason="no_key"` 拦截，message 按固定优先级指向「重新粘贴保存」（优先于测试失败文案）；SHALL NOT 出现 500，SHALL NOT 发起模型调用

#### Scenario: 全部密文解不开时用户级回退判据不放行

- Given 用户存在任一 `api_key` 字段非空的配置，但全部密文无法解密
- When 未绑定配置的书查询 AI 就绪状态
- Then 判定 SHALL 为 `no_key`（「用户有任一可用 Key」按可解密口径），SHALL NOT 因字段非空而误判可回退

### Requirement: 后端模型调用分层

- C端后端模型调用 SHALL 分层且边界可验证：**配置层**（`api_configs/`，存配置/测连接/记用量）→ **解析层**（`effective_model`，`project.ai_model` 唯一权威）→ **判定层**（`compute_ai_state`，单一事实源）→ **客户端层**（`ai_client.py`，构造连接、调用、按 `api_format` 落地 `json_mode`）→ **门控层**（`require_ai_access` + `require_novel_model`，判据复用判定层）→ **业务层**（`write/`/`settings/`/`chapters/`/`prompt/`/`archive/`/`story/`/`novels/`）→ **prompt 层**（模型无关模板）→ **计量层**（记实际模型 id）。
- 边界 SHALL 分「可 grep 门禁」与「review 清单」：
  - **可 grep**：① 业务层禁裸 `get_ai_client()`——`grep -rnE '\bget_ai_client\(' client/backend --include='*.py' | grep -vE 'ai_client\.py|/tests/|ai_prefill\.py|novels/router\.py|__pycache__|\.mimosa' | grep -vE '^\S+:[0-9]+:\s*#'` 须为空（豁免：`ai_client.py` 定义、`tests/`、`ai_prefill.py`、`novels/router.py` suggest-meta）；② `record_usage` 记实际模型 id（`grep -rn 'model="haiku"'` + 各调用点核对）；③ 门控违规近似 `grep -rnE 'check_permission\(|is_member' client/backend/{write,settings,chapters,prompt,archive,story,novels}` 须为空；④ **门控覆盖近似检查**：`get_ai_client_for_novel` 的每个调用文件，其所在路由模块（或其上游路由模块）须出现 `require_novel_model` 或等价门控依赖——近似性声明：调用点多在 service 文件（`write/auxiliary.py`、`story/engine.py`、`archive/service.py`），grep 做不了「文件→路由模块」映射，须配静态映射/豁免表（豁免至少含：`ai_client.py` 定义、`tests/`、`ai_prefill.py`、`novels/router.py` suggest-meta、`archive/service.py` 与 `archive/reconcile.py`——两处为 try/except 降级路径自带处理，非门控对象）。
  - **review 清单**（不可 grep）：① 业务层是否直读 `writing_model` 决定模型；② 门控是否只在 dependency 且判据复用判定层；③ 就绪状态是否只在判定层。

#### Scenario: story 推演端点的门控覆盖

- Given story 推演路由的路径参数只有 `deduction_id`（`project_id` 在会话引擎内部持有，不在路径/查询参数）
- When 死文配置下调用 `/api/story/{deduction_id}/round`
- Then SHALL 由等价门控（从会话引擎取 `project_id` 后复用判定核心的 dependency）以 503 `no_key` 拦截；SHALL NOT 穿透到 `get_ai_client_for_novel`（现状：ValueError 被 `gather(return_exceptions=True)` 吞掉，表现为静默空回合、无任何用户信号）

#### Scenario: 业务层不得绕过客户端层

- Given 任一 C端 AI 端点
- When 静态检查其客户端获取方式
- Then 只出现 `get_ai_client_for_novel(novel_id)`，无裸 `get_ai_client()`（`ai_prefill.py` 除外）

#### Scenario: 模型权威链不可穿透

- Given `writing-style.yaml` 的 `writing_model` 写了具体模型名
- When 该书的 AI 调用取模型
- Then 仍以 `project.ai_model`（经解析层 `effective_model`）为准，字面覆盖被忽略
