# Tasks: c-writing-agent-tier

## 1. 原型先行（UI 判定）

- [x] 1.1 判定：执行门复用既有「gate」事件与升级卡（Aui2Dock cardConfig code="gate"），零新增视觉、零新组件；不新增原型状态。依据：`client/frontend/src/components/novel/chat/Aui2Dock.tsx` 既有 gate 卡与 `__tests__/Aui2Dock.test.tsx` gate 用例
- [x] 1.2 无共享段改动（features.ts / assistant 注册表均为 C 端私有）；design:lint 结论见 6.1

## 2. 词汇表与契约

- [x] 2.1 `client/frontend/src/lib/features.ts` 增 `assistant-execute`（minTier standard）；`features.test.ts` 断言 free 锁定、standard 放行（8/8 通过）
- [x] 2.2 `docs/contracts/entitlement-defaults.json` 升 v3，standard/pro/max/trial 增 `assistant-execute`；`test_entitlement_sync.py` 对拍通过
- [x] 2.3 `auth_local/service.py` STANDARD_FALLBACK 四档同步增键；`test_assistant_execute_gate.py` 断言 member 档含、free/none 不含

## 3. 后端执行门

- [x] 3.1 `Tool` 增 `requires_feature` 字段；11 个写类工具（结构写/页面字段写/知识库写）全部声明 `assistant-execute`；读/产卡类为空
- [x] 3.2 `assistant/router.py` 新增 `execute_gate_event()`，在 `_gate_fn` 读类早退后、feature_key 闸前判定：无权 yield gate 事件后收口（不调用工具、不弹授权卡）；单测覆盖
- [x] 3.3 启动校验：`tools.py` 模块尾对 `TOOL_REGISTRY` 断言写类工具必须声明 `requires_feature`，缺声明 RuntimeError fail loud；`test_registry_declares_execute_for_all_write_tools` 双向断言
- [x] 3.4 标准档放行：`execute_gate_event` 在 `ai_access_granted("assistant-execute")=True` 时返回 None，后续走既有授权梯度（`test_assistant_write_gate.py` 既有默认档弹卡用例覆盖）

## 4. 前端交互

- [x] 4.1 执行类 chips 保持可见（入口一律可见口径，不新增锁定样式）；点击后由后端执行门回升级卡（沿用 gate 卡渲染）。验证：features 单测 + gate 事件形状复用既有用例
- [ ] 4.2 升级文案（refusal 句）与升级出口待 boss 评审；出口沿用既有 gate 卡按钮（/plans 可达）
- [x] 4.3 快照缺失场景沿用 useFeature 既有兜底（未授权锁定，与 ai-detect 同口径）；`_LEGACY_IMPLICIT_FEATURES` 增 `assistant-execute` 按标准档隐式放行，避免旧快照误锁标准用户

## 5. 兼容与发布顺序

- [x] 5.1 旧快照（无该键）标准用户经 `_LEGACY_IMPLICIT_FEATURES` 放行；单测 `test_legacy_implicit_allows_standard`
- [ ] 5.2 发布前置：S 端 `assistant-execute` 上线并可从 check-auth 快照读到（待 S 端 change 落地后真机核验）
- [ ] 5.3 更新日志与客服话术（免费档执行收紧）待写

## 6. 回归

- [x] 6.1 `cd client/frontend && npm run design:lint`：exit 0；仅存量 `docs/design-c/prototypes/preview.html` emoji 提示（主检出基线一致），本变更未触发新违规
- [x] 6.2 `cd client/frontend && npx tsc --noEmit`：exit 0，无输出
- [x] 6.3 后端定向回归（主检出 venv 复用）：`pytest tests/test_assistant_execute_gate.py tests/test_assistant_registry.py tests/test_entitlement_sync.py tests/test_ai_feature_registry.py tests/test_assistant_write_gate.py -q` → **59 passed**；新增 6 例全绿；ruff 改动文件 All checks passed
- [ ] 6.4 相关 e2e（免费档执行拦截 / 标准档授权执行）未运行——挂账
- [ ] 6.5 真机走查（free 拦截、standard 可执行）未运行——待 S 端 key 上线后
