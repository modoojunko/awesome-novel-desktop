## 1. 权益发放（契约单源＋两端镜像）

- [x] 1.1 `docs/contracts/entitlement-defaults.json`：pro/max features 追加 `ai-detect`（trial/free/none 不动）
- [x] 1.2 `server/app/config.py` ENTITLEMENT_DEFAULTS：pro/max 同批追加（兜底口径与契约一致）
- [x] 1.3 `client/backend/auth_local/service.py` STANDARD_FALLBACK：pro/max 同批追加；对拍测试（test_entitlement_sync 3.6）随同契约自动对齐

## 2. C端文案与注释口径

- [x] 2.1 `AiAssistPanel.tsx`：锁定徽章「MAX 专属」→「PRO 专属」、锁定描述「MAX 会员权益 · 升级后…」→「PRO 会员权益 · …」、就绪徽章「MAX 权益」→「PRO 权益」、底部来源声明「（MAX 会员权益）」→「（PRO 会员权益）」；四态注释改「无 ai-detect 权益／有权益」口径
- [x] 2.2 `ZhuquePanel.tsx`：介绍文案「MAX 会员权益（试用不含）」→「PRO 会员权益（试用不含）」＋头注同步
- [x] 2.3 `features.ts`／`features.test.ts`／`AiWriterAssistant.tsx`：注释口径同步（发放与锁定机制零改动；`maxlk` 内部变体不改名，CSS `zq-maxlk` 不动）

## 3. 测试与验收

- [x] 3.1 【pytest/vitest 本地跑】后端 `test_entitlement_sync.py`（3.6 对拍）＋`test_zhuque.py` 31 绿；S端 `test_check_auth_extension.py` 8 绿；前端 `features/zhuqueWorkbench/zhuqueConfig/useZhuqueCheck` 48 绿＋tsc 无新错；ruff 两文件净
- [x] 3.2 e2e 核对：`zhuque.spec.ts` 种子 MAX＋已配 Key——max ⊇ pro 收窄后判定不变，无需改种子；无 vitest/e2e 钉「MAX 专属」文案（静态核对）
- [ ] 3.3 【待真机验收】PRO 账号真机走查：模型配置 → 朱雀页签配置 Key → 工作台检测行就绪 → 发起检测出结果条与段落标注；试用账号确认仍锁定（「PRO 专属」章）
- [ ] 3.4 【运维随发布】生产 S端 发布本改后，核对 tiers 表 entitlement 配置——若 pro 档行存有 JSON，须同步补 `ai-detect`（defaults 仅为兜底）；验证 check-auth 快照 features 含该 key
