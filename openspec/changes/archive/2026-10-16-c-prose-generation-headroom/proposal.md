# c-prose-generation-headroom

## Why

MiniMax M3（用户实配：anthropic 兼容端点＋thinking_enabled=1 effort=low）正文生成实测思考超过 90 秒——首字守卫判死（llm.log：`op=write_chapter model=MiniMax-M3 duration_ms=90034 error=thinking timeout: no prose within 90.034s`），界面空白＋超时；即便放行守卫，正文 max_tokens=8192 与思考共用预算，M3 长思考大概率烧光预算致正文零字（c-prose-thinking-timeout 的 GLM effort=max 同款）。90 秒与 8192 都是以 GLM 系思考时长标定的，深度思考模型需要成级数的余量。

## What Changes

- **正文流式生成首字守卫 90 秒 → 600 秒**（仅 write_chapter 调用点；判定类短调用与其余 op 维持默认 90 秒）。思考期流上有增量、真挂死仍由「相邻事件间隔」read 上限（120 秒）兜底，守卫只对「健康思考但迟迟不出正文」的总时长封顶。
- **正文生成 max_tokens 8192 → 32768**（仅 write_chapter 调用点）：思考与正文合计预算给足；按实际用量计费，未用不产生成本。遥测面（finish_reason=length 截断判定）不变。
- **内联思考剥离同构扩展到 anthropic 兼容路径**（流式 text_delta 与非流式 text 块）：MiniMax 的 anthropic 端点在思考关断/未协商时会把 `<think>…</think>` 内联进 text 交付（用户原始泄漏截图即此形态——当时该配置就跑在 anthropic 格式上）；GLM/DeepSeek 等 anthropic 端点从不产出该形态，窄口径零影响。流式守卫撤点同步对齐（`<think>` 段不算首字）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `prose-writing`：**MODIFIED**「思考太久按失败收场（首字守卫）」——上限 90 秒 → 600 秒＋理由；判死语义/覆盖面/scenarios 不变。
- `ai-client`：**MODIFIED**「AI 调用必须有显式超时」——补「正文流式生成放宽至 600 秒」分级口径；**MODIFIED**「内联思考不得混入交付文本」——剥离范围从 openai 兼容路径扩至 openai 与 anthropic 兼容路径两路同构。

## Impact

- `client/backend/ai_client.py`：anthropic 流式分支接入剥离状态机（守卫撤点对齐）、anthropic 非流式出口剥前缀。
- `client/backend/write/router.py`：正文生成守卫与预算常量。
- 测试：anthropic 内联剥离（流式/非流式）、守卫不被 `<think>` text_delta 缴械、调用点常量钉。
- 无前端/API 契约变化；无界面改动（不涉 Design Impact）。
