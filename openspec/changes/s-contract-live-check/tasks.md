## 1. 双端影响判定

- [x] 1.1 双端影响判定：S web 测试基建＋契约 fixture，无产品界面改动、不触共享段——Design Impact「不适用」，无需原型先行

## 2. 活体冒烟档

- [x] 2.1 新增 `server/frontend/e2e/live/smoke.spec.ts`：直接 import base（不挂 mockApi），落地页渲染/登录成功进控制台/备案页三断言，`S_LIVE_BASE_URL` 未设整组 skip——diff 贴进 change 目录
- [x] 2.2 本地起 uvicorn（sqlite）真跑 2.1，三条断言绿——输出结论贴进 change 目录

## 3. 契约 fixture 单源

- [x] 3.1 新增 `docs/contracts/check-auth.example.json`（键集/类型族锚定，不含真实凭据）——diff 贴进 change 目录
- [x] 3.2 S端契约测试：check-auth handler 实际响应与 fixture 对拍（键集一致）——`pytest server/tests/contract` 绿
- [x] 3.3 C端消费侧对拍测试：auth_local 代打解析容忍 fixture 形状（加键兼容）——`pytest client/backend/tests` 相关用例绿
- [x] 3.4 反向验证：fixture 删一个既有键，两侧至少一侧测试变红——红→绿记录贴进 change 目录

## 4. nightly 接线

- [ ] 4.1 nightly（e2e-scheduled 或独立 job）起 S 后端并设 `S_LIVE_BASE_URL` 真跑活体组——首次运行结论贴进 change 目录

## 5. 回归

- [x] 5.1 `server/frontend` 全量 mock e2e 不受影响（仍全绿）——结论贴进 change 目录
- [x] 5.2 S端 pytest 全量绿；C端 pytest 相关用例绿——结论贴进 change 目录
- [x] 5.3 本 change 无前端组件改动，design:lint / design:check / tsc / vitest 不适用（判定依据见 1.1）
