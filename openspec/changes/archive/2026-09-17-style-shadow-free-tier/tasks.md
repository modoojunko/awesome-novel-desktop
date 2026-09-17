# Tasks

- [x] 1.1 `StyleShadowPane` 免费分支移除 PRO 占位：基线只读＋影子行全档位渲染——验证：`src/__tests__/StyleShadowPane.test.tsx`「免费可手工添加覆盖行」绿
- [x] 1.2 影子行行内编辑（取值/理由失焦保存）＋「添加覆盖行」控件（行选择＋取值门槛）——验证：同测试 PUT 载荷断言（含新增行）
- [x] 1.3 AI 建议区 isPro 分支：免费呈现锁定说明（非占位）；归档章只读禁用——验证：同文件「归档章只读」与 PRO「采纳写影子」用例
- [x] 1.4 `book.css`：`.ss-row` 四列栅格＋`.ss-add`；design:lint 过——验证：`npm run design:lint`（冻结统计无新增阻断）
- [x] 1.5 规范：workbench REMOVED/ADDED（档位契约重写）＋style-quant 增量（PUT 门控句落定）——验证：`openspec validate style-shadow-free-tier --strict`
- [x] 1.6 回归：vitest 全量 332 绿＋tsc 零错误——验证：本机执行
